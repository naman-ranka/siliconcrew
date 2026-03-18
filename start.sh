#!/bin/bash
# SiliconCrew Docker Startup Script
# Interactive setup with sensible defaults

set -e

DEFAULT_WORKSPACE="$(cd "$(dirname "$0")" && pwd)/workspace"
DEFAULT_DATA_DIR="$HOME/.siliconcrew"
DEFAULT_PORT_FRONTEND=3000
DEFAULT_PORT_BACKEND=8000

echo "=== SiliconCrew Docker Setup ==="
echo ""

# Workspace path
read -p "Workspace path [$DEFAULT_WORKSPACE]: " HOST_WORKSPACE
HOST_WORKSPACE="${HOST_WORKSPACE:-$DEFAULT_WORKSPACE}"

# Data directory (SQLite DB, session metadata)
read -p "Data directory [$DEFAULT_DATA_DIR]: " HOST_DATA_DIR
HOST_DATA_DIR="${HOST_DATA_DIR:-$DEFAULT_DATA_DIR}"

# Frontend port
read -p "Frontend port [$DEFAULT_PORT_FRONTEND]: " PORT_FRONTEND
PORT_FRONTEND="${PORT_FRONTEND:-$DEFAULT_PORT_FRONTEND}"

# Backend port
read -p "Backend port [$DEFAULT_PORT_BACKEND]: " PORT_BACKEND
PORT_BACKEND="${PORT_BACKEND:-$DEFAULT_PORT_BACKEND}"

# Check .env.docker
if [ ! -f .env.docker ]; then
    echo ""
    echo "No .env.docker found. Creating from .env.example..."
    if [ -f .env.example ]; then
        cp .env.example .env.docker
        echo "Edit .env.docker with your API keys, then re-run this script."
        exit 1
    else
        echo "No .env.example found either. Create .env.docker with your API keys:"
        echo "  GOOGLE_API_KEY=your_key"
        echo "  DEFAULT_MODEL=gemini-3-flash-preview"
        exit 1
    fi
fi

echo ""
echo "Starting with:"
echo "  Workspace:    $HOST_WORKSPACE"
echo "  Data dir:     $HOST_DATA_DIR"
echo "  Frontend:     http://localhost:$PORT_FRONTEND"
echo "  Backend:      http://localhost:$PORT_BACKEND"
echo ""

mkdir -p "$HOST_WORKSPACE" "$HOST_DATA_DIR"

export HOST_WORKSPACE
export HOST_DATA_DIR
export PORT_FRONTEND
export PORT_BACKEND

docker compose up -d --build

echo ""
echo "Ready! Open http://localhost:$PORT_FRONTEND"
