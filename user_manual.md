# MCP Forge — User Manual

> Advanced configuration, Codex integration, local folder setup, troubleshooting, and architecture reference.
> For the main getting-started guide see [README.md](README.md) (or [PyPI](https://pypi.org/project/mcp-forger/)).

```bash
pip install mcp-forger   # install the forge CLI
```

---

## Table of Contents

1. [Connect to Claude Desktop — Manual Config](#1-connect-to-claude-desktop--manual-config)
2. [Connect to Claude Code](#2-connect-to-claude-code)
3. [Connect to Codex](#3-connect-to-codex)
4. [Using a Local Folder as Source](#4-using-a-local-folder-as-source)
5. [Local HuggingFace Model (No API Key)](#5-local-huggingface-model-no-api-key)
6. [Full Configuration Reference](#6-full-configuration-reference)
7. [Resetting the Database](#7-resetting-the-database)
8. [Available MCP Tools](#8-available-mcp-tools)
9. [Architecture](#9-architecture)

---

## 1. Connect to Claude Desktop — Manual Config

The install scripts (`install_claude_plugin.ps1` / `.sh`) handle this automatically. Only use this section if you need to configure manually.

### Get your auth token

```bash
# macOS / Linux
grep -m1 '^MCP_AUTH_TOKEN=' .env | cut -d= -f2
# Windows (PowerShell)
(Get-Content .env | Where-Object { $_ -match '^MCP_AUTH_TOKEN=' }) -replace '^MCP_AUTH_TOKEN=',''
```

### Config file location

| OS | Path |
|---|---|
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

### stdio config (recommended — works on all Claude Desktop versions)

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

> Replace `C:/path/to/mcp-forge` with the actual repo path on your machine.
> On macOS/Linux use `.venv/bin/python` instead of `.venv/Scripts/python.exe`.

### SSE config (newer Claude Desktop versions with Connectors UI)

```json
{
  "mcpServers": {
    "mcp-forge": {
      "url": "http://localhost:8001/sse",
      "headers": { "X-MCP-Token": "YOUR_TOKEN_HERE" }
    }
  }
}
```

Or via **Customize → Connectors → `+`** in Claude Desktop UI:
- Name: `mcp-forge`
- URL: `http://localhost:8001/sse`
- Header: `X-MCP-Token` / your token

### After configuring

1. Fully **QUIT** Claude Desktop (system tray / menu bar → Quit — not just close)
2. Reopen → **Settings → Developer** → look for **mcp-forge** with 🟢 green dot

### Changing the token later

Edit `MCP_AUTH_TOKEN=` in `.env` → `docker compose restart` → re-run install script or update the config file.

---

## 2. Connect to Claude Code

### Option A — Marketplace (recommended, no cloning needed)

In Claude Code terminal:

```
/plugin marketplace add coderXcode/mcp-forge
/plugin install mcp-forge@coderXcode-mcp-forge
```

Reload Claude Code — skills are available immediately.

### Option B — Auto-detected from repo root

Clone the repo and open it in Claude Code — `.mcp.json` at the root is picked up automatically.

Set your token before launching VS Code:

```powershell
# Windows
$env:FORGE_TOKEN = "your-token-here"

# macOS / Linux
export FORGE_TOKEN=your-token-here
```

### Skills

```
/forge:analyze <project_id>
/forge:generate <project_id>
/forge:chat <project_id> <message>
/forge:status
/forge:test <project_id>
/forge:rollback <project_id> <version>
```

---

## 3. Connect to Codex

```bash
# Install the forge CLI
pip install mcp-forger
pipx install mcp-forger
pip install git+https://github.com/coderXcode/mcp-forge.git   # directly from GitHub

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

## 4. Using a Local Folder as Source

The `mnt/` folder next to `docker-compose.yml` is live-mounted into the container at `/mnt/`. Drop any project folder there — no Docker restart needed.

```
mcp-forge/
└── mnt/
    └── my-api/          ← copy your project folder here
        ├── src/
        └── package.json
```

- In the **dashboard**: Source type = `Local Folder`, Path = `/mnt/my-api`
- In **Claude Desktop**: *"Create a project, source type local_folder, path /mnt/my-api"*
- With the **CLI**: `forge analyze 1` after creating the project with `source_url=/mnt/my-api`

> `mnt/` contents are gitignored — your code won't be committed.

---

## 5. Local HuggingFace Model (No API Key)

Requires NVIDIA GPU + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html).

```env
LLM_PROVIDER=local
LOCAL_MODEL=Qwen/Qwen2.5-Coder-14B-Instruct   # any HuggingFace model ID
LOCAL_MODEL_DEVICE=auto
LOCAL_MODEL_LOAD_IN_4BIT=true
```

```bash
docker compose down && docker compose build && docker compose up -d
```

The model downloads on first use and is cached. Swap `LOCAL_MODEL` for any HuggingFace instruction model:

| Model | VRAM (4-bit) | Quality |
|---|---|---|
| `Qwen/Qwen2.5-Coder-7B-Instruct` | ~4 GB | Good |
| `Qwen/Qwen2.5-Coder-14B-Instruct` | ~8 GB | **Recommended** |
| `deepseek-ai/deepseek-coder-v2-lite-instruct` | ~8 GB | Very good |
| `Qwen/Qwen2.5-Coder-32B-Instruct` | ~18 GB | Best |
| `mistralai/Mistral-7B-Instruct-v0.3` | ~4 GB | General purpose |

> CPU-only: `LOCAL_MODEL_LOAD_IN_4BIT=false` + `LOCAL_MODEL_DEVICE=cpu` — slower but no GPU needed.

---

## 6. Full Configuration Reference

All settings live in `.env` — also editable live from the dashboard **Config** page.

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` \| `anthropic` \| `openai` \| `local` |
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `ANTHROPIC_API_KEY` | — | Anthropic Claude API key |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `ANTHROPIC_MODEL` | `claude-3-5-sonnet-20241022` | Anthropic model |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model |
| `LOCAL_MODEL` | `Qwen/Qwen2.5-Coder-14B-Instruct` | HuggingFace model ID |
| `LOCAL_MODEL_DEVICE` | `auto` | `auto` \| `cuda` \| `cpu` |
| `LOCAL_MODEL_LOAD_IN_4BIT` | `true` | 4-bit NF4 quantization (NVIDIA GPU required) |
| `GITHUB_TOKEN` | — | PAT for private GitHub repo ingestion |
| `DB_URL` | `sqlite:///./data/mcp_forge.db` | SQLite or PostgreSQL URL |
| `MCP_AUTH_TOKEN` | `change-me-mcp-secret` | Auth token — **change this** |
| `MCP_SERVER_PORT` | `8001` | MCP SSE server port |
| `OUTPUT_DIR` | `./generated` | Where generated files are written |
| `ENABLE_GIT_SNAPSHOTS` | `false` | Auto-commit snapshots to git |
| `ENABLE_LIVE_PROBING` | `true` | Allow live URL probing during analysis |
| `ENABLE_SECURITY_AUDIT` | `true` | Scan generated code for security issues |
| `SECRET_KEY` | auto | FastAPI session secret |
| `DEBUG` | `false` | Verbose logs + uvicorn reload |

---

## 7. Resetting the Database

```bash
# Clear all rows (schema preserved)
echo y | docker exec -i mcp_forge_app python clear_db.py

# Full reset including volumes
docker compose down -v && docker compose up -d
```

---

## 8. Available MCP Tools

These are the tools exposed to Claude Desktop / Claude Code / Codex:

| Tool | What it does |
|---|---|
| `create_project` | Create a project and auto-start analysis |
| `list_projects` | List all projects with status |
| `analyze_source` | Trigger / re-trigger source analysis |
| `generate_mcp` | Generate the MCP server code |
| `get_generated_code` | Read generated files |
| `get_project_status` | Poll status (built-in long-poll — waits for change) |
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

## 9. Architecture

```
Claude Desktop / Claude Code / Codex
        │
        │  stdio  (Claude Desktop — via install script)
        │  SSE http://localhost:8001/sse  (Claude Code / Codex / Connectors UI)
        ▼
 mcp_server/server.py     ←  FastMCP  ·  15 tools
        │
        │  httpx REST  (X-MCP-Token header)
        ▼
 http://localhost:8000     ←  MCP Forge  ·  FastAPI
        │
        ├── SQLite  (projects · snapshots · chat · tests · notifications)
        ├── LLM     (Gemini / Anthropic / OpenAI / Local HuggingFace NF4)
        └── ./generated/   ←  output MCP server files

forge CLI  ──────────────────────────────────────────────────►  http://localhost:8000
(pip install mcp-forger)                                         REST API  (X-MCP-Token)
```
