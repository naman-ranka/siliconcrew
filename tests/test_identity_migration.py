"""Identity unification migration (Phase 2, Slice 3) — google_<sub> -> workos_<sub>.

Proves the re-key primitives and the operator utility with in-memory / tmp-file
fakes (no WorkOS, no network, no live DB):
  * MetadataStore.reassign_user moves projects/sessions/threads and nothing else.
  * The BYOK keystore re-keys the owner and the key STILL decrypts (no rewrap).
  * The migration utility is idempotent, isolates per-user failures, and dry-runs.
  * build_verifier prefers WorkOS when configured (the web/MCP unification point).
"""
import os

import pytest

from src.platform_engines import auth as A
from src.platform_engines.identity import WorkOSVerifier
from src.platform_engines.identity_migration import (
    IdentityMapping,
    load_mappings,
    migrate_batch,
    migrate_identity,
)
from src.platform_engines.llm_keys import (
    EnvelopeKeyVault,
    FernetDataCipher,
    InMemoryWrappedKeyStore,
    LocalKekProvider,
)
from src.platform_engines.metadata_store import SqliteMetadataStore


# --- metadata reassign ------------------------------------------------------


def _store(tmp_path):
    s = SqliteMetadataStore(str(tmp_path / "state.db"))
    s.init_schema()
    return s


def test_metadata_reassign_moves_all_owned_rows(tmp_path):
    s = _store(tmp_path)
    import datetime

    now = datetime.datetime(2024, 1, 1)
    s.create_project("p1", "Proj", now, user_id="google_alice")
    s.upsert_session("p1/s1", "google_alice", "S1", "m", "p1", now)
    s.create_thread("t1", "p1/s1", "google_alice", "Chat 1", "m", now)
    # A second user's data must be untouched.
    s.upsert_session("s2", "google_bob", "S2", "m", None, now)

    moved = s.reassign_user("google_alice", "workos_alice")
    assert moved == 3  # project + session + thread

    # Alice's rows are now under the new id...
    assert s.get_project("p1", user_id="workos_alice") is not None
    assert s.get_session("p1/s1", user_id="workos_alice") is not None
    assert s.get_thread("t1", user_id="workos_alice") is not None
    # ...and gone from the old id.
    assert s.get_session("p1/s1", user_id="google_alice") is None
    # Bob is undisturbed.
    assert s.get_session("s2", user_id="google_bob") is not None


def test_metadata_reassign_is_idempotent_and_validated(tmp_path):
    s = _store(tmp_path)
    import datetime

    s.upsert_session("s1", "google_alice", "S1", "m", None, datetime.datetime(2024, 1, 1))
    assert s.reassign_user("google_alice", "workos_alice") == 1
    assert s.reassign_user("google_alice", "workos_alice") == 0  # nothing left to move
    assert s.reassign_user("workos_alice", "workos_alice") == 0  # no-op same id
    with pytest.raises(ValueError):
        s.reassign_user("", "workos_alice")


# --- BYOK reassign: keys still decrypt --------------------------------------


def _vault():
    store = InMemoryWrappedKeyStore()
    vault = EnvelopeKeyVault(store, FernetDataCipher(), LocalKekProvider(os.urandom(32)))
    return store, vault


def test_byok_reassign_preserves_decryptable_keys():
    store, vault = _vault()
    vault.store_key("google_alice", "openai", "sk-secret-123")
    vault.store_key("google_alice", "anthropic", "sk-ant-456")
    vault.store_key("google_bob", "openai", "sk-bob")

    moved = vault.reassign_user("google_alice", "workos_alice")
    assert moved == 2

    # Keys decrypt unchanged under the new id (no rewrap needed)...
    assert vault.get_key("workos_alice", "openai") == "sk-secret-123"
    assert vault.get_key("workos_alice", "anthropic") == "sk-ant-456"
    # ...and are gone from the old id; Bob untouched.
    assert vault.get_key("google_alice", "openai") is None
    assert vault.get_key("google_bob", "openai") == "sk-bob"


# --- migration utility ------------------------------------------------------


def test_migrate_identity_moves_metadata_and_byok(tmp_path):
    s = _store(tmp_path)
    import datetime

    s.upsert_session("s1", "google_alice", "S1", "m", None, datetime.datetime(2024, 1, 1))
    store, vault = _vault()
    vault.store_key("google_alice", "openai", "sk-x")

    res = migrate_identity(
        IdentityMapping("google_alice", "workos_alice", email="a@x.io"),
        metadata_store=s,
        key_store=vault,
    )
    assert res.ok and res.metadata_rows == 1 and res.byok_rows == 1
    assert res.total_rows == 2
    assert s.get_session("s1", user_id="workos_alice") is not None
    assert vault.get_key("workos_alice", "openai") == "sk-x"


def test_migrate_batch_isolates_failures(tmp_path):
    s = _store(tmp_path)
    import datetime

    s.upsert_session("s1", "google_alice", "S1", "m", None, datetime.datetime(2024, 1, 1))
    mappings = [
        IdentityMapping("google_alice", "workos_alice"),
        IdentityMapping("google_bad", "google_bad"),  # same id -> 0 moved, ok
    ]
    results = migrate_batch(mappings, metadata_store=s)
    assert results[0].ok and results[0].metadata_rows == 1
    assert results[1].ok and results[1].metadata_rows == 0


def test_migrate_dry_run_does_not_mutate(tmp_path):
    s = _store(tmp_path)
    import datetime

    s.upsert_session("s1", "google_alice", "S1", "m", None, datetime.datetime(2024, 1, 1))
    res = migrate_identity(
        IdentityMapping("google_alice", "workos_alice"),
        metadata_store=s,
        dry_run=True,
    )
    assert res.dry_run and res.metadata_rows == 0
    # Untouched: still under the old id.
    assert s.get_session("s1", user_id="google_alice") is not None
    assert s.get_session("s1", user_id="workos_alice") is None


def test_load_mappings_parses_and_validates():
    raw = '[{"old_user_id":"google_a","new_user_id":"workos_a","email":"a@x.io"}]'
    out = load_mappings(raw)
    assert out == [IdentityMapping("google_a", "workos_a", "a@x.io")]
    with pytest.raises(ValueError):
        load_mappings('[{"old_user_id":"google_a"}]')  # missing new_user_id
    with pytest.raises(ValueError):
        load_mappings('{"not":"a list"}')


# --- build_verifier: WorkOS preferred when configured -----------------------


def test_build_verifier_prefers_workos_when_configured():
    from dataclasses import dataclass

    @dataclass
    class S:
        google_oauth_client_id: str = "google-cid"
        workos_issuer: str = "iss"
        workos_jwks_url: str = "jwks"
        workos_audience: str = "aud"

        @property
        def workos_configured(self):
            return bool(self.workos_issuer and self.workos_jwks_url and self.workos_audience)

    v = A.build_verifier(S())
    assert isinstance(v, WorkOSVerifier)


def test_build_verifier_falls_back_to_google_without_workos():
    from dataclasses import dataclass

    from src.platform_engines.identity import GoogleOAuthVerifier

    @dataclass
    class S:
        google_oauth_client_id: str = "google-cid"
        workos_issuer: str = ""
        workos_jwks_url: str = ""
        workos_audience: str = ""

        @property
        def workos_configured(self):
            return False

    assert isinstance(A.build_verifier(S()), GoogleOAuthVerifier)
