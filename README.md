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
  <img src="https://img.shields.io/pypi/v/mcp-forger?label=pypi%20install" />
</p>

```bash
pip install mcp-forger   # CLI + Claude Desktop plugin installer
```

---

MCP Forge is a self-hosted AI agent that analyzes your existing app (via OpenAPI spec, GitHub repo, live URL, or local code) and generates a production-ready MCP server that **Claude Desktop, Claude Code**, or any MCP client can use directly.

---

## ✨ Features

| Category | Highlights |
|---|---|
| **Source ingestion** | OpenAPI/Swagger URL · GitHub repo · Live URL probing · Local folder (`mnt/`) · File upload · Manual description |
| **AI agent** | Multi-LLM (Gemini · Anthropic · OpenAI · local HuggingFace) · per-project chat · clarification Q&A loop |
| **Code generation** | Python FastMCP · Node.js · Go · Generic · LLM polish pass · security audit |
| **Versioning** | Snapshot on every generation · one-click rollback · optional git commits |
| **Testing** | AI-generated pytest cases · in-container runner · full test history |
| **Dashboard** | Real-time logs · 6-tab project view · editable `.env` config from the browser |
| **Claude / Codex** | Claude Desktop plugin (stdio + SSE) · Claude Code plugin (marketplace + `.mcp.json`) · Codex plugin · `forge` CLI |

---

## 🚀 Quick Start

### 1 — Get the code & configure

```bash
git clone https://github.com/coderXcode/mcp-forge.git
cd mcp-forge
cp .env.example .env
```

Open `.env` and fill in at least one LLM key or use local model as listed in below sections:

```env
LLM_PROVIDER=gemini          # or: anthropic | openai | local
GEMINI_API_KEY=your-key-here
MCP_AUTH_TOKEN=change-me-to-something-secret   # auth token for Claude/Codex
```

> **Free option:** Gemini has a free tier at [aistudio.google.com](https://aistudio.google.com).

### 2 — Start

```bash
docker compose up -d
```

| Service | URL |
|---|---|
| 🌐 Dashboard | http://localhost:8000 |
| 🔌 MCP endpoint | http://localhost:8001/sse |

### 3 — Open the dashboard

Visit **http://localhost:8000** → click **+ New Project** to begin.

---

## 🤖 Integrate with Claude Desktop / Claude Code

> For full step-by-step instructions see **[user_manual.md](user_manual.md)**.

**Claude Desktop (one-command):**
```powershell
# Windows
.\scripts\install_claude_plugin.ps1

# macOS / Linux
bash scripts/install_claude_plugin.sh
```

**Claude Code (one-liner):**
```
/plugin marketplace add coderXcode/mcp-forge
```

**forge CLI:**
```bash
pip install mcpforge
```

---

## 🖥️ Local Model (No API Key)

Run entirely offline using any HuggingFace model — no API key required. Requires an NVIDIA GPU.

```env
LLM_PROVIDER=local
LOCAL_MODEL=Qwen/Qwen2.5-Coder-14B-Instruct   # or any HuggingFace model ID
LOCAL_MODEL_DEVICE=auto
LOCAL_MODEL_LOAD_IN_4BIT=true                  # 4-bit NF4 quantization — fits on 8 GB VRAM
```

Rebuild once after changing these settings:

```bash
docker compose down && docker compose build && docker compose up -d
```

The model downloads from HuggingFace on first use and is cached for future runs. You can replace `LOCAL_MODEL` with **any HuggingFace model** that supports chat/instruction format — some well-tested options:

| Model | VRAM (4-bit) | Notes |
|---|---|---|
| `Qwen/Qwen2.5-Coder-7B-Instruct` | ~4 GB | Lightest option |
| `Qwen/Qwen2.5-Coder-14B-Instruct` | ~8 GB | **Recommended** |
| `deepseek-ai/deepseek-coder-v2-lite-instruct` | ~8 GB | Strong alternative |
| `Qwen/Qwen2.5-Coder-32B-Instruct` | ~18 GB | Best quality |
| `mistralai/Mistral-7B-Instruct-v0.3` | ~4 GB | General purpose |

> Set `LOCAL_MODEL_LOAD_IN_4BIT=false` and `LOCAL_MODEL_DEVICE=cpu` to run on CPU (slow but no GPU needed).

See [user_manual.md](user_manual.md#7-local-huggingface-model-no-api-key) for full setup details including NVIDIA Container Toolkit requirements.

---

## ⚙️ Key Configuration

All settings live in `.env` (also editable live from the dashboard **Config** page).

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` \| `anthropic` \| `openai` \| `local` |
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `ANTHROPIC_API_KEY` | — | Anthropic Claude API key |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `MCP_AUTH_TOKEN` | `change-me` | Auth token for Claude / Codex — **change this** |
| `GITHUB_TOKEN` | — | PAT for private GitHub repos |
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

## 📖 Documentation

| Document | What's in it |
|---|---|
| **[user_manual.md](user_manual.md)** | Full setup · Claude Desktop · Claude Code · Codex · forge CLI · troubleshooting · architecture |

---

## 📝 License

MIT
