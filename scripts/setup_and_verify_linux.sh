#!/usr/bin/env bash
set -Eeuo pipefail

# SiliconCrew Linux bootstrap + verification script
# Target platform: Ubuntu/Debian (apt-based)
#
# What this script does:
# 1) Installs system dependencies (Python, Node, Icarus, Docker, build tools)
# 2) Sets up backend virtualenv + Python requirements
# 3) Sets up frontend npm dependencies
# 4) Bootstraps stdcell caches for asap7 + sky130hd
# 5) Pulls OpenROAD Docker image
# 6) Runs pytest + all tests/verify_*.py scripts
# 7) Prints a final pass/fail summary with log paths
#
# Usage:
#   bash scripts/setup_and_verify_linux.sh
#   bash scripts/setup_and_verify_linux.sh --skip-system-install
#   bash scripts/setup_and_verify_linux.sh --fast

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${REPO_ROOT}/.setup_logs/${TIMESTAMP}"
mkdir -p "${LOG_DIR}"

SKIP_SYSTEM_INSTALL=0
FAST_MODE=0
STRICT_MODE=1

declare -a STEP_NAMES=()
declare -a STEP_STATUSES=()
declare -a STEP_LOGS=()

PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

usage() {
  cat <<'EOF'
Usage: bash scripts/setup_and_verify_linux.sh [options]

Options:
  --skip-system-install   Skip apt-based package install step
  --fast                  Skip frontend build and verify_*.py scripts
  --non-strict            Exit 0 even if one or more steps fail
  -h, --help              Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-system-install) SKIP_SYSTEM_INSTALL=1 ;;
    --fast) FAST_MODE=1 ;;
    --non-strict) STRICT_MODE=0 ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 2
      ;;
  esac
  shift
done

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This script only supports Linux."
  exit 1
fi

SUDO=""
if [[ "${EUID}" -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  fi
fi

record_result() {
  local name="$1"
  local status="$2"
  local log="$3"

  STEP_NAMES+=("${name}")
  STEP_STATUSES+=("${status}")
  STEP_LOGS+=("${log}")

  case "${status}" in
    PASS) ((PASS_COUNT+=1)) ;;
    FAIL) ((FAIL_COUNT+=1)) ;;
    SKIP) ((SKIP_COUNT+=1)) ;;
  esac
}

run_step() {
  local name="$1"
  local cmd="$2"
  local log="${LOG_DIR}/$(echo "${name}" | tr ' /:' '___').log"

  echo
  echo "==> ${name}"
  echo "    cmd: ${cmd}"
  if bash -lc "${cmd}" >"${log}" 2>&1; then
    echo "    status: PASS"
    record_result "${name}" "PASS" "${log}"
    return 0
  else
    echo "    status: FAIL (see ${log})"
    record_result "${name}" "FAIL" "${log}"
    return 1
  fi
}

skip_step() {
  local name="$1"
  local reason="$2"
  local log="${LOG_DIR}/$(echo "${name}" | tr ' /:' '___').log"
  printf "%s\n" "${reason}" >"${log}"
  echo
  echo "==> ${name}"
  echo "    status: SKIP (${reason})"
  record_result "${name}" "SKIP" "${log}"
}

require_file() {
  local path="$1"
  if [[ ! -f "${path}" ]]; then
    echo "Required file missing: ${path}"
    exit 1
  fi
}

env_has_real_key() {
  local key="$1"
  local env_file="$2"
  local value
  value="$(grep -E "^${key}=" "${env_file}" | tail -n1 | cut -d'=' -f2- || true)"
  value="${value%\"}"
  value="${value#\"}"
  [[ -n "${value}" ]] || return 1
  [[ "${value}" != "your_google_key_here" ]] || return 1
  [[ "${value}" != "your_openai_key_here" ]] || return 1
  [[ "${value}" != "your_anthropic_key_here" ]] || return 1
  return 0
}

echo "Repository root: ${REPO_ROOT}"
echo "Log directory:   ${LOG_DIR}"

require_file "${REPO_ROOT}/requirements.txt"
require_file "${REPO_ROOT}/frontend/package.json"
require_file "${REPO_ROOT}/scripts/bootstrap_stdcells.py"

if [[ "${SKIP_SYSTEM_INSTALL}" -eq 1 ]]; then
  skip_step "Install system packages (apt)" "skipped by --skip-system-install"
else
  if ! command -v apt-get >/dev/null 2>&1; then
    run_step "Install system packages (apt)" "echo 'apt-get not found; only apt-based distros are supported by this script.'; exit 1" || true
  else
    run_step \
      "Install system packages (apt)" \
      "${SUDO} apt-get update && ${SUDO} apt-get install -y \
      python3 python3-venv python3-pip python3-dev \
      nodejs npm \
      iverilog \
      docker.io \
      git curl ca-certificates build-essential pkg-config" || true

    if command -v systemctl >/dev/null 2>&1; then
      run_step "Enable docker service" "${SUDO} systemctl enable --now docker" || true
    else
      skip_step "Enable docker service" "systemctl not available"
    fi
  fi
fi

run_step "Create Python virtualenv" "cd '${REPO_ROOT}' && python3 -m venv .venv" || true
run_step "Upgrade pip/setuptools/wheel" "cd '${REPO_ROOT}' && . .venv/bin/activate && python -m pip install --upgrade pip setuptools wheel" || true
run_step "Install Python requirements" "cd '${REPO_ROOT}' && . .venv/bin/activate && pip install -r requirements.txt" || true

if [[ ! -f "${REPO_ROOT}/.env" ]]; then
  run_step "Create .env from template" "cd '${REPO_ROOT}' && cp .env.example .env" || true
else
  skip_step "Create .env from template" ".env already exists"
fi

if [[ -f "${REPO_ROOT}/.env" ]]; then
  if env_has_real_key "GOOGLE_API_KEY" "${REPO_ROOT}/.env" || env_has_real_key "OPENAI_API_KEY" "${REPO_ROOT}/.env" || env_has_real_key "ANTHROPIC_API_KEY" "${REPO_ROOT}/.env"; then
    run_step "Validate LLM API key presence" "echo 'At least one provider key appears configured in .env'" || true
  else
    run_step "Validate LLM API key presence" "echo 'No real API key configured in .env (placeholders detected). Some tests may fail.'; exit 1" || true
  fi
else
  run_step "Validate LLM API key presence" "echo '.env missing'; exit 1" || true
fi

run_step "Install frontend dependencies" "cd '${REPO_ROOT}/frontend' && if [[ -f package-lock.json ]]; then npm ci; else npm install; fi" || true
run_step "Run frontend lint" "cd '${REPO_ROOT}/frontend' && npm run lint" || true

if [[ "${FAST_MODE}" -eq 1 ]]; then
  skip_step "Run frontend build" "skipped by --fast"
else
  run_step "Run frontend build" "cd '${REPO_ROOT}/frontend' && npm run build" || true
fi

run_step "Bootstrap stdcells (asap7)" "cd '${REPO_ROOT}' && . .venv/bin/activate && PYTHONPATH=. python scripts/bootstrap_stdcells.py --workspace workspace --platform asap7" || true
run_step "Bootstrap stdcells (sky130hd)" "cd '${REPO_ROOT}' && . .venv/bin/activate && PYTHONPATH=. python scripts/bootstrap_stdcells.py --workspace workspace --platform sky130hd" || true

DOCKER_CMD="docker"
if docker info >/dev/null 2>&1; then
  DOCKER_CMD="docker"
elif [[ -n "${SUDO}" ]] && ${SUDO} docker info >/dev/null 2>&1; then
  DOCKER_CMD="${SUDO} docker"
fi

run_step "Check docker daemon access" "${DOCKER_CMD} info >/dev/null" || true
run_step "Pull OpenROAD image" "${DOCKER_CMD} pull openroad/orfs:latest" || true

run_step "Run pytest suite" "cd '${REPO_ROOT}' && . .venv/bin/activate && PYTHONPATH=. pytest -q" || true

if [[ "${FAST_MODE}" -eq 1 ]]; then
  skip_step "Run verify_*.py scripts" "skipped by --fast"
else
  mapfile -t VERIFY_SCRIPTS < <(cd "${REPO_ROOT}" && find tests -maxdepth 1 -type f -name 'verify_*.py' | sort)
  if [[ "${#VERIFY_SCRIPTS[@]}" -eq 0 ]]; then
    skip_step "Run verify_*.py scripts" "no verify scripts found"
  else
    for script in "${VERIFY_SCRIPTS[@]}"; do
      run_step "Run $(basename "${script}")" "cd '${REPO_ROOT}' && . .venv/bin/activate && PYTHONPATH=. python '${script}'" || true
    done
  fi
fi

echo
echo "================ Setup & Test Summary ================"
printf "%-4s | %-45s | %-6s | %s\n" "No." "Step" "Status" "Log"
printf "%s\n" "-----------------------------------------------------------------------------------------------"
for i in "${!STEP_NAMES[@]}"; do
  idx=$((i + 1))
  printf "%-4s | %-45s | %-6s | %s\n" \
    "${idx}" \
    "${STEP_NAMES[$i]}" \
    "${STEP_STATUSES[$i]}" \
    "${STEP_LOGS[$i]}"
done
printf "%s\n" "-----------------------------------------------------------------------------------------------"
echo "PASS: ${PASS_COUNT}  FAIL: ${FAIL_COUNT}  SKIP: ${SKIP_COUNT}"
echo "Logs directory: ${LOG_DIR}"
echo "======================================================"

if [[ "${STRICT_MODE}" -eq 1 && "${FAIL_COUNT}" -gt 0 ]]; then
  exit 1
fi

exit 0
