#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# MCP Forge — Local Model Server launcher for macOS
#
# What this script does (automatically):
#   1. Checks for Python 3.9+; installs it via Homebrew if missing
#   2. Creates a venv at  <project-root>/venv-model-server/  (once)
#   3. Installs torch (with MPS support), transformers, accelerate,
#      fastapi, and uvicorn into the venv  (once)
#   4. Runs scripts/run_model_local.py  inside the venv
#
# Run from your project root:
#   bash scripts/start_model_server.sh
#
# Optional env overrides:
#   LOCAL_MODEL=Qwen/Qwen2.5-Coder-7B-Instruct bash scripts/start_model_server.sh
#   LOCAL_MODEL_PORT=8005 bash scripts/start_model_server.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/venv-model-server"
PYTHON_SCRIPT="$SCRIPT_DIR/run_model_local.py"

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${CYAN}[model-server]${NC} $*"; }
success() { echo -e "${GREEN}[model-server]${NC} $*"; }
warn()    { echo -e "${YELLOW}[model-server]${NC} $*"; }
error()   { echo -e "${RED}[model-server] ERROR:${NC} $*" >&2; }

# ── macOS check ───────────────────────────────────────────────────────────────
if [[ "$(uname)" != "Darwin" ]]; then
  warn "This script is designed for macOS."
  warn "On Linux/Windows with NVIDIA GPU, the model loads directly inside Docker."
  warn "You can still continue — it will use CPU if no GPU is found."
  read -r -p "Continue anyway? [y/N] " confirm
  [[ "$confirm" =~ ^[Yy]$ ]] || exit 0
fi

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║        MCP Forge — Local Model Server Setup          ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Step 1: Ensure Python 3.9+ ────────────────────────────────────────────────
info "Step 1/3 — Checking Python…"

PYTHON_CMD=""
for cmd in python3.12 python3.11 python3.10 python3.9 python3; do
  if command -v "$cmd" &>/dev/null; then
    ver=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    major="${ver%%.*}"; minor="${ver##*.}"
    if [[ "$major" -ge 3 && "$minor" -ge 9 ]]; then
      PYTHON_CMD="$cmd"
      success "Found $cmd ($ver)"
      break
    fi
  fi
done

if [[ -z "$PYTHON_CMD" ]]; then
  warn "Python 3.9+ not found. Installing via Homebrew…"

  if ! command -v brew &>/dev/null; then
    info "Homebrew not found — installing Homebrew first…"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add Homebrew to PATH for Apple Silicon Macs
    if [[ -f /opt/homebrew/bin/brew ]]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
  fi

  brew install python@3.12
  # Homebrew Python is not on PATH by default on some installs
  for p in /opt/homebrew/bin /usr/local/bin; do
    [[ -x "$p/python3.12" ]] && PYTHON_CMD="$p/python3.12" && break
  done
  [[ -z "$PYTHON_CMD" ]] && PYTHON_CMD="python3.12"
  success "Python installed: $($PYTHON_CMD --version)"
fi

# ── Step 2: Create / reuse venv ───────────────────────────────────────────────
info "Step 2/3 — Setting up virtual environment at venv-model-server/…"

if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_CMD" -m venv "$VENV_DIR"
  success "Virtual environment created."
else
  success "Reusing existing virtual environment."
fi

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# ── Step 3: Install / upgrade dependencies ────────────────────────────────────
info "Step 3/3 — Installing / updating dependencies (first run may take a few minutes)…"

"$VENV_PIP" install --quiet --upgrade pip

# Check if packages are already installed (skip heavy reinstall on subsequent runs)
if "$VENV_PYTHON" -c "import torch, transformers, fastapi, uvicorn" 2>/dev/null; then
  success "All dependencies already installed — skipping."
else
  info "Installing PyTorch (MPS-enabled), transformers, fastapi, uvicorn…"
  # Standard pip install — macOS torch wheel includes MPS support out of the box
  "$VENV_PIP" install --quiet \
    torch \
    torchvision \
    "transformers>=4.45.0" \
    "accelerate>=0.34.0" \
    "fastapi>=0.110.0" \
    "uvicorn[standard]>=0.27.0" \
    "httpx>=0.27.0"
  success "Dependencies installed."
fi

# ── Launch ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
success "Launching model server…"
echo ""
echo -e "  Model : ${YELLOW}${LOCAL_MODEL:-auto-selected based on your RAM}${NC}"
echo -e "  Port  : ${YELLOW}${LOCAL_MODEL_PORT:-8005}${NC}"
echo -e "  Cache : ${YELLOW}$PROJECT_ROOT/cache/huggingface/${NC} (shared with Docker)"
echo ""
echo -e "  ${CYAN}Once the model says 'Listening on 0.0.0.0:8005':${NC}"
echo -e "  ${CYAN}→  Go back to the MCP Forge Config page${NC}"
echo -e "  ${CYAN}→  Click  'Set LOCAL_MODEL_HOST & save'${NC}"
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Press  ${RED}Ctrl+C${NC}  to stop the model server."
echo ""

# On macOS, prevent the system from sleeping while the model downloads / runs.
# caffeinate is a built-in macOS tool — no install needed.
if [[ "$(uname)" == "Darwin" ]]; then
  exec caffeinate -i "$VENV_PYTHON" "$PYTHON_SCRIPT"
else
  exec "$VENV_PYTHON" "$PYTHON_SCRIPT"
fi
