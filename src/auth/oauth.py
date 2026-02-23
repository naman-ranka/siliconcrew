import os
import httpx
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from urllib.parse import urlencode

class OAuthProvider(ABC):
    @abstractmethod
    def get_auth_url(
        self,
        redirect_uri: str,
        state: Optional[str] = None,
        code_challenge: Optional[str] = None,
        code_challenge_method: str = "S256",
    ) -> str:
        pass

    @abstractmethod
    async def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: Optional[str] = None
    ) -> Dict[str, Any]:
        """Returns dict with access_token, refresh_token, expires_in (seconds), meta"""
        pass

    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """Returns dict with access_token, expires_in, and optional new refresh_token"""
        pass

class GoogleOAuthProvider(OAuthProvider):
    def __init__(self):
        self.client_id = os.environ.get("GOOGLE_CLIENT_ID")
        self.client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
        self.auth_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
        self.token_endpoint = "https://oauth2.googleapis.com/token"

    def get_auth_url(
        self,
        redirect_uri: str,
        state: Optional[str] = None,
        code_challenge: Optional[str] = None,
        code_challenge_method: str = "S256",
    ) -> str:
        if not self.client_id:
            raise ValueError("GOOGLE_CLIENT_ID not set")

        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/generative-language",
            "access_type": "offline",
            "prompt": "consent",
        }
        if state:
            params["state"] = state
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method

        return f"{self.auth_endpoint}?{urlencode(params)}"

    async def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: Optional[str] = None
    ) -> Dict[str, Any]:
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            payload["code_verifier"] = code_verifier

        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_endpoint, data=payload)
            resp.raise_for_status()
            data = resp.json()

            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in", 3600),
                "meta": {"scope": data.get("scope")}
            }

    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_endpoint, data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            })
            resp.raise_for_status()
            data = resp.json()

            return {
                "access_token": data["access_token"],
                "expires_in": data.get("expires_in", 3600),
                # Google sometimes rotates refresh tokens
                "refresh_token": data.get("refresh_token")
            }

class OpenAICodexOAuthProvider(OAuthProvider):
    """
    OpenAI Codex OAuth provider.
    Endpoint URLs are configurable via env vars to avoid hardcoding unstable URLs.
    """

    def __init__(self):
        self.client_id = os.environ.get("OPENAI_CODEX_CLIENT_ID")
        self.client_secret = os.environ.get("OPENAI_CODEX_CLIENT_SECRET")
        self.auth_endpoint = os.environ.get("OPENAI_CODEX_AUTH_ENDPOINT")
        self.token_endpoint = os.environ.get("OPENAI_CODEX_TOKEN_ENDPOINT")
        self.scope = os.environ.get(
            "OPENAI_CODEX_SCOPE", "openid profile email offline_access"
        )

    def _validate_config(self) -> None:
        missing = []
        if not self.client_id:
            missing.append("OPENAI_CODEX_CLIENT_ID")
        if not self.client_secret:
            missing.append("OPENAI_CODEX_CLIENT_SECRET")
        if not self.auth_endpoint:
            missing.append("OPENAI_CODEX_AUTH_ENDPOINT")
        if not self.token_endpoint:
            missing.append("OPENAI_CODEX_TOKEN_ENDPOINT")
        if missing:
            raise ValueError(
                "OpenAI Codex OAuth is not configured. Missing env vars: "
                + ", ".join(missing)
            )

    def get_auth_url(
        self,
        redirect_uri: str,
        state: Optional[str] = None,
        code_challenge: Optional[str] = None,
        code_challenge_method: str = "S256",
    ) -> str:
        self._validate_config()
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.scope,
        }
        if state:
            params["state"] = state
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method
        return f"{self.auth_endpoint}?{urlencode(params)}"

    async def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: Optional[str] = None
    ) -> Dict[str, Any]:
        self._validate_config()
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            payload["code_verifier"] = code_verifier

        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_endpoint, data=payload)
            resp.raise_for_status()
            data = resp.json()
            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in", 3600),
                "meta": {"scope": data.get("scope", self.scope)},
            }

    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        self._validate_config()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.token_endpoint,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "access_token": data["access_token"],
                "expires_in": data.get("expires_in", 3600),
                "refresh_token": data.get("refresh_token"),
            }


class OAuthFactory:
    _providers = {
        "google": GoogleOAuthProvider,
        "openai-codex": OpenAICodexOAuthProvider,
    }

    @classmethod
    def get_provider(cls, name: str) -> OAuthProvider:
        provider_cls = cls._providers.get(name.lower())
        if not provider_cls:
            raise ValueError(f"Provider {name} not supported")
        return provider_cls()
