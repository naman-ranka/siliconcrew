"""LlmKeyProvider — which LLM key a request uses (Phase 2, slice 5).

Locked decision: BYOK for all three providers **plus** a capped hosted Gemini
3.5 Flash tier for users with no key of their own. Both are surfaced behind one
interface so the agent loop is unchanged — it asks for a key and gets a
request-scoped plaintext key, never an env var, never a log line.

BYOK keys are stored with **envelope encryption** (the GCP KMS pattern): a
random per-key Data Encryption Key (DEK) encrypts the API key; the DEK is then
wrapped by a Key Encryption Key (KEK) held in Cloud KMS. Only the wrapped DEK +
ciphertext are persisted. This module owns that orchestration; the AEAD
primitive (``DataCipher``) and the KEK (``KekProvider``) are injected, so:

  * production wires Fernet + Cloud KMS;
  * self-host wires Fernet + a local master key;
  * tests inject reversible fakes to exercise the envelope flow.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
from dataclasses import dataclass
from typing import Dict, Optional, Protocol

from src.llm.factory import infer_provider_from_model


@dataclass
class LlmKey:
    """A request-scoped resolved key. Do not persist or log ``api_key``."""

    provider: str
    api_key: str
    source: str  # "byok" | "hosted" | "env"
    model: Optional[str] = None  # hosted tier may pin a model


# Human-facing provider names for error copy surfaced to the user (the raw ids
# are lowercase/unbranded, e.g. "anthropic"; the UI shows these instead).
_PROVIDER_DISPLAY = {
    "gemini": "Gemini",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
}


# ---------------------------------------------------------------------------
# Envelope encryption primitives (injected).
# ---------------------------------------------------------------------------


class DataCipher(Protocol):
    """Authenticated symmetric encryption with a caller-supplied key."""

    def encrypt(self, key: bytes, plaintext: bytes) -> bytes: ...
    def decrypt(self, key: bytes, token: bytes) -> bytes: ...


class KekProvider(Protocol):
    """Wraps/unwraps a DEK with a Key Encryption Key (Cloud KMS in prod)."""

    def wrap_dek(self, dek: bytes) -> bytes: ...
    def unwrap_dek(self, wrapped: bytes) -> bytes: ...


class FernetDataCipher:
    """Production/self-host AEAD via cryptography's Fernet (lazy import)."""

    def _fernet(self, key: bytes):
        from cryptography.fernet import Fernet

        return Fernet(base64.urlsafe_b64encode(key))

    def encrypt(self, key: bytes, plaintext: bytes) -> bytes:
        return self._fernet(key).encrypt(plaintext)

    def decrypt(self, key: bytes, token: bytes) -> bytes:
        return self._fernet(key).decrypt(token)


class LocalKekProvider:
    """Self-host KEK: wrap the DEK with a 32-byte master key via Fernet."""

    def __init__(self, master_key: bytes, cipher: Optional[DataCipher] = None):
        self._master = master_key
        self._cipher = cipher or FernetDataCipher()

    def wrap_dek(self, dek: bytes) -> bytes:
        return self._cipher.encrypt(self._master, dek)

    def unwrap_dek(self, wrapped: bytes) -> bytes:
        return self._cipher.decrypt(self._master, wrapped)


class KmsKekProvider:
    """Production KEK: wrap/unwrap the DEK with a Cloud KMS key (lazy import)."""

    def __init__(self, key_uri: str, client=None):
        self._key_uri = key_uri
        self._client = client

    def _kms(self):
        if self._client is None:
            from google.cloud import kms  # lazy

            self._client = kms.KeyManagementServiceClient()
        return self._client

    def wrap_dek(self, dek: bytes) -> bytes:
        return self._kms().encrypt(request={"name": self._key_uri, "plaintext": dek}).ciphertext

    def unwrap_dek(self, wrapped: bytes) -> bytes:
        return self._kms().decrypt(request={"name": self._key_uri, "ciphertext": wrapped}).plaintext


# ---------------------------------------------------------------------------
# Vault — persists only wrapped DEK + ciphertext, never plaintext.
# ---------------------------------------------------------------------------


class WrappedKeyStore(Protocol):
    def put(self, user_id: str, provider: str, blob: str) -> None: ...
    def get(self, user_id: str, provider: str) -> Optional[str]: ...
    def delete(self, user_id: str, provider: str) -> None: ...


class InMemoryWrappedKeyStore:
    def __init__(self) -> None:
        self._d: Dict[tuple, str] = {}

    def put(self, user_id, provider, blob):
        self._d[(user_id, provider)] = blob

    def get(self, user_id, provider):
        return self._d.get((user_id, provider))

    def delete(self, user_id, provider):
        self._d.pop((user_id, provider), None)


class SqliteWrappedKeyStore:
    """Persist wrapped (encrypted) BYOK blobs in SQLite (self-host / single node)."""

    def __init__(self, db_path: str):
        import os as _os

        self.db_path = _os.path.abspath(db_path)
        self._init()

    def _connect(self):
        import sqlite3

        return sqlite3.connect(self.db_path)

    def _init(self):
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS byok_keys ("
                "user_id TEXT NOT NULL, provider TEXT NOT NULL, blob TEXT NOT NULL, "
                "PRIMARY KEY (user_id, provider))"
            )
            conn.commit()

    def put(self, user_id, provider, blob):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO byok_keys (user_id, provider, blob) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, provider) DO UPDATE SET blob = excluded.blob",
                (user_id, provider, blob),
            )
            conn.commit()

    def get(self, user_id, provider):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT blob FROM byok_keys WHERE user_id = ? AND provider = ?",
                (user_id, provider),
            ).fetchone()
        return row[0] if row else None

    def delete(self, user_id, provider):
        with self._connect() as conn:
            conn.execute("DELETE FROM byok_keys WHERE user_id = ? AND provider = ?", (user_id, provider))
            conn.commit()


class PostgresWrappedKeyStore:
    """Persist wrapped BYOK blobs in Cloud SQL (shared across replicas)."""

    def __init__(self, dsn: str, connect=None):
        self._dsn = dsn
        self._connect_fn = connect

    def _connect(self):
        if self._connect_fn is not None:
            return self._connect_fn(self._dsn)
        import psycopg  # lazy

        return psycopg.connect(self._dsn)

    def init_schema(self):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS byok_keys ("
                "user_id TEXT NOT NULL, provider TEXT NOT NULL, blob TEXT NOT NULL, "
                "PRIMARY KEY (user_id, provider))"
            )
            conn.commit()

    def put(self, user_id, provider, blob):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO byok_keys (user_id, provider, blob) VALUES (%s, %s, %s) "
                "ON CONFLICT (user_id, provider) DO UPDATE SET blob = excluded.blob",
                (user_id, provider, blob),
            )
            conn.commit()

    def get(self, user_id, provider):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT blob FROM byok_keys WHERE user_id = %s AND provider = %s", (user_id, provider))
            row = cur.fetchone()
        return row[0] if row else None

    def delete(self, user_id, provider):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM byok_keys WHERE user_id = %s AND provider = %s", (user_id, provider))
            conn.commit()


class EnvelopeKeyVault:
    """Store/retrieve BYOK keys with envelope encryption.

    ``store_key`` generates a fresh DEK, encrypts the API key under it, wraps the
    DEK with the KEK, and persists ``{wrapped_dek, ciphertext}`` only.
    ``get_key`` reverses it, returning the plaintext into the request scope.
    """

    def __init__(self, store: WrappedKeyStore, data_cipher: DataCipher, kek: KekProvider):
        self._store = store
        self._cipher = data_cipher
        self._kek = kek

    def store_key(self, user_id: str, provider: str, api_key: str) -> None:
        dek = secrets.token_bytes(32)
        ciphertext = self._cipher.encrypt(dek, api_key.encode("utf-8"))
        wrapped_dek = self._kek.wrap_dek(dek)
        blob = json.dumps(
            {
                "wrapped_dek": base64.b64encode(wrapped_dek).decode("ascii"),
                "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
                "v": 1,
            }
        )
        self._store.put(user_id, provider, blob)

    def get_key(self, user_id: str, provider: str) -> Optional[str]:
        blob = self._store.get(user_id, provider)
        if not blob:
            return None
        data = json.loads(blob)
        wrapped_dek = base64.b64decode(data["wrapped_dek"])
        ciphertext = base64.b64decode(data["ciphertext"])
        dek = self._kek.unwrap_dek(wrapped_dek)
        return self._cipher.decrypt(dek, ciphertext).decode("utf-8")

    def has_key(self, user_id: str, provider: str) -> bool:
        return self._store.get(user_id, provider) is not None

    def delete_key(self, user_id: str, provider: str) -> None:
        self._store.delete(user_id, provider)


# ---------------------------------------------------------------------------
# Hosted-tier cost ceiling.
# ---------------------------------------------------------------------------


class HostedTierExhausted(Exception):
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.code = "hosted_tier_exhausted"
        self.message = message
        self.details = details or {}


@dataclass
class HostedTierLimits:
    tokens_per_day: int = 200_000
    global_cost_ceiling_usd: float = 50.0


class HostedTierLimiter:
    """Hard caps on the shared hosted Gemini key (per-user tokens/day + global $)."""

    def __init__(self, limits: Optional[HostedTierLimits] = None, clock=None):
        import time as _t

        self._limits = limits or HostedTierLimits()
        self._clock = clock or _t.time
        self._tokens: Dict[tuple, int] = {}
        self._global_cost = 0.0

    def _day(self) -> str:
        import time as _t

        return _t.strftime("%Y-%m-%d", _t.gmtime(self._clock()))

    def check(self, user_id: str) -> None:
        if self._global_cost >= self._limits.global_cost_ceiling_usd:
            raise HostedTierExhausted(
                "Hosted free tier is temporarily unavailable (global budget reached). Add your own API key to continue.",
                {"global_cost_ceiling_usd": self._limits.global_cost_ceiling_usd},
            )
        used = self._tokens.get((user_id, self._day()), 0)
        if used >= self._limits.tokens_per_day:
            raise HostedTierExhausted(
                f"Hosted free-tier daily token limit reached ({self._limits.tokens_per_day}). Add your own API key to continue.",
                {"tokens_per_day": self._limits.tokens_per_day, "used": used},
            )

    def record(self, user_id: str, tokens: int, cost_usd: float) -> None:
        self._tokens[(user_id, self._day())] = self._tokens.get((user_id, self._day()), 0) + tokens
        self._global_cost += cost_usd


# ---------------------------------------------------------------------------
# LlmKeyProvider — the interface the agent uses.
# ---------------------------------------------------------------------------


class LlmKeyProvider(Protocol):
    def resolve(self, user_id: Optional[str], model_name: str) -> LlmKey: ...


class EnvLlmKeyProvider:
    """Self-host: read the provider key from the environment (today's behavior)."""

    _ENV = {"gemini": "GOOGLE_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}

    def resolve(self, user_id: Optional[str], model_name: str) -> LlmKey:
        provider = infer_provider_from_model(model_name)
        key = os.environ.get(self._ENV[provider])
        if not key:
            raise ValueError(f"Missing API key env var {self._ENV[provider]} for provider '{provider}'.")
        return LlmKey(provider=provider, api_key=key, source="env")


class ByokHostedLlmKeyProvider:
    """Hosted: prefer the user's BYOK key; otherwise fall back to capped Gemini.

    For the requested model's provider:
      * if the user has stored a BYOK key → decrypt and use it;
      * else, only for Gemini, use the shared hosted key under hard caps;
      * else, signal that the user must add a key for that provider.
    """

    def __init__(
        self,
        vault: EnvelopeKeyVault,
        hosted_gemini_key: str = "",
        hosted_model: str = "gemini-3-flash-preview",
        limiter: Optional[HostedTierLimiter] = None,
    ):
        self._vault = vault
        self._hosted_gemini_key = hosted_gemini_key
        self._hosted_model = hosted_model
        self._limiter = limiter or HostedTierLimiter()

    def resolve(self, user_id: Optional[str], model_name: str) -> LlmKey:
        provider = infer_provider_from_model(model_name)

        if user_id:
            byok = self._vault.get_key(user_id, provider)
            if byok:
                return LlmKey(provider=provider, api_key=byok, source="byok")

        # Fall back to container environment variables if present (useful for single-user staging/prod)
        env_vars = {"gemini": "GOOGLE_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
        env_key = os.environ.get(env_vars[provider])
        if env_key:
            return LlmKey(provider=provider, api_key=env_key, source="env")

        # No BYOK key or env key — only the hosted Gemini tier is available, under caps.
        if provider == "gemini" and self._hosted_gemini_key:
            self._limiter.check(user_id or "anonymous")
            return LlmKey(
                provider="gemini",
                api_key=self._hosted_gemini_key,
                source="hosted",
                model=self._hosted_model,
            )

        display = _PROVIDER_DISPLAY.get(provider, provider.title())
        raise ValueError(
            f"No key available for {display}. Add your own {display} API key, "
            "or use the hosted Gemini tier."
        )

    @property
    def limiter(self) -> HostedTierLimiter:
        return self._limiter


# ---------------------------------------------------------------------------
# Factories — built once from settings (the single wiring point).
# ---------------------------------------------------------------------------

VALID_PROVIDERS = ("gemini", "openai", "anthropic")


def _derive_master_key(secret: str) -> bytes:
    """Derive a 32-byte master key from a configured secret string."""
    import hashlib

    return hashlib.sha256(secret.encode("utf-8")).digest()


def build_key_vault(settings, db_path: Optional[str] = None) -> Optional[EnvelopeKeyVault]:
    """Construct the BYOK vault from settings, or None if BYOK isn't configured.

    KEK selection:
      * ``KMS_KEY_URI`` set → Cloud KMS wraps the DEK (production).
      * else ``SILICONCREW_MASTER_KEY`` set → local master key (self-host BYOK).
      * else → None (BYOK disabled; endpoints return 503).

    Persistence: Postgres in hosted+Postgres, else SQLite at ``db_path``.
    """
    if settings.persistence_engine == "postgres" and settings.database_url:
        store: WrappedKeyStore = PostgresWrappedKeyStore(settings.database_url)
        try:
            store.init_schema()  # type: ignore[attr-defined]
        except Exception:
            pass
    elif db_path:
        store = SqliteWrappedKeyStore(db_path)
    else:
        return None

    if settings.kms_key_uri:
        kek: KekProvider = KmsKekProvider(settings.kms_key_uri)
    else:
        master = os.environ.get("SILICONCREW_MASTER_KEY")
        if not master:
            return None
        kek = LocalKekProvider(_derive_master_key(master))

    return EnvelopeKeyVault(store, FernetDataCipher(), kek)


def build_llm_key_provider(settings, vault: Optional[EnvelopeKeyVault]) -> LlmKeyProvider:
    """Pick the LLM key provider: env keys (self-host) or BYOK+hosted (hosted)."""
    if settings.llm_key_engine == "byok" and vault is not None:
        return ByokHostedLlmKeyProvider(
            vault,
            hosted_gemini_key=settings.hosted_gemini_key,
            hosted_model=settings.hosted_gemini_model,
        )
    return EnvLlmKeyProvider()
