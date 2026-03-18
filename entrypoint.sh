#!/bin/bash
set -e

# Bootstrap standard-cell models if not already present
# These persist on the host via the /workspace bind mount
for platform in asap7 sky130hd; do
    cache="/workspace/_stdcells/${platform}/sim"
    if [ ! -d "$cache" ] || [ -z "$(ls -A "$cache" 2>/dev/null)" ]; then
        echo "Bootstrapping stdcells for ${platform}..."
        PYTHONPATH=/app python /app/scripts/bootstrap_stdcells.py \
            --workspace /workspace --platform "$platform" || \
            echo "Warning: stdcell bootstrap for ${platform} failed (non-fatal)"
    fi
done

# Pull ORFS image if Docker is available and image not present
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    if ! docker image inspect openroad/orfs:latest &>/dev/null 2>&1; then
        echo "Pulling openroad/orfs:latest (first run only)..."
        docker pull openroad/orfs:latest || \
            echo "Warning: ORFS image pull failed (synthesis won't work until pulled)"
    fi
fi

echo "Starting SiliconCrew..."

# Start backend, frontend, and MCP server
uvicorn api:app --host 0.0.0.0 --port 8000 &
cd /app/frontend && npm run dev -- -p 3000 &
cd /app && python mcp_server.py --transport sse --host 0.0.0.0 --port 8080 &
wait
