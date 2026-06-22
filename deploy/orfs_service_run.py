"""Run the ORFS synthesis service on a Docker-capable host (e.g. a VM).

This is the "Path B" server: it exposes the submit/status/artifacts HTTP
contract (see deploy/ORFS_SERVICE.md) and runs real synthesis via the existing
``LocalDockerOrfsRunner`` (which shells ``docker run openroad/orfs``). Run it as
a plain process on a box that has Docker + the ORFS image, so it can reach the
host Docker daemon directly.

The Claude Code web agent (which has no Docker) then sets:
    ORFS_ENGINE=remote
    ORFS_SERVICE_URL=http://<this-host>:<port>
    ORFS_SERVICE_TOKEN=<same token as below>
and its synthesis calls are routed here.

Env vars:
    ORFS_SERVICE_TOKEN  bearer token clients must send (REQUIRED; empty = open)
    ORFS_IMAGE          ORFS docker image (default openroad/orfs:latest)
    ORFS_SCRATCH        scratch dir for staged run inputs (default /tmp/orfs-service)
    PORT                listen port (default 8090)

Run (from the repo root):
    PYTHONPATH=. python deploy/orfs_service_run.py
"""
import os

import uvicorn

from src.platform_engines.orfs_service import OrfsService, create_app
from src.platform_engines.orfs_runner import LocalDockerOrfsRunner


def build_app():
    token = os.environ.get("ORFS_SERVICE_TOKEN", "")
    if not token:
        print("WARNING: ORFS_SERVICE_TOKEN is empty — the service is UNAUTHENTICATED.")
    runner = LocalDockerOrfsRunner(image=os.environ.get("ORFS_IMAGE", "openroad/orfs:latest"))
    service = OrfsService(runner, scratch_dir=os.environ.get("ORFS_SCRATCH", "/tmp/orfs-service"))
    return create_app(service, token=token)


app = build_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8090")))
