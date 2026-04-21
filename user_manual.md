# MCP Forge — User Manual

> Complete guide to running MCP Forge and integrating it with Claude Desktop, Claude Code, Codex, and the `forge` CLI.

```bash
pip install mcp-forger   # install the forge CLI
```

---

## Table of Contents

1. [Run MCP Forge](#1-run-mcp-forge)
2. [Connect to Claude Desktop](#2-connect-to-claude-desktop)
3. [Connect to Claude Code](#3-connect-to-claude-code)
4. [Connect to Codex](#4-connect-to-codex)
5. [forge CLI](#5-forge-cli)
6. [Using a Local Folder as Source](#6-using-a-local-folder-as-source)
7. [Local HuggingFace Model (No API Key)](#7-local-huggingface-model-no-api-key)
8. [Configuration Reference](#8-configuration-reference)
9. [Resetting the Database](#9-resetting-the-database)
10. [Troubleshooting](#10-troubleshooting)
11. [Architecture](#11-architecture)

---

## 1. Run MCP Forge

### Requirements

| Tool | Notes |
|---|---|
| Docker + Docker Compose v24+ | Required |
| NVIDIA GPU | Optional — only for `LLM_PROVIDER=local` |
| Python 3.12+ | Optional — only for `forge` CLI or stdio plugin mode |

### Step 1 — Clone & configure

```bash
git clone https://github.com/coderXcode/mcp-forge.git
cd mcp-forge
cp .env.example .env
```

Open `.env` and set at minimum:

```env
LLM_PROVIDER=gemini          # or: anthropic | openai | local
GEMINI_API_KEY=your-key-here

# Change this — used to authenticate Claude Desktop / Claude Code / Codex
MCP_AUTH_TOKEN=change-me-to-something-secret
```

> **No API key?** Use `LLM_PROVIDER=gemini` — Gemini has a free tier at [aistudio.google.com](https://aistudio.google.com).

### Step 2 — Start

```bash
docker compose up -d
```

| Service | URL | Purpose |
|---|---|---|
| 🌐 Dashboard | http://localhost:8000 | Web UI — all operations |
| 🔌 MCP SSE endpoint | http://localhost:8001/sse | Claude Desktop / Claude Code / Codex |

### Step 3 — Verify

```bash
# Should return [] (empty project list)
curl http://localhost:8000/api/projects/

# Should emit: event: endpoint  (MCP server is up)
curl http://localhost:8001/sse
```

---

## 2. Connect to Claude Desktop

Claude Desktop runs the MCP server locally via **stdio** transport. The install scripts handle everything automatically.

### 🪟 Windows

Open **PowerShell** in the project folder:

```powershell
.\scripts\install_claude_plugin.ps1
```

### 🍎 macOS / 🐧 Linux

Open **Terminal** in the project folder:

```bash
bash scripts/install_claude_plugin.sh
```

Both scripts automatically:
1. Check Docker + `mcp_forge_app` is running
2. Pull `MCP_AUTH_TOKEN` from the container
3. Create the Claude config folder if it doesn't exist
4. Write `claude_desktop_config.json` with the correct path and token

Config file locations:

| OS | Path |
|---|---|
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

### After running the script

1. **Fully QUIT Claude Desktop** — right-click system tray / menu bar → **Quit** (just closing the window is not enough)
2. **Reopen Claude Desktop**
3. Go to **Settings → Developer** — you should see **mcp-forge** with a 🟢 green dot
4. Test it: *"List all my MCP Forge projects"*

### Manual config (stdio mode)

If you prefer to write the file yourself, get your token first:

```bash
docker exec mcp_forge_app printenv MCP_AUTH_TOKEN
```

Then create the config file at the path for your OS (see table above):

```json
{
  "mcpServers": {
    "mcp-forge": {
      "command": "C:/path/to/mcp-forge/.venv/Scripts/python.exe",
      "args": ["mcp_server/server.py"],
      "cwd": "C:/path/to/mcp-forge",
      "env": {
        "APP_URL": "http://localhost:8000",
        "MCP_AUTH_TOKEN": "YOUR_TOKEN_HERE"
      }
    }
  }
}
```

> Replace `C:/path/to/mcp-forge` with the actual path to the repo on your machine.  
> On macOS/Linux use `.venv/bin/python` instead of `.venv/Scripts/python.exe`.

### Via Claude Desktop Connectors UI (newer versions)

Some newer Claude Desktop builds have a **Customize → Connectors** screen:

1. Click **Customize** in the left sidebar → **Connectors** → **`+`**
2. Fill in: **Name** = `mcp-forge`, **URL** = `http://localhost:8001/sse`, **Header** = `X-MCP-Token` / *(your token)*
3. Save → fully restart Claude Desktop

> ⚠️ If there is no URL field (only OAuth options), use the script method above.

### Changing the token later

Edit `MCP_AUTH_TOKEN=` in `.env`, run `docker compose restart`, then re-run the install script.

---

### What you can ask Claude Desktop

```
Create a new MCP Forge project called "petstore" from
https://petstore3.swagger.io/api/v3/openapi.json
```
```
Analyze project 1 and tell me what endpoints were found
```
```
Generate the MCP server for project 1 in Python FastMCP
```
```
Run tests for project 1 and show me the results
```
```
Show me the generated code for project 1
```
```
Do I have any unread notifications in MCP Forge?
```
```
Chat with the forge agent for project 1:
"Review all endpoints and ask me anything unclear before generating"
```

### Available MCP tools

| Tool | What it does |
|---|---|
| `create_project` | Create a project and auto-start analysis |
| `list_projects` | List all projects with status |
| `analyze_source` | Trigger / re-trigger source analysis |
| `generate_mcp` | Generate the MCP server code |
| `get_generated_code` | Read generated files |
| `get_project_status` | Poll project status (with built-in long-poll) |
| `run_tests` | Run AI-generated tests |
| `get_test_results` | Latest pass/fail counts |
| `list_snapshots` | All versioned snapshots |
| `rollback_snapshot` | Restore a previous snapshot |
| `chat_with_agent` | Talk to the AI forge agent |
| `get_notifications` | Bell notifications (questions, errors) |
| `get_clarifications` | List pending clarification questions |
| `answer_clarification` | Answer a clarification question |
| `validate_generated_code` | Security + structure audit |

---

## 3. Connect to Claude Code Terminal

### Option A — Marketplace install (recommended)

In Claude Code Terminal, run:

```
/plugin marketplace add coderXcode/mcp-forge
/plugin install mcp-forge@coderXcode-mcp-forge
```

Reload Claude Code. Skills are available immediately — no cloning or environment variables needed.

> This installs the plugin from the Claude Code marketplace using the `coderXcode/mcp-forge` package identifier. Claude Code fetches the plugin manifest and registers all forge skills automatically.

### Option B — Auto-detected from repo root

If you have this repo cloned and open in Claude Code, the `.mcp.json` file at the root is picked up automatically.

Set your token as an environment variable before launching VS Code:

```powershell
# Windows PowerShell
$env:FORGE_TOKEN = "your-token-here"

# macOS / Linux
export FORGE_TOKEN=your-token-here
```

### Skills available in Claude Code

```
/forge:analyze <project_id>          # trigger analysis
/forge:generate <project_id>         # generate MCP server
/forge:chat <project_id> <message>   # chat with AI agent
/forge:status                        # list all projects
/forge:test <project_id>             # run tests
/forge:rollback <project_id> <ver>   # rollback to snapshot
```

---

## 4. Connect to Codex

```bash
# Install the forge CLI — pick one:
pip install mcp-forger                                                            # from PyPI (recommended)
pipx install mcp-forger                                                           # isolated install
pip install git+https://github.com/coderXcode/mcp-forge.git     # directly from GitHub

# Add the plugin to Codex
codex marketplace add mcp-forge/mcp-forge
```

Skills in Codex:

```
$forge discover          # list all projects
$forge analyze 1         # trigger analysis
$forge generate 1        # generate MCP server
$forge chat 1 "message"  # chat with AI agent
```

---

## 5. forge CLI

A `forge` command-line tool is included for terminal-based workflows.

### Install

```bash
# From PyPI (recommended)
pip install mcp-forger
pipx install mcp-forger

# From GitHub
pip install git+https://github.com/coderXcode/mcp-forge.git
pipx install git+https://github.com/coderXcode/mcp-forge.git

# From this repo (local dev)
pip install -e .
```

### Commands

```bash
forge connect --url http://localhost:8000 --token <token>  # save connection
forge status                                                # list all projects
forge analyze 1                                             # trigger analysis
forge generate 1 --lang python_fastmcp                     # generate MCP server
forge chat 1 "add rate limiting to all tools"              # chat with agent
forge logs 1 --tail 50                                      # coloured log tail
forge plugin install                                        # write claude_desktop_config.json
forge plugin status                                         # verify config
```

---

## 6. Using a Local Folder as Source

The `mnt/` folder next to `docker-compose.yml` is live-mounted into the container at `/mnt/`. Drop any project folder there and point MCP Forge at it — no Docker restart needed.

```
mcp-forge/
└── mnt/
    └── my-api/          ← copy your project folder here
        ├── src/
        └── package.json
```

In the dashboard or via Claude: set **Source type** = `local_folder`, **Source path** = `/mnt/my-api`.

When using Claude Desktop, tell Claude: *"My project is in the mnt/ folder as 'my-api', source type local_folder, path /mnt/my-api"*.

> The `mnt/` folder contents are gitignored — your code won't be committed.

---

## 7. Local HuggingFace Model (No API Key)

Run entirely offline with a local model. Requires an NVIDIA GPU.

### Requirements

- NVIDIA GPU with ≥8 GB VRAM
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

### Setup

```env
LLM_PROVIDER=local
LOCAL_MODEL=Qwen/Qwen2.5-Coder-14B-Instruct
LOCAL_MODEL_DEVICE=auto
LOCAL_MODEL_LOAD_IN_4BIT=true
```

Rebuild once (installs `transformers`, `accelerate`, `bitsandbytes`):

```bash
docker compose down && docker compose build && docker compose up -d
```

The model downloads from HuggingFace on first use (~8 GB) and is cached for future runs.

| Model | VRAM (4-bit) | Quality |
|---|---|---|
| `Qwen/Qwen2.5-Coder-7B-Instruct` | ~4 GB | Good |
| `Qwen/Qwen2.5-Coder-14B-Instruct` | ~8 GB | **Recommended** |
| `deepseek-ai/deepseek-coder-v2-lite-instruct` | ~8 GB | Very good |
| `Qwen/Qwen2.5-Coder-32B-Instruct` | ~18 GB | Best |

---

## 8. Configuration Reference

All settings live in `.env`. They can also be edited live from the **Config** page in the dashboard.

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` \| `anthropic` \| `openai` \| `local` |
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `ANTHROPIC_API_KEY` | — | Anthropic Claude API key |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `ANTHROPIC_MODEL` | `claude-3-5-sonnet-20241022` | Anthropic model name |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model name |
| `LOCAL_MODEL` | `Qwen/Qwen2.5-Coder-14B-Instruct` | HuggingFace model ID |
| `LOCAL_MODEL_DEVICE` | `auto` | `auto` \| `cuda` \| `cpu` |
| `LOCAL_MODEL_LOAD_IN_4BIT` | `true` | 4-bit NF4 quantization (requires NVIDIA GPU) |
| `GITHUB_TOKEN` | — | PAT for private GitHub repo ingestion |
| `DB_URL` | `sqlite:///./data/mcp_forge.db` | SQLite (default) or PostgreSQL URL |
| `MCP_AUTH_TOKEN` | `change-me-mcp-secret` | Auth token for Claude / Codex — **change this** |
| `MCP_SERVER_PORT` | `8001` | MCP SSE server port |
| `OUTPUT_DIR` | `./generated` | Where generated MCP files are written |
| `ENABLE_GIT_SNAPSHOTS` | `false` | Auto-commit each snapshot to a local git repo |
| `ENABLE_LIVE_PROBING` | `true` | Allow live URL probing during analysis |
| `ENABLE_SECURITY_AUDIT` | `true` | Scan generated code for security issues |
| `SECRET_KEY` | auto | FastAPI session secret |
| `DEBUG` | `false` | Enable uvicorn reload and verbose logs |

---

## 9. Resetting the Database

```bash
# Clear all rows (schema preserved)
echo y | docker exec -i mcp_forge_app python clear_db.py

# Full reset including volumes
docker compose down -v && docker compose up -d
```

---

## 10. Troubleshooting

### mcp-forge not showing in Claude Desktop (red dot or missing)

- **Fully quit** Claude Desktop — system tray / menu bar → **Quit** (not just close the window)
- Re-run the install script: `.\scripts\install_claude_plugin.ps1`
- Check the config file was written: open it and validate the JSON at [jsonlint.com](https://jsonlint.com)
- Make sure Docker is running: `docker ps`

### "Connection refused" on port 8001

```bash
docker ps                              # confirm mcp_forge_mcp is Up
docker logs mcp_forge_mcp --tail 30    # check for startup errors
docker compose up -d                   # restart if needed
```

### Wrong or expired auth token

```bash
# Get the current token
docker exec mcp_forge_app printenv MCP_AUTH_TOKEN

# Re-run the install script to update claude_desktop_config.json automatically
.\scripts\install_claude_plugin.ps1
```

### `url:` field not supported in your Claude Desktop version

Use **stdio mode** — the install script already writes this format. For manual config:

```json
{
  "mcpServers": {
    "mcp-forge": {
      "command": "C:/path/to/mcp-forge/.venv/Scripts/python.exe",
      "args": ["mcp_server/server.py"],
      "cwd": "C:/path/to/mcp-forge",
      "env": {
        "APP_URL": "http://localhost:8000",
        "MCP_AUTH_TOKEN": "YOUR_TOKEN_HERE"
      }
    }
  }
}
```

### Tests stuck on "running" with 0/0 results

The test container may still be spinning up. Wait ~30 seconds and click **Run Tests** again from the dashboard Tests tab.

---

## 11. Architecture

```
Claude Desktop / Claude Code / Codex
        │
        │  stdio  (Claude Desktop)
        │  SSE http://localhost:8001/sse  (Claude Code / Codex)
        ▼
 mcp_server/server.py     ←  FastMCP  ·  15 tools
        │
        │  httpx REST  (X-MCP-Token header)
        ▼
 http://localhost:8000     ←  MCP Forge  ·  FastAPI
        │
        ├── SQLite  (projects · snapshots · chat · tests · notifications)
        ├── LLM     (Gemini / Anthropic / OpenAI / Local Qwen NF4)
        └── ./generated/   ←  output MCP server files
```
