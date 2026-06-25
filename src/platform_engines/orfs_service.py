"""Standalone, token-authed ORFS runner service (Phase 2 I7).

Exposes any :class:`~src.platform_engines.orfs_runner.OrfsRunner` over a tiny
HTTP contract so an **external** client (e.g. the Phase 1 branch) can submit a
synth job, poll it, and fetch artifacts WITHOUT importing this codebase. The
wire contract is documented in ``deploy/ORFS_SERVICE.md``.

This module is the framework-free *core* (``OrfsService``) plus a thin Starlette
app factory. The core takes/returns plain JSON-serializable dicts — exactly the
wire payloads — so it unit-tests against a loopback transport with no socket and
no Docker (inject a fake/mock OrfsRunner).

Inputs may arrive as a base64 gzip tarball of the run dir, or (in cloud) as an
object-storage reference the service downloads. Artifacts are returned as a
base64 gzip tarball of the run-dir-relative output subdirs.
"""
from __future__ import annotations

import os
import shutil
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Dict, List, Optional

# Contract + tar helpers come from the shareable stdlib-only client package and
# are re-exported here so existing imports (orfs_service.tar_dir_b64, ...) work.
from src.orfs_client import OrfsRequest, OrfsResult, tar_dir_b64, untar_b64_into  # noqa: F401


class ServiceError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# ---------------------------------------------------------------------------
# Service core
# ---------------------------------------------------------------------------


class OrfsService:
    """Manage submit -> run (via an OrfsRunner) -> poll -> artifacts."""

    def __init__(self, runner, scratch_dir: str, object_store=None, executor=None,
                 job_ttl_seconds: float = 3600.0, clock=time.time):
        self._runner = runner
        self._scratch = scratch_dir
        self._store = object_store  # optional ObjectStore for object_ref inputs
        self._executor = executor or ThreadPoolExecutor(max_workers=4)
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        # Bound the in-memory job map: finished jobs older than the TTL are
        # evicted (and their scratch dirs removed) on the next operation, so a
        # long-running service doesn't leak memory/disk. ttl<=0 disables GC.
        self._job_ttl = job_ttl_seconds
        self._clock = clock
        os.makedirs(self._scratch, exist_ok=True)

    # -- wire operations (plain dicts in/out) --------------------------------

    def submit(self, payload: dict) -> dict:
        self._gc()
        command = payload.get("command")
        if not command:
            raise ServiceError(400, "Missing 'command'.")
        volumes_rel: List[str] = payload.get("volumes", []) or []
        timeout = int(payload.get("timeout", 3600))

        job_id = f"rorfs_{uuid.uuid4().hex[:12]}"
        run_dir = os.path.join(self._scratch, job_id)
        os.makedirs(run_dir, exist_ok=True)

        # Materialize inputs: inline tarball or an object-storage reference.
        if payload.get("inputs_tar_b64"):
            untar_b64_into(payload["inputs_tar_b64"], run_dir)
        elif payload.get("object_ref"):
            if self._store is None:
                raise ServiceError(400, "object_ref given but service has no object store.")
            self._store.get_tree(payload["object_ref"], run_dir)
        else:
            raise ServiceError(400, "Provide 'inputs_tar_b64' or 'object_ref'.")

        # Rebuild absolute volume specs against THIS host's run_dir; remember the
        # run-dir-relative subdirs so we can tar exactly those as artifacts.
        abs_volumes, result_subdirs = [], []
        for spec in volumes_rel:
            rel, _, container = spec.partition(":")
            host = os.path.join(run_dir, rel)
            os.makedirs(host, exist_ok=True)
            abs_volumes.append(f"{host}:{container}" if container else host)
            result_subdirs.append(rel)

        req = OrfsRequest(run_dir=run_dir, command=command, volumes=abs_volumes, timeout=timeout)
        future = self._executor.submit(self._runner.run, req)
        with self._lock:
            self._jobs[job_id] = {
                "future": future, "run_dir": run_dir, "subdirs": result_subdirs,
                "created_at": self._clock(), "finished_at": None,
            }
        return {"job_id": job_id, "status": "queued"}

    def status(self, job_id: str) -> dict:
        job = self._job(job_id)
        future: Future = job["future"]
        if not future.done():
            state = "running" if future.running() else "queued"
            return {"job_id": job_id, "status": state, "exit_code": None, "stdout": "", "stderr": ""}
        # Stamp the terminal time once, so TTL eviction can age the job out.
        if job.get("finished_at") is None:
            with self._lock:
                job["finished_at"] = self._clock()
        try:
            result: OrfsResult = future.result()
        except Exception as exc:  # noqa: BLE001
            return {"job_id": job_id, "status": "failed", "exit_code": None, "stdout": "", "stderr": str(exc)}
        return {
            "job_id": job_id,
            "status": "succeeded" if result.success else "failed",
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def artifacts(self, job_id: str) -> dict:
        job = self._job(job_id)
        future: Future = job["future"]
        if not future.done():
            raise ServiceError(409, "Job not finished.")
        # Tar exactly the declared result subdirs (fall back to whole run dir).
        subdirs = job["subdirs"] or None
        return {"artifacts_tar_b64": tar_dir_b64(job["run_dir"], subdirs)}

    def _job(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise ServiceError(404, f"Unknown job '{job_id}'.")
        return job

    def _gc(self) -> None:
        """Evict finished jobs older than the TTL and remove their scratch dirs."""
        if self._job_ttl is None or self._job_ttl <= 0:
            return
        now = self._clock()
        evict = []
        with self._lock:
            for jid, job in list(self._jobs.items()):
                fut: Future = job["future"]
                finished = job.get("finished_at")
                # Opportunistically stamp jobs that finished but were never polled.
                if finished is None and fut.done():
                    job["finished_at"] = finished = now
                if finished is not None and (now - finished) > self._job_ttl:
                    evict.append((jid, job["run_dir"]))
                    del self._jobs[jid]
        for _jid, run_dir in evict:
            shutil.rmtree(run_dir, ignore_errors=True)

    def gc_now(self) -> int:
        """Force a GC pass (test/ops hook). Returns the post-GC job count."""
        self._gc()
        with self._lock:
            return len(self._jobs)


# ---------------------------------------------------------------------------
# Thin HTTP app (Starlette) — deploy-time; the core above is what tests drive.
# ---------------------------------------------------------------------------


def create_app(service: OrfsService, token: str):
    """Build a Starlette ASGI app exposing the wire contract with bearer auth."""
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    def _authed(request) -> bool:
        if not token:
            return True
        header = request.headers.get("authorization", "")
        return header == f"Bearer {token}"

    async def submit_job(request):
        if not _authed(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        payload = await request.json()
        try:
            return JSONResponse(service.submit(payload))
        except ServiceError as e:
            return JSONResponse({"error": e.message}, status_code=e.status)

    async def get_status(request):
        if not _authed(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        try:
            return JSONResponse(service.status(request.path_params["job_id"]))
        except ServiceError as e:
            return JSONResponse({"error": e.message}, status_code=e.status)

    async def get_artifacts(request):
        if not _authed(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        try:
            return JSONResponse(service.artifacts(request.path_params["job_id"]))
        except ServiceError as e:
            return JSONResponse({"error": e.message}, status_code=e.status)

    return Starlette(routes=[
        Route("/v1/jobs", submit_job, methods=["POST"]),
        Route("/v1/jobs/{job_id}", get_status, methods=["GET"]),
        Route("/v1/jobs/{job_id}/artifacts", get_artifacts, methods=["GET"]),
    ])
