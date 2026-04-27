<p align="center">
  <img src="https://raw.githubusercontent.com/coderXcode/mcp-forge/main/images/mcp_forge.jpg" alt="MCP Forger" width="200" />
</p>

<h1 align="center">🔨 MCP Forger</h1>

<p align="center">
  Convert <strong>any application</strong> into an MCP (Model Context Protocol) server — with AI assistance.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/docker-ready-blue?logo=docker" />
  <img src="https://img.shields.io/badge/claude-plugin-blueviolet?logo=anthropic" />
  <img src="https://img.shields.io/badge/python-3.12+-green?logo=python" />
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" />
  <img src="https://img.shields.io/pypi/v/mcp-forger?label=pypi" />
</p>

---

MCP Forger is a self-hosted AI agent that analyzes your existing app (via OpenAPI spec, GitHub repo, live URL, or local code) and generates a production-ready MCP server that **Claude Desktop, Claude Code**, or any MCP client can use directly.

---

## ✨ Features

| Category | Highlights |
|---|---|
| **Source ingestion** | OpenAPI/Swagger URL · GitHub repo · Live URL probing · Local folder (`mnt/`) · File upload · Manual description |
| **AI agent** | Multi-LLM (Gemini · Anthropic · OpenAI · local HuggingFace) · per-project chat · clarification Q&A loop |
| **Code generation** | Python FastMCP · Node.js (in testing) · Go (in testing) · Generic (in testing)· LLM polish pass · security audit |
| **Versioning** | Snapshot on every generation · one-click rollback · optional git commits |
| **Testing** | AI-generated pytest cases · in-container runner · full test history |
| **Dashboard** | Real-time logs · 6-tab project view · editable `.env` config from the browser |
| **Integrations** | Claude Desktop · Claude Code · Codex · `forge` CLI |

---

## 🗺️ Two Ways to Use MCP Forger

| Method | Best for |
|---|---|
| **Web Dashboard** | Visual workflow — point & click, no code |
| **`forge` CLI + Claude Desktop** | AI-driven workflow from your terminal or Claude chat |

Both require MCP Forger running in Docker first — see [Step 1](#step-1--run-mcp-forge-docker) below.

---

## Step 1 — Run MCP Forger (Docker)

> **Required for everything** — the dashboard, CLI, and Claude Desktop all connect to this Docker instance.

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- At least one LLM API key **or** an NVIDIA GPU for local mode

### 1.1 — Clone & configure

```bash
git clone https://github.com/coderXcode/mcp-forge.git
cd mcp-forge
cp .env.example .env
```

Open `.env` and set at minimum:

```env
LLM_PROVIDER=gemini          # or: anthropic | openai | local
GEMINI_API_KEY=your-key-here

# This token authenticates the CLI and Claude Desktop — change it to something secret
MCP_AUTH_TOKEN=change-me-to-something-secret
```

> **Free option:** Gemini has a free tier at [aistudio.google.com](https://aistudio.google.com) — no credit card needed.

### 1.2 — Start

```bash
docker compose up -d
```

| Service | URL | Purpose |
|---|---|---|
| 🌐 Dashboard | http://localhost:8000 | Web UI — full visual workflow |
| 🔌 MCP endpoint | http://localhost:8001/sse | Used by Claude Desktop / Claude Code |

### 1.3 — Verify it's running

```bash
# Should return [] (empty list — that's fine)
curl http://localhost:8000/api/projects/
```

✅ MCP Forger is now online. Keep Docker running whenever you use the CLI or Claude Desktop.

---

## Step 2A — Use the Web Dashboard

Visit **http://localhost:8000** → click **+ New Project** → follow the UI.

No further setup needed.

---

## Step 2B — Use the `forge` CLI

### Install

```bash
pip install mcp-forger
# or: pipx install mcp-forger  (isolated, recommended)
```

### Connect the CLI to your running MCP Forger instance

> Do this once — it saves your connection details locally.

```bash
forge connect --url http://localhost:8000 --token YOUR_MCP_AUTH_TOKEN
```

Get your token with:
```bash
docker exec mcp_forge_app printenv MCP_AUTH_TOKEN
```

### Verify

```bash
forge status
# Should list your projects (empty at first — that's fine)
```

### Create and convert your first project

```bash
# From an OpenAPI/Swagger spec URL
forge analyze 1   # after creating via dashboard or --source-url flag

# Check what's happening
forge logs 1 --tail 20

# Generate the MCP server
forge generate 1 --lang python_fastmcp

# Run AI-generated tests
forge test 1

# Chat with the AI agent
forge chat 1 "review all endpoints and ask me anything unclear"
```

### Install the Claude Desktop plugin (one command)

```bash
forge plugin install
# Then fully quit + reopen Claude Desktop
```

This writes `claude_desktop_config.json` automatically — no manual editing.

### All CLI commands

```bash
forge connect   --url <url> --token <token>    # save connection (run once)
forge status                                    # list all projects
forge analyze   <project_id>                    # trigger analysis
forge generate  <project_id> --lang <lang>      # generate MCP server
forge chat      <project_id> "<message>"        # chat with AI agent
forge logs      <project_id> --tail 50          # stream live logs
forge test      <project_id>                    # run AI-generated tests
forge plugin    install                         # write claude_desktop_config.json
forge plugin    status                          # verify Claude Desktop config
```

---

## Step 2C — Use Claude Desktop

Claude Desktop lets you control MCP Forger entirely through natural language.

### Install the plugin

**Windows (PowerShell):**
```powershell
.\scripts\install_claude_plugin.ps1
```

**macOS / Linux:**
```bash
bash scripts/install_claude_plugin.sh
```

Or if you have the CLI installed:
```bash
forge plugin install
```

Then **fully quit and reopen Claude Desktop** (right-click system tray → Quit).

Go to **Settings → Developer** — you should see **mcp-forge** with a 🟢 green dot.

### Example prompts

```
Create a new MCP Forger project called "petstore" from
https://petstore3.swagger.io/api/v3/openapi.json
```
```
Generate the MCP server for project 1 in Python FastMCP
```
```
Run tests for project 1 and show me the results
```
```
Chat with the forge agent for project 1:
"Add rate limiting to all tools"
```

---

## Step 2D — Use Claude Code

```
/plugin marketplace add coderXcode/mcp-forge
/plugin install mcp-forge@coderXcode-mcp-forge
```

Skills available:
```
/forge:analyze <project_id>
/forge:generate <project_id>
/forge:chat <project_id> <message>
/forge:status
/forge:test <project_id>
/forge:rollback <project_id> <version>
```

---

## 🖥️ Local Model (No API Key)

Run entirely offline with any HuggingFace model — no API key needed. Requires NVIDIA GPU.

```env
LLM_PROVIDER=local
LOCAL_MODEL=Qwen/Qwen2.5-Coder-14B-Instruct   # swap for any HuggingFace model
LOCAL_MODEL_DEVICE=auto
LOCAL_MODEL_LOAD_IN_4BIT=true
```

```bash
docker compose down && docker compose build && docker compose up -d
```

| Model | VRAM (4-bit) | Notes |
|---|---|---|
| `Qwen/Qwen2.5-Coder-7B-Instruct` | ~4 GB | Lightest |
| `Qwen/Qwen2.5-Coder-14B-Instruct` | ~8 GB | **Recommended** |
| `deepseek-ai/deepseek-coder-v2-lite-instruct` | ~8 GB | Strong alternative |
| `Qwen/Qwen2.5-Coder-32B-Instruct` | ~18 GB | Best quality |
| `mistralai/Mistral-7B-Instruct-v0.3` | ~4 GB | General purpose |

> CPU-only (no GPU): set `LOCAL_MODEL_LOAD_IN_4BIT=false` and `LOCAL_MODEL_DEVICE=cpu` — much slower but works.

---

## ⚙️ Key Configuration

All settings live in `.env` — also editable live from the dashboard **Config** page.

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` \| `anthropic` \| `openai` \| `local` |
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `ANTHROPIC_API_KEY` | — | Anthropic Claude API key |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `MCP_AUTH_TOKEN` | `change-me` | Auth token for CLI / Claude — **change this** |
| `GITHUB_TOKEN` | — | PAT for private GitHub repos |
| `LOCAL_MODEL` | `Qwen/Qwen2.5-Coder-14B-Instruct` | Any HuggingFace model ID |
| `ENABLE_GIT_SNAPSHOTS` | `false` | Auto-commit each snapshot to git |
| `DEBUG` | `false` | Verbose logs + uvicorn reload |

---

## 🐳 Useful Docker Commands

```bash
docker compose up -d              # start
docker compose up -d --build      # rebuild after code changes
docker compose restart            # restart after .env changes
docker compose down -v            # stop + wipe database
docker logs mcp_forge_app -f      # app logs
docker logs mcp_forge_mcp -f      # MCP server logs
```

---

## 🔧 Troubleshooting

**mcp-forge not showing in Claude Desktop (red dot / missing)**
- Fully quit Claude Desktop (system tray → Quit, not just close)
- Re-run: `forge plugin install` or `.\scripts\install_claude_plugin.ps1`
- Validate JSON at [jsonlint.com](https://jsonlint.com)

**"Connection refused" on port 8000 or 8001**
```bash
docker ps                          # check containers are running
docker compose up -d               # start if not running
docker logs mcp_forge_app --tail 30
```

**Wrong / expired auth token**
```bash
docker exec mcp_forge_app printenv MCP_AUTH_TOKEN
forge connect --url http://localhost:8000 --token <new-token>
forge plugin install   # updates claude_desktop_config.json too
```

**Reset the database**
```bash
echo y | docker exec -i mcp_forge_app python clear_db.py
```

---

## 📖 Full Documentation

See **[user_manual.md](https://github.com/coderXcode/mcp-forge/blob/main/user_manual.md)** for advanced configuration, Codex integration, local folder setup, architecture details, and more.

---

## 📝 License

MIT
