# Real synth for the Claude Code web agent — ORFS service on a VM

Goal: let the **Claude Code web agent** (no Docker in its container) run **real
synthesis**, so it can polish the synth/report/layout UI against real data.

How: run the ORFS service (`deploy/orfs_service_run.py`) once on a VM that has
Docker + the ORFS image, give it a public URL + token, and point the web
environment at it (`ORFS_ENGINE=remote`). The agent's synth calls then run on
the VM and return real reports/layouts.

```
Claude Code web agent  --HTTP(submit/poll/fetch)-->  VM: ORFS service
  (no Docker)            URL + bearer token              docker run openroad/orfs
```

---

## Part 1 — Stand up the VM (GCP example; $300 free credit)

You can do all of this from **Cloud Shell** (a terminal in your browser at
https://console.cloud.google.com — nothing to install locally).

### 1. Create a project + a VM
ORFS needs RAM/CPU — use at least 4 vCPU / 16 GB and a big disk (the image is
~6.5 GB).

```bash
# in Cloud Shell (set your own project id)
gcloud config set project YOUR_PROJECT_ID

gcloud compute instances create orfs-service \
  --zone=us-central1-a \
  --machine-type=e2-standard-4 \
  --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud \
  --boot-disk-size=60GB \
  --tags=orfs-service
```

### 2. Open the service port (8090), ideally only to known sources
```bash
# DEV-simple: open 8090 to the internet (token still required).
gcloud compute firewall-rules create allow-orfs-8090 \
  --allow=tcp:8090 --target-tags=orfs-service --source-ranges=0.0.0.0/0
# Better: restrict --source-ranges to the egress IPs your web env uses, if known.
```

### 3. SSH in (use the browser "SSH" button on the VM, or:)
```bash
gcloud compute ssh orfs-service --zone=us-central1-a
```

### 4. On the VM: install Docker + pull the ORFS image (slow, ~6.5 GB)
```bash
sudo apt-get update && sudo apt-get install -y docker.io git python3-pip
sudo usermod -aG docker $USER && newgrp docker     # use docker without sudo
docker pull openroad/orfs:latest
```

### 5. On the VM: get the code + deps, then run the service
```bash
git clone https://github.com/naman-ranka/siliconcrew.git
cd siliconcrew && git checkout claude/integration-p1p2
pip3 install fastapi "uvicorn[standard]" starlette pyyaml

export ORFS_SERVICE_TOKEN="$(openssl rand -hex 24)"   # <-- COPY THIS TOKEN
echo "TOKEN = $ORFS_SERVICE_TOKEN"
PYTHONPATH=. python3 deploy/orfs_service_run.py        # listens on :8090
```
For a long-lived service, run it under `tmux`/`systemd` instead of the foreground
(so it survives logout). A minimal systemd unit is at the bottom of this file.

### 6. Find the public URL + smoke-test it
```bash
# the VM's external IP (from Cloud Shell):
gcloud compute instances describe orfs-service --zone=us-central1-a \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
# → http://EXTERNAL_IP:8090
# quick auth check (wrong token must 401, missing job 404):
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer WRONG" \
  http://EXTERNAL_IP:8090/v1/jobs/none     # expect 401
```

> Security note: this is plain HTTP, so the token travels in clear. Fine for a
> short-lived dev box. For anything longer-lived, put Caddy/nginx in front for
> HTTPS, or restrict the firewall source ranges.

---

## Part 2 — Point the Claude Code web environment at it

In your Claude Code **web environment settings** (not in code):

1. **Network egress allowlist** — add the service host so the agent's container
   is allowed to reach it. ⚠️ Without this the agent silently can't connect
   (outbound is blocked by default).
   - allow host: `EXTERNAL_IP` (or your domain) on port `8090`.

2. **Environment variables** (applied to the agent's sessions):
   ```
   ORFS_ENGINE=remote
   ORFS_SERVICE_URL=http://EXTERNAL_IP:8090
   ORFS_SERVICE_TOKEN=<the token from step 5>
   ```

3. **Setup script** (so lint/sim and the app run in the agent's container):
   ```bash
   apt-get update && apt-get install -y iverilog
   pip install fastapi "uvicorn[standard]" aiosqlite python-dotenv pyyaml \
       vcdvcd httpx python-multipart cryptography
   # (+ langchain-core langgraph langgraph-checkpoint-sqlite if booting the full app)
   ```

That's it. In a session, the backend reads `ORFS_ENGINE=remote`, so
`get_orfs_runner()` returns the `RemoteOrfsRunner` → every synth call goes to the
VM → real report/layout comes back → the agent can polish that UI and find where
it breaks.

---

## How the agent verifies it works
- Lint/sim run locally (iverilog) as before.
- A synth from the workbench (or `POST /api/workspace/{id}/synthesize`) now
  produces a real run with PPA/timing + a layout — the `RemoteOrfsRunner` tars
  the run dir to the VM, ORFS runs there, artifacts come back.
- The synth/report/layout viewers now have **real data** to polish against.

## Cost / lifecycle
- e2-standard-4 ≈ a few $/day while running. **Stop the VM when not in use**:
  `gcloud compute instances stop orfs-service` (restart with `start`). The
  external IP may change on restart unless you reserve a static IP — if it does,
  update `ORFS_SERVICE_URL` + the egress allowlist.

## Cheaper/flakier alternative (no VM)
Run `deploy/orfs_service_run.py` on your **own laptop** (needs Docker + the ORFS
image) and expose it with `cloudflared tunnel --url http://localhost:8090`. Use
the tunnel URL as `ORFS_SERVICE_URL` and allowlist it. Works only while your
laptop + tunnel are up.

---

## Appendix — run the service under systemd (long-lived)
```ini
# /etc/systemd/system/orfs-service.service
[Unit]
Description=ORFS synthesis service
After=docker.service
Requires=docker.service

[Service]
WorkingDirectory=/home/USER/siliconcrew
Environment=PYTHONPATH=/home/USER/siliconcrew
Environment=ORFS_SERVICE_TOKEN=PASTE_TOKEN_HERE
ExecStart=/usr/bin/python3 deploy/orfs_service_run.py
Restart=on-failure
User=USER

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload && sudo systemctl enable --now orfs-service
sudo journalctl -u orfs-service -f      # logs
```
