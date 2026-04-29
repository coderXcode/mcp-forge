"""
Test case generator.
Uses the LLM to generate unit tests for the MCP server,
or reads existing test files from the source repo.
"""
from __future__ import annotations

import json
import re
from config import get_settings

TEST_PROMPT = """You are an expert software tester writing HTTP integration tests against a REST API backend.

The MCP server code below is a PROXY wrapper — it shows you the API's endpoints, paths, and payload shapes.
Your tests will run directly against the backend REST API at BASE_URL.
You do NOT test the MCP server itself — you test the underlying REST API endpoints listed in the server code.

==== STRICT RULES ====
1. Use httpx.AsyncClient to make HTTP requests — NO imports from server code, NO mocking.
2. BASE_URL = os.getenv("BASE_URL", "http://localhost:8000") — every request goes here.
3. Every test must be `async def test_...()` — do NOT add @pytest.mark.asyncio (auto mode is active).
4. Return ONLY raw Python code — no markdown fences, no prose, no triple backticks.
======================

==== HOW TO WRITE SAFE ASSERTIONS ====

You do NOT know the exact behavior of the backend — write FLEXIBLE assertions:

STATUS CODES:
  ✅ POST (create):   assert response.status_code in (200, 201)
  ✅ GET (found):     assert response.status_code == 200
  ✅ PATCH/PUT:       assert response.status_code in (200, 204)
  ✅ DELETE:          assert response.status_code in (200, 204)
  ✅ Not found:       assert response.status_code in (404, 422)
  ✅ Invalid input:   assert response.status_code in (400, 422)
  ❌ NEVER assert exact 201 unless you are 100% certain
  ❌ NEVER assert exact 404 unless you are 100% certain

RESPONSE BODY:
  ✅ For object responses: assert isinstance(response.json(), dict) — that is enough
  ✅ For list responses: assert isinstance(response.json(), list) — that is enough
  ❌ NEVER assert that a specific key exists in the response (e.g. do NOT write `assert "completion_notes" in data`)
     unless that exact key name is explicitly visible in the MCP server code below.
  ❌ NEVER assert specific field values
  ❌ For /stats or /summary endpoints: ONLY assert isinstance(data, dict) — never guess key names like
     "total_tasks", "status_counts", "priority_counts". The actual keys are unknown to you.

STATEFUL TESTS (create-then-read pattern):
  ✅ To test GET/PATCH/DELETE/POST-action by ID: first POST to create, extract ID from response, then use it
  ✅ Use a helper fixture or inline create step — never hardcode IDs like "9999"
  ✅ For action endpoints (e.g. POST /tasks/{{id}}/complete): assert status in (200, 201) and isinstance(data, dict)
     — do NOT assert any specific keys like "completion_notes" or "completed_at" in the response

FILTER PARAMETERS:
  ✅ Only use query parameter names that EXACTLY match the server code
  ✅ For filter values: create a resource with a specific value, then filter by the EXACT same value you used
     when creating — this guarantees the value is valid and accepted by the backend
  ✅ Use only enum values that appear in the server code or its imports (e.g. look for Enum class definitions)
  ❌ Do NOT assume status values like "pending" or "active" — only use values explicitly shown in the code
  ❌ Do NOT invent query parameters that are not in the server code

==== REQUIRED FILE STRUCTURE ====

import httpx
import os

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


async def test_health():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10) as client:
        r = await client.get("/health")
        assert r.status_code == 200


async def test_list_items_returns_list():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10) as client:
        r = await client.get("/items")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


async def test_create_item():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10) as client:
        r = await client.post("/items", json={{"title": "Test item"}})
        assert r.status_code in (200, 201)
        data = r.json()
        assert isinstance(data, dict)


async def test_get_item_by_id():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10) as client:
        # Create first
        create_r = await client.post("/items", json={{"title": "Fetch me"}})
        assert create_r.status_code in (200, 201)
        item_id = create_r.json().get("id") or create_r.json().get("_id")
        # Then fetch
        r = await client.get(f"/items/{{item_id}}")
        assert r.status_code == 200


async def test_get_nonexistent_item():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10) as client:
        r = await client.get("/items/nonexistent-id-that-does-not-exist")
        assert r.status_code in (404, 422)

==== MCP SERVER CODE (shows API endpoints, paths, payload shapes) ====
{server_code}

{source_files_section}
PROJECT NAME: {project_name}

Write comprehensive tests for ALL endpoints in the server code above.
Follow the patterns shown. Raw Python only:
"""


class TestGenerator:
    """Generate test cases for a generated MCP server."""

    async def generate_from_code(
        self,
        server_code: str,
        analysis: dict,
        project_name: str,
        source_files: dict[str, str] | None = None,
    ) -> str:
        """Generate pytest test file content from the server code."""
        # Build a section with the original source files if provided
        source_files_section = ""
        if source_files:
            snippets = []
            for fname, content in list(source_files.items())[:5]:
                snippets.append(f"### {fname}\n{content[:3000]}")
            if snippets:
                source_files_section = (
                    "==== ORIGINAL SOURCE FILES (authoritative — use these for exact enum values, "
                    "field names, status codes) ====\n"
                    + "\n\n".join(snippets)
                    + "\n===================================\n"
                )

        prompt = TEST_PROMPT.format(
            server_code=server_code[:20_000],
            project_name=project_name,
            source_files_section=source_files_section,
        )

        return await self._call_llm(prompt)

    async def generate_from_docs(self, docs: dict[str, str], project_name: str) -> str:
        """Extract test cases mentioned in documentation."""
        docs_text = "\n\n".join(
            f"### {fname}\n{content[:5000]}"
            for fname, content in list(docs.items())[:5]
        )

        prompt = f"""Extract test cases from this documentation for project: {project_name}

Convert any mentioned examples, test cases, or API usage patterns into pytest tests.
Return ONLY Python pytest code.

DOCUMENTATION:
{docs_text}
"""
        return await self._call_llm(prompt)

    async def _call_llm(self, prompt: str) -> str:
        settings = get_settings()
        provider = settings.llm_provider

        try:
            if provider == "gemini":
                import asyncio
                from google import genai
                client = genai.Client(api_key=settings.gemini_api_key)
                resp = await asyncio.to_thread(
                    client.models.generate_content,
                    model=settings.gemini_model,
                    contents=prompt,
                )
                code = resp.text
                import re as _re
                code = _re.sub(r'<think>.*?</think>', '', code, flags=_re.DOTALL).strip()
            elif provider == "anthropic":
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
                msg = await client.messages.create(
                    model=settings.anthropic_model,
                    max_tokens=6144,
                    messages=[{"role": "user", "content": prompt}],
                )
                code = msg.content[0].text
            elif provider == "local":
                from core.llm.local_provider import generate
                code = await generate(prompt, max_new_tokens=6144)
            else:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=settings.openai_api_key)
                resp = await client.chat.completions.create(
                    model=settings.openai_model,
                    messages=[{"role": "user", "content": prompt}],
                )
                code = resp.choices[0].message.content
        except Exception as e:
            return f"# Test generation failed: {e}\n# Please add tests manually."

        # Strip markdown fences
        code = re.sub(r"^```python\n|^```\n|```$", "", code, flags=re.MULTILINE).strip()
        return code
