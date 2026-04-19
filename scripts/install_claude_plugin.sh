#!/bin/bash
# =============================================================================
# MCP Forge — Claude Desktop Plugin Installer (macOS / Linux)
# Usage: bash scripts/install_claude_plugin.sh
# =============================================================================

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo ""
echo -e "  ${CYAN}MCP Forge — Claude Desktop Plugin Installer${NC}"
echo -e "  ${CYAN}============================================${NC}"
echo ""

# --- Step 1: Check Docker is running ---
echo -e "${YELLOW}[1/4] Checking Docker...${NC}"
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}  ERROR: Docker is not running. Start Docker Desktop first.${NC}"
    exit 1
fi
RUNNING=$(docker inspect --format='{{.State.Running}}' mcp_forge_app 2>/dev/null || echo "false")
if [ "$RUNNING" != "true" ]; then
    echo -e "${RED}  ERROR: mcp_forge_app container is not running.${NC}"
    echo -e "${RED}  Run 'docker compose up -d' first, then re-run this script.${NC}"
    exit 1
fi
echo -e "${GREEN}  Docker OK -- mcp_forge_app is running.${NC}"

# --- Step 2: Get auth token ---
echo -e "${YELLOW}[2/5] Fetching auth token from container...${NC}"
TOKEN=$(docker exec mcp_forge_app printenv MCP_AUTH_TOKEN)
if [ -z "$TOKEN" ]; then
    echo -e "${RED}  ERROR: Could not read MCP_AUTH_TOKEN from container.${NC}"
    exit 1
fi
echo -e "${GREEN}  Token fetched OK.${NC}"

# --- Step 3: Create venv + install dependencies ---
echo -e "${YELLOW}[3/5] Setting up Python virtual environment...${NC}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_PATH="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_PATH/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

# Find system python
SYS_PYTHON=$(command -v python3 || command -v python || true)
if [ -z "$SYS_PYTHON" ]; then
    echo -e "${RED}  ERROR: Python 3 not found. Install Python 3.10+ and retry.${NC}"
    exit 1
fi

if [ ! -f "$VENV_PYTHON" ]; then
    echo -e "${CYAN}  Creating .venv...${NC}"
    "$SYS_PYTHON" -m venv "$VENV_DIR"
fi
echo -e "${CYAN}  Installing dependencies into .venv (may take a minute)...${NC}"
"$VENV_PYTHON" -m pip install --upgrade pip --quiet
"$VENV_PYTHON" -m pip install -r "$PROJECT_PATH/requirements.txt" --quiet
echo -e "${GREEN}  Virtual environment ready.${NC}"

# --- Step 4: Write the config file ---
echo -e "${YELLOW}[4/5] Writing Claude Desktop config...${NC}"

# Detect OS and set config path
if [[ "$OSTYPE" == "darwin"* ]]; then
    CONFIG_DIR="$HOME/Library/Application Support/Claude"
    if [ ! -d "/Applications/Claude.app" ] && [ ! -d "$HOME/Applications/Claude.app" ]; then
        echo -e "${YELLOW}  WARNING: Claude.app not found in /Applications.${NC}"
        echo -e "${YELLOW}  Download from https://claude.ai/download and install it first.${NC}"
    fi
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/Claude"
else
    echo -e "${RED}  ERROR: Unsupported OS: $OSTYPE${NC}"
    exit 1
fi

mkdir -p "$CONFIG_DIR"
CONFIG_PATH="$CONFIG_DIR/claude_desktop_config.json"

cat > "$CONFIG_PATH" <<EOF
{
  "mcpServers": {
    "mcp-forge": {
      "command": "$VENV_PYTHON",
      "args": ["$PROJECT_PATH/mcp_server/server.py"],
      "env": {
        "PYTHONPATH": "$PROJECT_PATH",
        "APP_URL": "http://localhost:8000",
        "MCP_AUTH_TOKEN": "$TOKEN",
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
EOF

echo -e "${GREEN}  Config written to: $CONFIG_PATH${NC}"

# --- Step 5: Done ---
echo -e "${YELLOW}[5/5] Done!${NC}"
echo ""
echo -e "${CYAN}  Next steps:${NC}"
echo "  1. Fully QUIT Claude Desktop (menu bar → Quit)"
echo "  2. Reopen Claude Desktop"
echo "  3. Go to Settings → Developer — you should see 'mcp-forge' with a green dot"
echo "  4. Try asking: 'List all my MCP Forge projects'"
echo ""
