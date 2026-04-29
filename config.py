"""
Central configuration — loaded from .env by pydantic-settings.
All modules import `settings` from here; never read os.environ directly.
"""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "MCP Forge"
    app_env: Literal["development", "production"] = "development"
    secret_key: str = secrets.token_hex(32)
    port: int = 8000
    debug: bool = True
    log_level: str = "INFO"

    # ── Database ─────────────────────────────────────────────────────────────
    db_url: str = "sqlite+aiosqlite:///./data/mcp_forge.db"

    # ── LLM Provider ─────────────────────────────────────────────────────────
    llm_provider: Literal["gemini", "anthropic", "openai", "local"] = "gemini"

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-pro"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Local HuggingFace model
    local_model: str = "Qwen/Qwen2.5-Coder-14B-Instruct"
    local_model_device: str = "auto"
    local_model_load_in_4bit: bool = True
    # Proxy to an external model server (set when running inside Docker on macOS).
    # e.g. http://host.docker.internal:8005  (run scripts/run_model_local.py on the host)
    local_model_host: str = ""       # empty = load model in-process
    local_model_port: int = 8005     # port for scripts/run_model_local.py

    # ── GitHub ────────────────────────────────────────────────────────────────
    github_token: str = ""

    # ── Security ─────────────────────────────────────────────────────────────
    encryption_key: str = ""  # Fernet key — auto-generated on first run

    # ── MCP Server ───────────────────────────────────────────────────────────
    mcp_server_host: str = "localhost"
    mcp_server_port: int = 8001
    mcp_auth_token: str = "change-me-mcp-secret"

    # ── Output ───────────────────────────────────────────────────────────────
    output_dir: Path = Path("./generated")

    # ── CORS ─────────────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:8000"

    # ── Features ─────────────────────────────────────────────────────────────
    enable_live_probing: bool = True
    enable_security_audit: bool = True
    enable_git_snapshots: bool = False

    # ── Redis (optional) ─────────────────────────────────────────────────────
    redis_url: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def active_llm_key(self) -> str:
        """Return the API key for the currently active LLM provider."""
        mapping = {
            "gemini": self.gemini_api_key,
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "local": "",
        }
        return mapping.get(self.llm_provider, "")

    @property
    def active_llm_model(self) -> str:
        mapping = {
            "gemini": self.gemini_model,
            "anthropic": self.anthropic_model,
            "openai": self.openai_model,
            "local": self.local_model,
        }
        return mapping.get(self.llm_provider, "")

    def ensure_dirs(self) -> None:
        """Create required directories if they don't exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        Path("./data").mkdir(parents=True, exist_ok=True)
        Path("./logs").mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
