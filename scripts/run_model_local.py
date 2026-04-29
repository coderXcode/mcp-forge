#!/usr/bin/env python3
"""
Local model server — run this OUTSIDE Docker on macOS (or any host with a GPU).

 - Loads the HuggingFace model natively so it can use Apple MPS on M-series Macs,
   CUDA on Linux/Windows, or CPU as a fallback.
 - Saves model weights to ./cache/huggingface — the SAME directory Docker mounts,
   so the download is only needed once.
 - Starts a tiny HTTP server on port 8005 (configurable).
 - MCP Forge inside Docker connects back to it via host.docker.internal:8005.
   Set LOCAL_MODEL_HOST=http://host.docker.internal:8005 in .env and restart Docker.

Quick start (from project root):
    pip install transformers torch accelerate fastapi uvicorn
    python scripts/run_model_local.py

Override model or port:
    LOCAL_MODEL=Qwen/Qwen2.5-Coder-7B-Instruct LOCAL_MODEL_PORT=8005 python scripts/run_model_local.py
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# ── Point HuggingFace cache at the shared ./cache dir (also mounted in Docker) ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR    = PROJECT_ROOT / "cache" / "huggingface"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME",            str(CACHE_DIR))
os.environ.setdefault("TRANSFORMERS_CACHE", str(CACHE_DIR / "hub"))
# MPS: remove the allocator high-watermark that rejects large (>8 GB) single allocations.
# Without this, loading a 7B/14B model on MPS raises "Invalid buffer size".
os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")

MODEL_NAME = os.getenv("LOCAL_MODEL", "")   # empty = auto-select based on RAM
PORT       = int(os.getenv("LOCAL_MODEL_PORT", "8005"))

# Model options keyed by minimum RAM (GB) required
_MODEL_BY_RAM = [
    (32, "Qwen/Qwen2.5-Coder-14B-Instruct"),   # float16: ~28 GB weights + OS overhead
    (20, "Qwen/Qwen2.5-Coder-7B-Instruct"),    # float16: ~14 GB weights + OS overhead
    (0,  "Qwen/Qwen2.5-Coder-3B-Instruct"),    # float16:  ~6 GB weights + overhead
]


def _total_ram_gb() -> float:
    """Return total system RAM in GB (macOS + Linux)."""
    import subprocess, platform
    try:
        if platform.system() == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip()
            return int(out) / 1e9
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1e6
    except Exception:
        pass
    return 16.0   # safe fallback


def _pick_model() -> str:
    if MODEL_NAME:
        return MODEL_NAME
    ram = _total_ram_gb()
    for min_ram, name in _MODEL_BY_RAM:
        if ram >= min_ram:
            return name
    return _MODEL_BY_RAM[-1][1]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("local-model-server")

_model     = None
_tokenizer = None
_device: str = "cpu"


# ── Model loading ─────────────────────────────────────────────────────────────

def load_model() -> None:
    global _model, _tokenizer, _device

    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
    except ImportError:
        sys.exit(
            "\nMissing dependencies. Install them and try again:\n"
            "  pip install transformers torch accelerate fastapi uvicorn\n"
        )

    # Auto-select model based on available RAM if not overridden
    model_name = _pick_model()
    ram_gb     = _total_ram_gb()

    # Pick best available device
    if torch.backends.mps.is_available():
        _device = "mps"
        dtype   = torch.float16
        logger.info("Apple Silicon MPS detected — model will run on MPS (GPU-accelerated)")
    elif torch.cuda.is_available():
        _device = "cuda"
        dtype   = torch.float16
        logger.info("CUDA GPU detected — model will run on GPU")
    else:
        _device = "cpu"
        dtype   = torch.float32
        logger.info("No GPU found — model will run on CPU (slow but functional)")

    logger.info("System RAM : %.1f GB", ram_gb)
    logger.info("Model      : %s", model_name)
    logger.info("HuggingFace cache : %s", CACHE_DIR)

    # ── Resumable download via snapshot_download ──────────────────────────────
    logger.info("Downloading / verifying model files… (resumable — safe to interrupt)")
    from huggingface_hub import snapshot_download
    local_model_dir = snapshot_download(
        model_name,
        cache_dir=str(CACHE_DIR),
        ignore_patterns=["*.msgpack", "*.h5", "flax_model*"],
    )
    logger.info("Model files ready at %s", local_model_dir)

    logger.info("Loading tokenizer…")
    _tokenizer = AutoTokenizer.from_pretrained(local_model_dir, trust_remote_code=True)

    logger.info("Loading model weights…")
    if _device == "mps":
        # device_map="mps" triggers caching_allocator_warmup in transformers which tries
        # to pre-allocate the full model as one contiguous buffer — fails on MPS even with
        # PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0.
        # Fix: load onto CPU first, then .to("mps").
        # On Apple Silicon, CPU and MPS share unified memory — no physical copy occurs.
        _model = AutoModelForCausalLM.from_pretrained(
            local_model_dir,
            trust_remote_code=True,
            torch_dtype=dtype,
            low_cpu_mem_usage=True,
        )
        logger.info("Moving model to MPS (unified memory — no copy on Apple Silicon)…")
        _model = _model.to("mps")
    else:
        _model = AutoModelForCausalLM.from_pretrained(
            local_model_dir,
            trust_remote_code=True,
            device_map=_device,
            torch_dtype=dtype,
            low_cpu_mem_usage=True,
        )
    logger.info("Model %s ready on %s", model_name, _device)


# ── FastAPI server ─────────────────────────────────────────────────────────────

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="MCP Forge Local Model Server")


class GenerateRequest(BaseModel):
    prompt: str | None          = None
    messages: list[dict] | None = None
    max_new_tokens: int         = 4096


@app.get("/health")
def health() -> dict:
    """Status endpoint polled by MCP Forge inside Docker."""
    if _model is None:
        return {"state": "not_loaded", "model": None, "vram_gb": None}

    if _device == "mps":
        vram = "Apple Silicon MPS (unified memory)"
    elif _device == "cuda":
        try:
            import torch
            alloc    = torch.cuda.memory_allocated() / 1e9
            reserved = torch.cuda.memory_reserved()  / 1e9
            vram = f"{alloc:.1f} GB allocated / {reserved:.1f} GB reserved (CUDA)"
        except Exception:
            vram = "CUDA"
    else:
        vram = "CPU"

    return {"state": "loaded", "model": MODEL_NAME, "device": _device, "vram_gb": vram}


@app.post("/generate")
def generate(req: GenerateRequest) -> dict:
    if _model is None:
        raise HTTPException(503, "Model not loaded yet")

    import torch

    if req.messages:
        text = _tokenizer.apply_chat_template(
            req.messages, tokenize=False, add_generation_prompt=True
        )
    elif req.prompt:
        text = req.prompt
    else:
        raise HTTPException(400, "Provide either 'prompt' or 'messages'")

    dev    = next(_model.parameters()).device
    inputs = _tokenizer(text, return_tensors="pt").to(dev)
    with torch.no_grad():
        output = _model.generate(**inputs, max_new_tokens=req.max_new_tokens, do_sample=False)
    new_tokens = output[0][inputs["input_ids"].shape[1]:]
    return {"text": _tokenizer.decode(new_tokens, skip_special_tokens=True)}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("=== MCP Forge Local Model Server ===")
    logger.info("Model  : %s", MODEL_NAME)
    logger.info("Port   : %d", PORT)
    logger.info("Cache  : %s", CACHE_DIR)
    load_model()
    logger.info(
        "Listening on 0.0.0.0:%d — inside Docker reach it via host.docker.internal:%d",
        PORT, PORT,
    )
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
