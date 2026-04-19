<p align="center">
  <img src="images/mcp_forge.jpg" alt="MCP Forge" width="200" />
</p>

<h1 align="center">🔨 MCP Forge</h1>

<p align="center">
  Convert <strong>any application</strong> into an MCP (Model Context Protocol) server — with AI assistance.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/docker-ready-blue?logo=docker" />
  <img src="https://img.shields.io/badge/claude-plugin-blueviolet?logo=anthropic" />
  <img src="https://img.shields.io/badge/python-3.12+-green?logo=python" />
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" />
</p>

---

MCP Forge is a self-hosted AI agent that analyzes your existing app (via OpenAPI spec, GitHub repo, live URL, or raw code in any language) and generates a production-ready MCP server that **Claude Desktop, Claude Code, Codex**, or any MCP client can use directly.

---

## ✨ Features

### Core Conversion
| Feature | Description |
|---|---|
| **OpenAPI / Swagger ingestion** | Point to any OAS 2/3 spec URL or paste raw JSON/YAML — all endpoints extracted automatically |
| **GitHub repo ingestion** | Enter a GitHub URL (public or private with token) — code fetched, analyzed, converted |
| **Live URL probing** | Give a running app URL — Forge probes 15+ common paths to auto-discover the API structure |
| **Local folder** | Drop any project folder into `mnt/` — it's auto-mounted in Docker, just point at `/mnt/your-folder` |
| **File / zip upload** | Upload code files directly from your machine |
| **Language-agnostic analysis** | Works on Python, Node.js, Go, Java, Ruby, PHP, Rust, C#, and more — LLM-powered analysis means no AST parser required |
| **Documentation ingestion** | Provide docs/README URLs alongside code for richer context |

### AI Agent
| Feature | Description |
|---|---|
| **Multi-LLM support** | Switch between Gemini, Anthropic Claude, OpenAI GPT, and **local HuggingFace models** with a single env var |
| **Local HuggingFace model** | Run any HuggingFace model (e.g. `Qwen/Qwen2.5-Coder-14B-Instruct`) fully offline with 4-bit NF4 quantization — no API key needed |
| **Per-project chat** | Conversational agent per project — ask it to add tools, change auth, refine output |
| **Clarification Q&A loop** | Agent sends `[CLARIFICATION]` questions when it needs more context; a bell notification fires and links to the chat tab; your inline answers feed back into the generation polish pass |
| **Memory** | Agent carries project context (analysis, snapshots, test results) into every conversation |

### Code Generation
| Feature | Description |
|---|---|
| **Python / FastMCP** | Primary output — async FastMCP server with `@mcp.tool()` and `@mcp.resource()` decorators |
| **Node.js** | MCP SDK-based server in TypeScript/JS |
| **Go** | `mcp-golang` based server |
| **LLM polish pass** | After template generation, a second LLM pass improves quality and injects answered clarifications |
| **Security audit** | Scans generated code for hardcoded secrets, `eval`, `exec`, and unsafe subprocess calls |

### Versioning & Rollback
| Feature | Description |
|---|---|
| **Snapshot system** | Every generation creates a numbered snapshot with a file diff from the previous version |
| **One-click rollback** | Restore any previous version from the Snapshots tab |
| **Optional git commits** | Enable `ENABLE_GIT_SNAPSHOTS=true` to auto-commit each snapshot to a local git repo |

### Testing
| Feature | Description |
|---|---|
| **AI-generated tests** | LLM writes pytest test cases from your generated server code or documentation |
| **In-container test runner** | Tests run inside Docker with `pytest --json-report`; results shown in the dashboard |
| **Test history** | All test runs stored with pass/fail/skip counts and full output |

### Dashboard & UI
| Feature | Description |
|---|---|
| **Real-time logs** | SSE-streamed live log panel per project |
| **Auto-refreshing status badge** | Project status badge polls every 2s and reloads the page when a job finishes |
| **Live LLM provider badge** | Top-right badge updates instantly when you switch providers — no page reload |
| **LLM model in logs** | Every job logs the active provider + model (e.g. `LLM: GEMINI / gemini-2.5-flash`) |
| **Notification bell** | Agent questions and system alerts pushed to the UI bell in real time with deep-links to the relevant tab |
| **6-tab project view** | Overview · Chat · Generated Code · Tests · Snapshots · Logs |
| **Editable .env config** | Edit every API key and feature flag from the browser — no SSH needed |
| **Syntax-highlighted code viewer** | Browse every generated file with highlight.js |
| **Diff viewer** | Snapshot diffs shown inline |

### Claude / Codex Plugin (MCP Server)
| Feature | Description |
|---|---|
| **Claude Desktop plugin** | MCP Forge exposes itself as an MCP server over **SSE** (port 8001) or **stdio** — Claude Desktop drives the entire conversion workflow |
| **Claude Code plugin** | `.mcp.json` at the repo root — Claude Code picks it up automatically; 6 skills as `/forge:*` commands |
| **Codex plugin** | `plugins/codex-plugin.yaml` manifest ready for the Codex marketplace |
| **forge CLI** | `forge connect / status / analyze / generate / chat / plugin install` — install with `pip install mcp-forge` |
| **11 MCP tools** | `create_project`, `analyze_source`, `generate_mcp`, `run_tests`, `rollback_snapshot`, `chat_with_agent`, `get_notifications`, `validate_generated_code`, and more |
| **2 MCP resources** | `forge://projects` and `forge://projects/{id}/analysis` |

---

## 🚀 Quick Start

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- At least one LLM API key (Gemini, Anthropic, or OpenAI) — or a GPU for local mode

### 1 — Get the code

```bash
git clone https://github.com/coderXcode/mcp-forge.git
cd YOUR_REPO
```

### 2 — Configure

```bash
cp .env.example .env
```

Open `.env` and fill in at minimum one LLM key:

```env
LLM_PROVIDER=gemini          # or: anthropic | openai | local

GEMINI_API_KEY=your-key-here
# ANTHROPIC_API_KEY=your-key-here
# OPENAI_API_KEY=your-key-here

# Optional — for GitHub private repo access:
GITHUB_TOKEN=ghp_...

# Change this — used to authenticate Claude Desktop / Codex
MCP_AUTH_TOKEN=change-me-to-something-secret
```

> **Free option:** Gemini has a free tier at [aistudio.google.com](https://aistudio.google.com).

### 3 — Start

```bash
docker compose up -d
```

| Service | URL | Purpose |
|---|---|---|
| 🌐 Dashboard | http://localhost:8000 | Web UI — all operations |
| 🔌 MCP SSE endpoint | http://localhost:8001/sse | Claude Desktop / Claude Code / Codex |

### 4 — Open the dashboard

Visit **http://localhost:8000** → click **+ New Project** to begin.

---

## 🔄 Converting Your First App

1. Click **+ New Project** on the dashboard
2. Choose a source type:
   - **OpenAPI/Swagger URL** — e.g. `https://petstore3.swagger.io/api/v3/openapi.json`
   - **GitHub Repository** — e.g. `https://github.com/org/repo`
   - **Live App URL** — Forge auto-probes 15+ common paths
   - **Local Folder** — drop folder into `mnt/`, enter `/mnt/your-folder`
   - **Upload Code Files** — upload directly from your browser
3. Choose target language (Python FastMCP recommended)
4. Click **Start Conversion** — analysis begins immediately
5. Use the **Chat tab** to talk to the agent, answer clarification questions, or request changes
6. **Generated Code tab** → view, validate, download
7. **Tests tab** → generate and run AI-written tests
8. **Snapshots tab** → roll back to any previous version

---

## 📁 Using a Local Folder

1. Drop your project folder into `mnt/`:
   ```
   YOUR_REPO/
   └── mnt/
       └── my-api/          ← drag your folder here
           ├── src/
           └── package.json
   ```
2. No restart needed — volume is live-mounted
3. In the dashboard: Source type = **Local Folder Path**, Path = `/mnt/my-api`

> The `mnt/` folder contents are gitignored — your code won't be committed.

---

## 🖥️ Local HuggingFace Model (No API Key)

Run entirely offline with a local model.

### Requirements
- NVIDIA GPU with ≥8 GB VRAM
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) on the host

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

The model (~8 GB) downloads from HuggingFace on first use and is cached for subsequent runs.

| Model | VRAM (4-bit) | Quality |
|---|---|---|
| `Qwen/Qwen2.5-Coder-7B-Instruct` | ~4 GB | Good |
| `Qwen/Qwen2.5-Coder-14B-Instruct` | ~8 GB | **Recommended** |
| `deepseek-ai/deepseek-coder-v2-lite-instruct` | ~8 GB | Very good |
| `Qwen/Qwen2.5-Coder-32B-Instruct` | ~18 GB | Best |

---

## 🤖 Claude Desktop Plugin

Connect MCP Forge to Claude Desktop so Claude can drive the entire workflow.

### One-command install

**🪟 Windows (PowerShell):**
```powershell
.\scripts\install_claude_plugin.ps1
```

**🍎 macOS / 🐧 Linux (Terminal):**
```bash
bash scripts/install_claude_plugin.sh
```

Both scripts:
- Check Docker + `mcp_forge_app` is running
- Pull `MCP_AUTH_TOKEN` automatically from the container
- Create the `Claude` config folder if it doesn't exist
- Write `claude_desktop_config.json` with the correct token and SSE URL

Config file locations written by the script:

| OS | Path |
|---|---|
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

> **Mac:** Claude Desktop must be installed first — download from [claude.ai/download](https://claude.ai/download). The script will warn you if it's not found.

Then **fully quit and reopen Claude Desktop** (system tray / menu bar → Quit).

### Verify

Open Claude Desktop → **Settings → Developer** → you should see **mcp-forge** with a 🟢 green dot.

> To change the token: edit `MCP_AUTH_TOKEN=` in `.env`, run `docker compose restart`, then re-run the script.

### Manual config (SSE mode)

If you prefer to write the file yourself — config location:

| OS | Path |
|---|---|
| Windows | `C:\Users\<YourName>\AppData\Roaming\Claude\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |

```json
{
  "mcpServers": {
    "mcp-forge": {
      "url": "http://localhost:8001/sse",
      "headers": {
        "X-MCP-Token": "YOUR_TOKEN_HERE"
      }
    }
  }
}
```

### Example prompts for Claude

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
Do I have any unread notifications in MCP Forge?
```
```
Chat with the forge agent for project 1:
"Review all endpoints and ask me anything unclear before generating"
```

---

## 🧩 Claude Code Plugin

Two ways to install — pick one:

**Option A — Marketplace install (recommended, one-time):**
```
/plugin marketplace add coderXcode/mcp-forge
/plugin install mcp-forge@coderXcode-mcp-forge
```
Reload Claude Code. Skills become available immediately.

**Option B — Auto-detected from repo root:**
Clone the repo and open it in Claude Code — `.mcp.json` at the root is picked up automatically.

Set your token:

```powershell
# Windows
$env:FORGE_TOKEN = "your-token-here"

# macOS / Linux
export FORGE_TOKEN=your-token-here
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

## ⚒️ forge CLI

A `forge` command-line tool is included for terminal-based workflows.

### Install

```bash
# From this repo (works immediately)
pip install -e .

# From GitHub 
pip install git+https://github.com/coderXcode/mcp-forge.git

# From PyPI (in progress)
pip install mcp-forge
pipx install mcp-forge
```

### Commands

```bash
forge connect --url http://localhost:8000 --token <token>   # save connection
forge status                                                  # list all projects
forge analyze 1                                               # trigger analysis
forge generate 1 --lang python_fastmcp                       # generate MCP server
forge chat 1 "add rate limiting to all tools"                # chat with agent
forge logs 1 --tail 50                                        # coloured log tail
forge plugin install                                          # write claude_desktop_config.json
forge plugin status                                           # verify config
```

---

## 🐳 Docker Commands

```bash
docker compose up -d              # start all services
docker compose up -d --build      # rebuild after code changes
docker logs mcp_forge_app -f      # app logs
docker logs mcp_forge_mcp -f      # MCP server logs
docker compose down               # stop everything
docker compose down -v            # stop + wipe volumes (resets DB)
docker compose restart            # restart after .env changes
```

---

## 🗑️ Resetting the Database

```bash
# Wipe all rows (schema preserved)
docker exec mcp_forge_app python clear_db.py --yes

# Drop and recreate all tables
docker exec mcp_forge_app python clear_db.py --drop --yes
```

> Or `docker compose down -v && docker compose up -d` for a complete reset including volumes.

---

## ⚙️ Configuration Reference

All settings live in `.env` and can also be edited from the **Config** page in the dashboard.

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
| `GITHUB_TOKEN` | — | PAT for private repo ingestion |
| `DB_URL` | SQLite `./data/mcp_forge.db` | Database (SQLite or PostgreSQL) |
| `MCP_AUTH_TOKEN` | `change-me-mcp-secret` | Auth token for Claude / Codex — **change this** |
| `MCP_SERVER_PORT` | `8001` | MCP SSE server port |
| `OUTPUT_DIR` | `./generated` | Where generated MCP files are written |
| `ENABLE_GIT_SNAPSHOTS` | `false` | Auto-commit each snapshot to git |
| `ENABLE_LIVE_PROBING` | `true` | Allow live URL probing |
| `ENABLE_SECURITY_AUDIT` | `true` | Scan generated code for security issues |
| `SECRET_KEY` | auto | FastAPI session secret |
| `DEBUG` | `false` | Enable uvicorn reload and verbose logs |

---

## 🗂️ Project Structure

```
.
├── main.py                        # FastAPI entry point
├── config.py                      # Settings (pydantic-settings)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml                 # forge CLI package
├── .env                           # Your secrets (gitignored)
├── .env.example                   # Template
├── .mcp.json                      # Claude Code plugin manifest
├── mnt/                           # Drop local project folders here
│
├── forge_cli/                     # forge CLI source
│   └── main.py
│
├── mcp_server/
│   └── server.py                  # FastMCP server (11 tools + 2 resources)
│
├── plugins/
│   ├── codex-plugin.yaml          # Codex marketplace manifest
│   ├── claude_desktop_config.json # Claude Desktop config template (stdio)
│   └── claude_desktop_config_sse.json  # Claude Desktop config template (SSE)
│
├── api/routes/                    # REST API
│   ├── projects.py
│   ├── chat.py
│   ├── generate.py
│   ├── snapshots.py
│   ├── tests.py
│   ├── logs.py
│   └── config_routes.py
│
├── core/
│   ├── llm/local_provider.py      # HuggingFace 4-bit NF4 singleton
│   ├── analyzer/                  # OpenAPI, AST, live prober, GitHub fetcher
│   ├── generator/                 # Jinja2 + LLM engine, validator, templates
│   ├── tester/                    # AI test writer + pytest runner
│   └── versioner/snapshot.py      # Snapshot create/rollback/diff
│
├── agent/
│   ├── chat.py                    # ForgeAgent — multi-LLM stateful chat
│   └── memory.py                  # Project context assembler
│
├── db/
│   ├── database.py
│   └── models.py
│
└── dashboard/
    ├── static/
    └── templates/                 # Jinja2 + HTMX UI
```

---

## 🛠️ Development (without Docker)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

uvicorn main:app --reload --port 8000   # web app
python mcp_server/server.py             # MCP server (separate terminal)
```

---

## 📝 Notes

- **No API key needed to start** — the dashboard loads without keys. Keys are only required when you trigger analysis or generation.
- **SQLite by default** — stored in `data/mcp_forge.db`. Switch to PostgreSQL by setting `DB_URL` in `.env`.
- **Generated files** are stored in both the `generated/` volume and database snapshots — they survive container restarts.
- **MCP server transport** — SSE when running in Docker (port 8001), stdio when run directly.
- **Full setup guide** → see [user_manual.md](user_manual.md)
