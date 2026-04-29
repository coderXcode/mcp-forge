"""
Local HuggingFace model provider.

Loaded lazily on first use and cached as a singleton so the model is only
downloaded/loaded once per container lifetime.

Controlled by .env:
    LOCAL_MODEL=Qwen/Qwen2.5-Coder-14B-Instruct
    LOCAL_MODEL_DEVICE=auto          # auto | cuda | cpu
    LOCAL_MODEL_LOAD_IN_4BIT=true    # 4-bit quantisation (fits 14B in ~7 GB VRAM)
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

_model = None
_tokenizer = None
_loading = False   # True while model is being loaded in background
_load_error: str | None = None
_lock = asyncio.Lock()


def _proxy_host() -> str:
    """Return LOCAL_MODEL_HOST if configured (proxy / native-server mode)."""
    try:
        from config import settings
        return (settings.local_model_host or "").rstrip("/")
    except Exception:
        return ""


async def _ensure_loaded() -> None:
    """Load model + tokenizer once; subsequent calls are instant."""
    global _model, _tokenizer, _loading, _load_error

    if _proxy_host():
        return   # model runs in external server — nothing to load in-process

    if _model is not None:
        return

    async with _lock:
        if _model is not None:          # double-checked locking
            return
        _loading = True
        _load_error = None

        from config import settings     # avoid circular import at module level

        model_name = settings.local_model
        load_4bit = settings.local_model_load_in_4bit
        device = settings.local_model_device

        logger.info("Loading local model %s (4bit=%s, device=%s) …", model_name, load_4bit, device)

        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
            import torch

            # Auto-detect best device: cuda > mps (Apple Silicon) > cpu
            if device == "auto":
                if torch.cuda.is_available():
                    device = "cuda"
                elif torch.backends.mps.is_available():
                    device = "mps"
                    logger.info("Apple Silicon MPS detected — using mps device")
                else:
                    device = "cpu"
                    logger.info("No GPU found — falling back to CPU")

            # 4-bit quantisation requires bitsandbytes which needs CUDA — disable on MPS/CPU
            if load_4bit and device != "cuda":
                logger.info("4-bit quantisation requires CUDA — disabling for device=%s", device)
                load_4bit = False

            logger.info("Downloading/loading tokenizer for %s…", model_name)
            _tokenizer = await asyncio.to_thread(
                AutoTokenizer.from_pretrained,
                model_name,
                trust_remote_code=True,
            )
            logger.info("Tokenizer loaded. Now loading model weights (device=%s, 4bit=%s) — this can take a while on first load…", device, load_4bit)

            kwargs: dict = {
                "trust_remote_code": True,
                "device_map": device,
            }

            if load_4bit:
                kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.bfloat16,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4",
                )
            else:
                kwargs["torch_dtype"] = torch.float16 if device in ("cuda", "mps") else torch.float32

            _model = await asyncio.to_thread(
                AutoModelForCausalLM.from_pretrained,
                model_name,
                **kwargs,
            )

            logger.info("Local model %s loaded successfully.", model_name)
            _loading = False

        except ImportError as e:
            _loading = False
            _load_error = "transformers / torch not installed in container. Rebuild with LOCAL deps."
            raise RuntimeError(_load_error) from e
        except Exception as e:
            _loading = False
            _load_error = str(e)
            logger.error("Failed to load local model: %s", e)
            raise


def get_status() -> dict:
    """Return current load state of the local model (no side-effects)."""
    host = _proxy_host()
    if host:
        try:
            import httpx
            r = httpx.get(f"{host}/health", timeout=2.0)
            d = r.json()
            return {**d, "proxy": True}
        except Exception as exc:
            return {
                "state": "proxy_disconnected",
                "model": None,
                "vram_gb": None,
                "proxy": True,
                "warning": (
                    f"Cannot reach local model server at {host}. "
                    "Is 'bash scripts/start_model_server.sh' running on your machine?"
                ),
            }

    # In-process mode — detect GPU availability for UI warnings
    try:
        import torch
        has_gpu = torch.cuda.is_available() or torch.backends.mps.is_available()
    except Exception:
        has_gpu = False

    if _model is None:
        if _loading:
            return {"state": "loading", "model": None, "vram_gb": None, "error": None}
        if _load_error:
            return {"state": "error", "model": None, "vram_gb": None, "error": _load_error}
        warning = None
        if not has_gpu:
            warning = (
                "No GPU detected in this container. "
                "Docker on macOS cannot access Apple MPS — "
                "run scripts/run_model_local.py on your Mac for GPU acceleration."
            )
        return {"state": "not_loaded", "model": None, "vram_gb": None, "warning": warning}
    try:
        import torch
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated() / 1e9
            reserved  = torch.cuda.memory_reserved()  / 1e9
            vram_info = f"{allocated:.1f} GB allocated / {reserved:.1f} GB reserved (CUDA)"
        elif torch.backends.mps.is_available():
            vram_info = "Apple Silicon MPS (unified memory)"
        else:
            vram_info = "CPU only"
    except Exception:
        vram_info = "unknown"
    from config import settings
    return {"state": "loaded", "model": settings.local_model, "vram_gb": vram_info}


async def generate(prompt: str, max_new_tokens: int = 8192) -> str:
    """Run inference with the local model (single-turn). Returns the generated text."""
    host = _proxy_host()
    if host:
        import httpx
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{host}/generate", json={"prompt": prompt, "max_new_tokens": max_new_tokens})
            r.raise_for_status()
            return r.json()["text"]
    await _ensure_loaded()
    messages = [{"role": "user", "content": prompt}]
    return await generate_chat(messages, max_new_tokens=max_new_tokens)


async def generate_chat(messages: list[dict], max_new_tokens: int = 4096) -> str:
    """Run chat inference with the local model using a messages list. Returns the assistant reply."""
    host = _proxy_host()
    if host:
        import httpx
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{host}/generate", json={"messages": messages, "max_new_tokens": max_new_tokens})
            r.raise_for_status()
            return r.json()["text"]
    await _ensure_loaded()

    def _run() -> str:
        import torch
        text = _tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = _tokenizer([text], return_tensors="pt").to(_model.device)

        with torch.no_grad():
            generated_ids = _model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,           # greedy — deterministic, best for code
                pad_token_id=_tokenizer.eos_token_id,
            )

        output_ids = generated_ids[0][len(inputs.input_ids[0]):].tolist()
        return _tokenizer.decode(output_ids, skip_special_tokens=True)

    return await asyncio.to_thread(_run)
