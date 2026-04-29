"""
LLM-powered code analyzer — language agnostic.
Sends code files to the configured LLM and asks it to:
  - Identify language & framework
  - Extract all API endpoints / functions
  - Suggest Tool vs Resource classification for each
  - Identify auth patterns
This approach works for ANY language without tree-sitter grammar files.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from config import get_settings


ANALYZE_PROMPT = """You are an expert API analyzer for MCP (Model Context Protocol) conversion.

Analyze the following code files and extract:
1. Programming language and framework
2. All API endpoints / RPC functions / public methods
3. For each endpoint: method, path/name, parameters, return type, description
4. Authentication mechanisms used
5. For each endpoint, classify as one of:
   - "tool": performs an action, has side effects, takes meaningful parameters (POST/PUT/DELETE)
   - "resource": reads/fetches data, can be URI-addressed (GET)
   - "prompt": generates or formats text for the user

Return a JSON object with this exact structure:
{
  "language": "python|javascript|go|java|...",
  "framework": "fastapi|express|django|gin|...",
  "auth_info": {"type": "bearer|api_key|basic|none", "details": "..."},
  "endpoints": [
    {
      "name": "function_or_operation_name",
      "path": "/api/path or function_name",
      "method": "GET|POST|PUT|DELETE|FUNCTION",
      "description": "what this does",
      "parameters": [{"name": "x", "type": "string", "required": true, "description": "..."}],
      "returns": "return type description",
      "mcp_type": "tool|resource|prompt",
      "tags": []
    }
  ],
  "schemas": {},
  "notes": "anything important the MCP generator should know"
}

Only return the JSON, no explanation.

CODE FILES:
{code}
"""


class ASTAnalyzer:
    """
    Language-agnostic analyzer that uses the LLM to understand any codebase.
    Accepts file paths (local), raw code strings, or a zip archive.
    """

    def __init__(self, files: dict[str, str] | None = None):
        """
        files: dict of {filename: content}
        """
        self._files = files or {}

    def add_file(self, filename: str, content: str) -> None:
        self._files[filename] = content

    async def analyze(self) -> dict:
        """Return normalized analysis result using LLM understanding."""
        if not self._files:
            return self._empty_result()

        code_block = self._format_code_block()
        response_text = await self._call_llm(code_block)
        return self._parse_response(response_text)

    # ── LLM call ─────────────────────────────────────────────────────────────

    async def _call_llm(self, code: str) -> str:
        # Use % substitution to avoid KeyError from { } in the prompt template
        prompt = ANALYZE_PROMPT.replace("{code}", code[:60_000])

        settings = get_settings()
        provider = settings.llm_provider
        if provider == "gemini":
            if not settings.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is not set. Add it to your .env file and restart.")
            return await self._call_gemini(prompt)
        elif provider == "anthropic":
            if not settings.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY is not set. Add it to your .env file and restart.")
            return await self._call_anthropic(prompt)
        elif provider == "local":
            return await self._call_local(prompt)
        else:
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY is not set. Add it to your .env file and restart.")
            return await self._call_openai(prompt)

    async def _call_gemini(self, prompt: str) -> str:
        settings = get_settings()
        import asyncio
        from google import genai
        client = genai.Client(api_key=settings.gemini_api_key)
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=settings.gemini_model,
            contents=prompt,
        )
        return response.text

    async def _call_anthropic(self, prompt: str) -> str:
        settings = get_settings()
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    async def _call_openai(self, prompt: str) -> str:
        settings = get_settings()
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content

    async def _call_local(self, prompt: str) -> str:
        from core.llm.local_provider import generate
        return await generate(prompt)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _format_code_block(self) -> str:
        blocks = []
        for fname, content in self._files.items():
            ext = Path(fname).suffix
            lang_hint = {
                ".py": "python", ".js": "javascript", ".ts": "typescript",
                ".go": "go", ".java": "java", ".rb": "ruby", ".rs": "rust",
                ".cs": "csharp", ".php": "php",
            }.get(ext, "")
            blocks.append(f"### FILE: {fname}\n```{lang_hint}\n{content[:10_000]}\n```")
        return "\n\n".join(blocks)

    def _parse_response(self, text: str) -> dict:
        # Strip thinking blocks (Gemini 2.5 wraps reasoning in <think>...</think>)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        # Strip markdown code fences if present
        text = re.sub(r"```(?:json)?\n?", "", text).strip().rstrip("`").strip()
        # If there's still non-JSON preamble, find the first {
        brace_idx = text.find("{")
        if brace_idx > 0:
            text = text[brace_idx:]
        try:
            data = json.loads(text)
            data.setdefault("language", "unknown")
            data.setdefault("framework", "unknown")
            data.setdefault("auth_info", {})
            data.setdefault("endpoints", [])
            data.setdefault("schemas", {})
            data.setdefault("base_url", "")
            return data
        except json.JSONDecodeError:
            return {**self._empty_result(), "raw_response": text}

    @staticmethod
    def _empty_result() -> dict:
        return {
            "language": "unknown",
            "framework": "unknown",
            "auth_info": {},
            "endpoints": [],
            "schemas": {},
            "base_url": "",
            "notes": "",
        }
