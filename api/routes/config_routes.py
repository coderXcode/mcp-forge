"""
Config editor routes — read and write the .env file from the dashboard.
Changes are applied immediately (settings object is reloaded).
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/config", tags=["config"])

ENV_FILE = Path(".env")
ENV_EXAMPLE = Path(".env.example")


class EnvVar(BaseModel):
    key: str
    value: str


class EnvUpdate(BaseModel):
    vars: list[EnvVar]


@router.get("/")
async def get_config():
    """Return all .env variables (masks sensitive values)."""
    env_vars = _read_env_file()
    masked = {}
    for key, value in env_vars.items():
        masked[key] = _mask_value(key, value)
    return {"vars": masked, "file_exists": ENV_FILE.exists()}


@router.get("/raw")
async def get_raw_config():
    """Return the raw .env file content (with masking for sensitive keys)."""
    if not ENV_FILE.exists():
        # Return example file as template
        if ENV_EXAMPLE.exists():
            return {"content": ENV_EXAMPLE.read_text(), "is_template": True}
        return {"content": "", "is_template": False}
    return {"content": ENV_FILE.read_text(), "is_template": False}


@router.put("/")
async def update_config(payload: EnvUpdate):
    """Update specific .env variables. Creates .env if it doesn't exist."""
    env_vars = _read_env_file()

    for item in payload.vars:
        key = item.key.strip().upper()
        if not re.match(r"^[A-Z][A-Z0-9_]*$", key):
            raise HTTPException(400, f"Invalid env var name: {key}")
        env_vars[key] = item.value

    _write_env_file(env_vars)

    # Reload settings
    from config import get_settings
    get_settings.cache_clear()

    return {"ok": True, "updated": [v.key for v in payload.vars]}


@router.put("/raw")
async def update_raw_config(payload: dict):
    """Overwrite .env with raw text content from the editor."""
    content = payload.get("content", "")
    if not isinstance(content, str):
        raise HTTPException(400, "content must be a string")
    ENV_FILE.write_text(content)
    # Reload settings so changes take effect immediately
    from config import get_settings
    get_settings.cache_clear()
    return {"ok": True}


@router.post("/reset")
async def reset_from_example():
    """Copy .env.example → .env (useful for first-time setup)."""
    if not ENV_EXAMPLE.exists():
        raise HTTPException(404, ".env.example not found")
    content = ENV_EXAMPLE.read_text()
    ENV_FILE.write_text(content)
    return {"ok": True}


@router.get("/local-model/status")
async def local_model_status():
    """Return whether the local HuggingFace model is loaded in memory."""
    from core.llm.local_provider import get_status
    return get_status()


@router.post("/local-model/load")
async def local_model_load():
    """
    Trigger eager loading of the local model in the background.
    - Proxy mode (LOCAL_MODEL_HOST set): tests the connection to the external server.
    - Normal mode: fires off background loading inside Docker.
    Returns immediately; poll /local-model/status to watch progress.
    """
    from config import get_settings

    settings = get_settings()

    # ── Proxy mode: test connection to the external model server ─────────────
    if settings.local_model_host:
        from core.llm.local_provider import get_status
        status = get_status()
        if status.get("state") == "loaded":
            return {"ok": True, "message": "Connected to local model server.", "proxy": True}
        raise HTTPException(
            503,
            detail=(
                f"Cannot reach local model server at {settings.local_model_host}. "
                "Run 'python scripts/run_model_local.py' on your machine first."
            ),
        )

    # ── Normal (in-process Docker) mode ──────────────────────────────────────
    env_vars = _read_env_file()
    changed = False
    if env_vars.get("LLM_PROVIDER", "").lower() != "local":
        env_vars["LLM_PROVIDER"] = "local"
        changed = True

    # On Apple Silicon / no CUDA: switch device to mps and disable 4-bit
    import platform
    is_mac = platform.system() == "Darwin"
    if is_mac:
        try:
            import torch
            has_cuda = torch.cuda.is_available()
        except Exception:
            has_cuda = False
        if not has_cuda:
            if env_vars.get("LOCAL_MODEL_DEVICE", "auto") not in ("mps", "cpu"):
                env_vars["LOCAL_MODEL_DEVICE"] = "mps"
                changed = True
            if env_vars.get("LOCAL_MODEL_LOAD_IN_4BIT", "true").lower() == "true":
                env_vars["LOCAL_MODEL_LOAD_IN_4BIT"] = "false"
                changed = True

    if changed:
        _write_env_file(env_vars)
        get_settings.cache_clear()

    settings = get_settings()
    import asyncio
    from core.llm.local_provider import _ensure_loaded
    asyncio.create_task(_ensure_loaded())
    return {"ok": True, "message": f"Loading {settings.local_model} in background…"}

def _read_env_file() -> dict[str, str]:
    if not ENV_FILE.exists():
        if ENV_EXAMPLE.exists():
            return _parse_env_text(ENV_EXAMPLE.read_text())
        return {}
    return _parse_env_text(ENV_FILE.read_text())


def _parse_env_text(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            result[key] = value
    return result


def _write_env_file(vars: dict[str, str]) -> None:
    lines = []
    existing_keys = set()

    # Preserve comments and structure from existing file
    source = ENV_FILE if ENV_FILE.exists() else ENV_EXAMPLE
    if source.exists():
        for line in source.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=")[0].strip()
                if key in vars:
                    lines.append(f'{key}={vars[key]}')
                    existing_keys.add(key)
                else:
                    lines.append(line)
            else:
                lines.append(line)

    # Append any new keys not in original file
    for key, value in vars.items():
        if key not in existing_keys:
            lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(lines) + "\n")


# Exact key names that should be masked in the UI (not substrings)
SENSITIVE_KEYS = {
    "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
    "GITHUB_TOKEN", "ENCRYPTION_KEY", "MCP_AUTH_TOKEN",
}


def _mask_value(key: str, value: str) -> str:
    if key.upper() in SENSITIVE_KEYS and len(value) > 4:
        return value[:4] + "****"
    return value
