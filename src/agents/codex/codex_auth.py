"""Codex account (ChatGPT) device-auth — per-user `codex login --device-auth`.

Ported from the reference (plans/codex-engine-reference.md §4). Spawns the Codex
CLI device-auth flow, scrapes stdout for the login URL + user code, and reports
status. Credentials cache as `auth.json` under a per-user CODEX_HOME; API
responses expose only status/URL/code, never the credential.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_URL_RE = re.compile(r"https?://[^\s)>\]]+")


def _discover_codex_command() -> str:
    """Locate the codex CLI. It ships inside the ``codex_cli_bin`` package (not on
    PATH), so bare ``codex`` fails in the container — resolve the real binary."""
    import shutil

    found = shutil.which("codex")
    if found:
        return found
    try:
        import codex_cli_bin  # type: ignore

        cand = os.path.join(os.path.dirname(codex_cli_bin.__file__), "bin", "codex")
        if os.path.exists(cand):
            return cand
    except Exception:
        pass
    return "codex"
_CODE_RE = re.compile(r"(?:user[_ ]?code|code)[^A-Z0-9]*([A-Z0-9]{4,}(?:-[A-Z0-9]{4,})*)", re.IGNORECASE)
_STANDALONE_CODE_RE = re.compile(r"\b([A-Z0-9]{4,}(?:-[A-Z0-9]{4,})+)\b")


class CodexAuthUnavailable(RuntimeError):
    """Raised when the Codex CLI/device-auth flow cannot be started."""


def _safe_component(value: Optional[str], fallback: str = "anonymous") -> str:
    raw = (value or fallback).strip() or fallback
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")
    return (safe or fallback)[:96]


def _mkdir_private(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    with suppress(OSError, NotImplementedError):
        path.chmod(0o700)


def _write_auth_config(home: Path) -> None:
    _mkdir_private(home)
    config = home / "config.toml"
    if not config.exists():
        config.write_text('cli_auth_credentials_store = "file"\n', encoding="utf-8")
    with suppress(OSError, NotImplementedError):
        config.chmod(0o600)


def _split_command(command: str) -> list[str]:
    import shlex
    return shlex.split(command, posix=os.name != "nt") or ["codex"]


def _tail(lines: list[str], limit: int = 20) -> str:
    return "\n".join(lines[-limit:])


@dataclass
class _DeviceAuthJob:
    process: Any
    home: Path
    lines: list[str] = field(default_factory=list)
    login_url: Optional[str] = None
    user_code: Optional[str] = None
    error: Optional[str] = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def append_line(self, line: str) -> None:
        line = line.rstrip()
        if not line:
            return
        with self.lock:
            self.lines.append(line)
            self.lines[:] = self.lines[-100:]
            self._parse_line(line)

    def _parse_line(self, line: str) -> None:
        # The CLI colorizes the URL/code with ANSI escapes — strip them or the
        # scraped URL/code would carry trailing "\x1b[0m" garbage.
        line = _ANSI_RE.sub("", line)
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            for key in ("verification_uri_complete", "verification_uri", "url", "login_url"):
                if payload.get(key):
                    self.login_url = str(payload[key])
                    break
            for key in ("user_code", "code"):
                if payload.get(key):
                    self.user_code = str(payload[key])
                    break
        url_match = _URL_RE.search(line)
        if url_match:
            self.login_url = url_match.group(0).rstrip(".,")
        code_match = _CODE_RE.search(line) or _STANDALONE_CODE_RE.search(line)
        if code_match:
            self.user_code = code_match.group(1).strip().rstrip(".,")

    def poll(self) -> Optional[int]:
        poll = getattr(self.process, "poll", None)
        return poll() if callable(poll) else None

    def terminate(self) -> None:
        terminate = getattr(self.process, "terminate", None)
        if callable(terminate):
            terminate()


class CodexAccountAuthManager:
    """Start and track per-user `codex login --device-auth` sessions."""

    def __init__(self, state_dir: str, *, command: Optional[str] = None,
                 process_factory: Optional[Callable[..., Any]] = None):
        self.state_dir = Path(state_dir).resolve()
        self.command = command or os.environ.get("CODEX_LOGIN_COMMAND") or _discover_codex_command()
        self.process_factory = process_factory or subprocess.Popen
        self._jobs: dict[str, _DeviceAuthJob] = {}
        self._lock = threading.Lock()

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
        response: dict[str, Any] = {
            "connected": connected, "in_progress": False, "login_url": None,
            "user_code": None, "message": "Connected" if connected else "Not connected",
        }
        if job is None:
            return response
        exit_code = job.poll()
        with job.lock:
            response.update({"login_url": job.login_url, "user_code": job.user_code, "output_tail": _tail(job.lines)})
            if job.error:
                response["error"] = job.error
        if connected:
            response.update({"in_progress": False, "message": "Connected"})
            return response
        if exit_code is None:
            response.update({"in_progress": True, "message": "Waiting for browser/device login"})
            return response
        response.update({"in_progress": False, "exit_code": exit_code,
                         "message": "Login failed or was cancelled before credentials were written."})
        return response

    def start_device_auth(self, user_id: str) -> dict[str, Any]:
        with self._lock:
            if self.is_connected(user_id):
                return self.status(user_id)
            existing = self._jobs.get(user_id)
            if existing is not None and existing.poll() is None:
                return self.status(user_id)
            home = Path(self.auth_home(user_id))
            _write_auth_config(home)
            args = [*_split_command(self.command), "login", "--device-auth"]
            env = os.environ.copy()
            for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "CODEX_ACCESS_TOKEN"):
                env.pop(key, None)
            env.update({"CODEX_HOME": str(home), "CODEX_SQLITE_HOME": str(home)})
            startupinfo = None
            if os.name == "nt" and hasattr(subprocess, "STARTUPINFO"):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            try:
                process = self.process_factory(
                    args, cwd=str(home), env=env, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                    startupinfo=startupinfo)
            except FileNotFoundError as exc:
                raise CodexAuthUnavailable("Codex CLI was not found. Set CODEX_LOGIN_COMMAND or install Codex.") from exc
            except Exception as exc:  # noqa: BLE001 - endpoint returns structured error
                raise CodexAuthUnavailable(f"Could not start Codex login: {exc}") from exc
            job = _DeviceAuthJob(process=process, home=home)
            self._jobs[user_id] = job
            threading.Thread(target=self._read_output, args=(user_id, job), daemon=True).start()
        return self.status(user_id)

    def cancel(self, user_id: str) -> dict[str, Any]:
        job = self._jobs.pop(user_id, None)
        if job is not None and job.poll() is None:
            job.terminate()
        return self.status(user_id)

    def disconnect(self, user_id: str) -> dict[str, Any]:
        self.cancel(user_id)
        home = Path(self.auth_home(user_id))
        if home.exists():
            shutil.rmtree(home)
        return self.status(user_id)

    def _read_output(self, user_id: str, job: _DeviceAuthJob) -> None:
        stream = getattr(job.process, "stdout", None)
        if stream is None:
            return
        try:
            for line in stream:
                job.append_line(str(line))
        except Exception as exc:  # noqa: BLE001 - diagnostic only
            with job.lock:
                job.error = str(exc)
