# Standalone ORFS Runner Service — Wire Contract

A small, token-authed HTTP service that runs an ORFS synthesis job and returns
its artifacts. It exists so **any** client (including the Phase 1 frontend
branch) can drive a real synth **without importing the SiliconCrew backend** —
just speak this JSON-over-HTTP contract.

- Server core: `src/platform_engines/orfs_service.py` (`OrfsService` +
  `create_app(service, token)` Starlette app).
- Reference client: `src/platform_engines.orfs_runner.RemoteOrfsRunner`
  (implements the `OrfsRunner` interface; selectable via `ORFS_ENGINE=remote`).

## Auth

Every request: `Authorization: Bearer <ORFS_SERVICE_TOKEN>`. Missing/wrong token
→ `401 {"error":"unauthorized"}`. (If the server is started with an empty token,
auth is disabled — only for trusted/private networks.)

## A run dir is self-contained

The job's run directory is a pure function of its inputs: it contains everything
ORFS needs (`config.mk`, `inputs/`, `constraints.sdc`, …). The client sends it as
a **gzip tarball** (base64) whose entries are the run-dir's top-level files; the
server materializes it into its own scratch dir and runs ORFS there.

`volumes` are **run-dir-relative** `"<subdir>:<container_path>"` specs. The server
rebuilds absolute host paths against its own run dir and remembers `<subdir>` so
it can return exactly those as artifacts.

## Endpoints

### `POST /v1/jobs` — submit
Request body (JSON):
```json
{
  "command": "make DESIGN_CONFIG=/workspace/config.mk",
  "volumes": ["orfs_results:/OpenROAD-flow-scripts/flow/results",
              "orfs_logs:/OpenROAD-flow-scripts/flow/logs",
              "orfs_reports:/OpenROAD-flow-scripts/flow/reports"],
  "timeout": 1800,
  "inputs_tar_b64": "<base64 gzip tar of the run dir>"
}
```
`inputs_tar_b64` **or** `object_ref` (a key the server's object store can fetch,
for cloud deployments) is required. Response `200`:
```json
{ "job_id": "rorfs_ab12cd34ef56", "status": "queued" }
```
Errors: `400 {"error":"..."}` (missing command/inputs), `401`.

### `GET /v1/jobs/{job_id}` — poll
Response `200`:
```json
{
  "job_id": "rorfs_...",
  "status": "queued | running | succeeded | failed",
  "exit_code": 0,
  "stdout": "ORFS log tail...",
  "stderr": ""
}
```
`404` for an unknown `job_id`. Poll with backoff until `status` is `succeeded`
or `failed`.

### `GET /v1/jobs/{job_id}/artifacts` — fetch
Response `200` (only once terminal):
```json
{ "artifacts_tar_b64": "<base64 gzip tar of the result subdirs>" }
```
`409 {"error":"Job not finished."}` if still running. The client untars this
back into its **own** run dir, so downstream parsing sees the normal layout.

## Minimal external client (no SiliconCrew import)

```python
import base64, io, json, tarfile, time, urllib.request

def _post(url, body, token):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(req).read())

def tar_b64(run_dir):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for n in os.listdir(run_dir): t.add(os.path.join(run_dir, n), arcname=n)
    return base64.b64encode(buf.getvalue()).decode()

job = _post(f"{URL}/v1/jobs", {"command": CMD, "volumes": VOLS,
                               "timeout": 1800, "inputs_tar_b64": tar_b64(run_dir)}, TOKEN)
# poll GET /v1/jobs/{job[job_id]} until status in {succeeded, failed},
# then GET .../artifacts and untar artifacts_tar_b64 into run_dir.
```

## Deploy

The service wraps any `OrfsRunner` — typically `LocalDockerOrfsRunner` on a host
with Docker + the ORFS image, or `CloudJobOrfsRunner`. Run it behind the bearer
token on a private network / authenticated ingress. Determinism, provenance,
run-dir isolation, and quotas are unchanged — this only swaps *where ORFS
executes*. Client selection is config-only: `ORFS_ENGINE=remote`,
`ORFS_SERVICE_URL`, `ORFS_SERVICE_TOKEN`.

## Sharing with Phase 1

`OrfsRequest` / `OrfsResult` / the `OrfsRunner` Protocol / `RemoteOrfsRunner` all
live in `src/platform_engines/orfs_runner.py` and depend only on the stdlib.
That module is the candidate to extract into a tiny shared package (e.g.
`siliconcrew-orfs-client`) so the Phase 1 branch can import the client directly
instead of reimplementing this contract.
