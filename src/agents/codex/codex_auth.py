"""Codex account (ChatGPT) auth — SDK-native device-code login.

Uses the openai_codex SDK's programmatic device-code flow instead of spawning
`codex login` and scraping stdout:

    with Codex(CodexConfig(env={"CODEX_HOME": <per-user home>})) as codex:
        handle = codex.login_chatgpt_device_code()   # typed url + code, no scrape
        # show handle.verification_url + handle.user_code to the user
        result = handle.wait()                        # blocks until login lands
        # on success, auth.json is persisted under CODEX_HOME

Per-user: each user's login lives under a per-uid CODEX_HOME
(``<state_dir>/codex-account-auth/users/<uid>/auth.json``). The flow runs on a
daemon thread (``wait()`` blocks up to ~15 min); status() reports the url/code
while in progress and "connected" once auth.json exists.
"""
from __future__ import annotations

import os
import re
import shutil
import threading
from contextlib import suppress
from pathlib import Path
from typing import Any, Callable, Optional


class CodexAuthUnavailable(RuntimeError):
    """Raised when the device-code login could not be started."""


def _safe_component(value: Optional[str], fallback: str = "anonymous") -> str:
    raw = (value or fallback).strip() or fallback
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")
    return (safe or fallback)[:96]


def _mkdir_private(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    with suppress(OSError, NotImplementedError):
        path.chmod(0o700)


class _LoginJob:
    """One in-flight device-code login, driven on a daemon thread.

    ``login_chatgpt_device_code()`` returns immediately with the url + code; the
    thread stores those (unblocking ``start``) then calls ``handle.wait()`` which
    blocks until the user finishes in the browser and auth.json is written.
    """

    def __init__(self, home: Path, sqlite_home: Path,
                 sdk_factory: Optional[Callable[[str], Any]]):
        self.home = Path(home)
        self.sqlite_home = Path(sqlite_home)
        self._sdk_factory = sdk_factory
        self.verification_url: Optional[str] = None
        self.user_code: Optional[str] = None
        self.error: Optional[str] = None
        self.done = False
        self._handle: Any = None
        self._ready = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()
        # Let the flow produce the url + code before we report status.
        self._ready.wait(timeout=20)

    def _make_codex(self):
        if self._sdk_factory is not None:
            return self._sdk_factory(str(self.home))
        from openai_codex import Codex, CodexConfig  # lazy — self-host w/o codex never imports

        env = {
            "CODEX_HOME": str(self.home),
            "CODEX_SQLITE_HOME": str(self.sqlite_home),
            # Scrub other providers' keys so the login is unambiguously ChatGPT.
            "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "",
        }
        return Codex(CodexConfig(env=env))

    def _run(self) -> None:
        try:
            with self._make_codex() as codex:
                handle = codex.login_chatgpt_device_code()
                self._handle = handle
                self.verification_url = str(getattr(handle, "verification_url", "") or "") or None
                self.user_code = str(getattr(handle, "user_code", "") or "") or None
                self._ready.set()
                result = handle.wait()
                if not getattr(result, "success", False):
                    self.error = str(getattr(result, "error", "") or "Login was not completed.")
        except Exception as exc:  # noqa: BLE001 - surfaced via status()/start()
            self.error = str(exc)
        finally:
            self.done = True
            self._ready.set()

    def cancel(self) -> None:
        h = self._handle
        if h is not None:
            with suppress(Exception):
                h.cancel()

    @property
    def in_progress(self) -> bool:
        return self._ready.is_set() and not self.done and self.error is None


class CodexAccountAuthManager:
    """Start and track per-user ChatGPT device-code logins via the Codex SDK."""

    def __init__(self, state_dir: str, *, sdk_factory: Optional[Callable[[str], Any]] = None):
        self.state_dir = Path(state_dir).resolve()
        self._sdk_factory = sdk_factory  # injectable for tests
        self._jobs: dict[str, _LoginJob] = {}
        self._lock = threading.Lock()
        # SQLite/rollout scratch on local disk (never the durable auth home).
        self._local_sqlite = os.environ.get("SILICONCREW_CODEX_SQLITE_DIR", "/app/codex-sqlite")

    def auth_home(self, user_id: str) -> str:
        return str(self.state_dir / "codex-account-auth" / "users" / _safe_component(user_id))

    def auth_file(self, user_id: str) -> Path:
        return Path(self.auth_home(user_id)) / "auth.json"

    def is_connected(self, user_id: Optional[str]) -> bool:
        if not user_id:
            return False
        f = self.auth_file(user_id)
        return f.exists() and f.stat().st_size > 0

    def status(self, user_id: str) -> dict[str, Any]:
        job = self._jobs.get(user_id)
        connected = self.is_connected(user_id)
        # Prune a finished login job once its credential landed — its daemon
        # thread has exited, so keeping the entry only leaks. Errored jobs are
        # kept so status() still surfaces the error (replaced on the next start).
        if job is not None and job.done and connected:
            self._jobs.pop(user_id, None)
            job = None
        resp: dict[str, Any] = {
            "connected": connected, "in_progress": False, "login_url": None,
            "user_code": None, "message": "Connected" if connected else "Not connected",
        }
        if connected or job is None:
            return resp
        if job.error:
            resp.update({"message": f"Login failed: {job.error}", "error": job.error})
            return resp
        if not job.done:
            resp.update({
                "in_progress": True, "login_url": job.verification_url,
                "user_code": job.user_code, "message": "Waiting for browser/device login",
            })
        return resp

    def start_device_auth(self, user_id: str) -> dict[str, Any]:
        with self._lock:
            if self.is_connected(user_id):
                return self.status(user_id)
            existing = self._jobs.get(user_id)
            if existing is not None and existing.in_progress:
                return self.status(user_id)
            home = Path(self.auth_home(user_id))
            _mkdir_private(home)
            sqlite_home = Path(self._local_sqlite) / "account-auth" / _safe_component(user_id)
            _mkdir_private(sqlite_home)
            job = _LoginJob(home, sqlite_home, self._sdk_factory)
            self._jobs[user_id] = job
            job.start()
        if job.error and not job.verification_url:
            raise CodexAuthUnavailable(job.error)
        return self.status(user_id)

    def cancel(self, user_id: str) -> dict[str, Any]:
        job = self._jobs.pop(user_id, None)
        if job is not None:
            job.cancel()
        return self.status(user_id)

    def disconnect(self, user_id: str) -> dict[str, Any]:
        self.cancel(user_id)
        home = Path(self.auth_home(user_id))
        if home.exists():
            shutil.rmtree(home, ignore_errors=True)
        return self.status(user_id)
