#!/usr/bin/env bash
set -euo pipefail

# Start SiliconCrew without Docker Compose.
# Usage:
#   bash scripts/start_without_compose.sh
# Optional overrides:
#   PORT_FRONTEND=3001 PORT_BACKEND=8001 PORT_MCP=8081 HOST_WORKSPACE=/path HOST_DATA_DIR=/path bash scripts/start_without_compose.sh

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

HOST_WORKSPACE="${HOST_WORKSPACE:-$REPO_ROOT/workspace}"
HOST_DATA_DIR="${HOST_DATA_DIR:-$HOME/.siliconcrew}"
PORT_FRONTEND="${PORT_FRONTEND:-3000}"
PORT_BACKEND="${PORT_BACKEND:-8000}"
PORT_MCP="${PORT_MCP:-8080}"
CONTAINER_NAME="${CONTAINER_NAME:-siliconcrew}"
IMAGE_NAME="${IMAGE_NAME:-siliconcrew:latest}"

if [[ ! -f .env.docker ]]; then
  echo "Missing .env.docker"
  echo "Create it first: cp .env.example .env.docker && edit API keys"
  exit 1
fi

mkdir -p "$HOST_WORKSPACE" "$HOST_DATA_DIR"

echo "Building image: $IMAGE_NAME"
docker build -t "$IMAGE_NAME" .

echo "Removing old container (if any): $CONTAINER_NAME"
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

echo "Starting container: $CONTAINER_NAME"
docker run -d \
  --name "$CONTAINER_NAME" \
  -p "$PORT_FRONTEND":3000 \
  -p "$PORT_BACKEND":8000 \
  -p "$PORT_MCP":8080 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$HOST_WORKSPACE":/workspace \
  -v "$HOST_DATA_DIR":/root/.siliconcrew \
  --env-file .env.docker \
  -e RTL_WORKSPACE=/workspace \
  -e HOST_WORKSPACE="$HOST_WORKSPACE" \
  "$IMAGE_NAME"

echo
echo "SiliconCrew started."
echo "Frontend: http://localhost:$PORT_FRONTEND"
echo "Backend:  http://localhost:$PORT_BACKEND"
echo "MCP HTTP: http://localhost:$PORT_MCP/mcp"
echo "Logs:     docker logs -f $CONTAINER_NAME"
