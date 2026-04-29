"""
Multi-LLM chat agent.
Supports Gemini, Anthropic (Claude), and OpenAI.
Maintains per-project conversation history.
Has function calling to trigger forge actions from chat.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from config import get_settings
from db.models import (
    ChatMessage, Clarification, MessageRole, Notification,
    NotificationType, Project
)

# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are MCP Forge Agent — an expert AI assistant that helps developers convert applications into MCP (Model Context Protocol) servers.

You have deep knowledge of:
- MCP protocol (tools, resources, prompts)
- REST API design and OpenAPI specs
- Python (FastMCP), Node.js, Go MCP SDKs
- Code analysis and generation

Your role:
1. Help users convert their existing APIs/apps into MCP servers
2. Ask clarifying questions when something is ambiguous
3. Suggest improvements to the generated MCP code
4. Explain decisions (e.g., why an endpoint is a Tool vs Resource)
5. Help debug issues with generated code

IMPORTANT: Reply with plain conversational text only. Do NOT use XML tags, function call syntax, <execute_function> blocks, or any structured markup in your response. Just answer naturally.
When something is ambiguous, ask ONE clear question at a time.

When you need the user to clarify something specific about an endpoint or conversion decision (e.g. whether /users/export should be a tool vs resource, or what auth scheme to use), wrap your question in a CLARIFICATION block:

[CLARIFICATION]
Your specific question here?
[/CLARIFICATION]

Only use [CLARIFICATION] blocks for genuine decision-blocking questions. Do not use them for general conversation.

Current project context will be injected below.
"""


class ForgeAgent:
    """Stateful chat agent for a specific project."""

    def __init__(self, session: AsyncSession, project: Project):
        self._session = session
        self._project = project
        self._action_callbacks: dict[str, Callable] = {}

    def register_action(self, name: str, fn: Callable) -> None:
        """Register a callable that the agent can invoke via function calling."""
        self._action_callbacks[name] = fn

    async def chat(self, user_message: str, context: dict | None = None) -> dict:
        """
        Send a user message, get agent response.
        Returns: {response, actions_triggered, clarifications}
        """
        # Save user message
        await self._save_message(MessageRole.USER, user_message)

        # Build conversation history
        history = await self._load_history()

        # Build context string
        context_str = self._build_context_string(context or {})

        # Call LLM
        response_text, tool_calls = await self._call_llm(history, context_str)

        # Save assistant response
        await self._save_message(MessageRole.ASSISTANT, response_text, {"tool_calls": tool_calls})

        # Process tool calls
        actions_triggered = []
        for tc in tool_calls:
            result = await self._execute_tool_call(tc)
            actions_triggered.append(result)

        # Check if agent is asking a clarification question
        clarifications = await self._extract_and_save_clarifications(response_text)

        # Create notification if there's a question
        if clarifications:
            await self._create_notification(
                NotificationType.QUESTION,
                "Agent needs clarification",
                clarifications[0]["question"],
                requires_response=True,
            )

        return {
            "response": response_text,
            "actions_triggered": actions_triggered,
            "clarifications": clarifications,
        }

    # ── LLM Dispatch ──────────────────────────────────────────────────────────

    async def _call_llm(
        self, history: list[dict], context: str
    ) -> tuple[str, list[dict]]:
        settings = get_settings()
        provider = settings.llm_provider

        system = SYSTEM_PROMPT
        if context:
            system += f"\n\n## Current Project Context\n{context}"

        if provider == "gemini":
            return await self._call_gemini(history, system)
        elif provider == "anthropic":
            return await self._call_anthropic(history, system)
        elif provider == "local":
            return await self._call_local(history, system)
        else:
            return await self._call_openai(history, system)

    async def _call_gemini(self, history: list[dict], system: str) -> tuple[str, list]:
        settings = get_settings()
        import asyncio
        from google import genai
        client = genai.Client(api_key=settings.gemini_api_key)

        # Build a single prompt with system + history for the new SDK
        parts = []
        if system:
            parts.append(f"<system>\n{system}\n</system>\n")
        for m in history:
            role = "User" if m["role"] == "user" else "Assistant"
            parts.append(f"{role}: {m['content']}")
        parts.append("Assistant:")
        prompt = "\n".join(parts)

        resp = await asyncio.to_thread(
            client.models.generate_content,
            model=settings.gemini_model,
            contents=prompt,
        )
        import re
        text = re.sub(r'<execute_function>.*?</execute_function>', '', resp.text, flags=re.DOTALL).strip()
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
        return text, []

    async def _call_anthropic(self, history: list[dict], system: str) -> tuple[str, list]:
        settings = get_settings()
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        messages = [
            {"role": m["role"], "content": m["content"]}
            for m in history
            if m["role"] in ("user", "assistant")
        ]

        resp = await client.messages.create(
            model=settings.anthropic_model,
            system=system,
            max_tokens=4096,
            messages=messages,
        )
        return resp.content[0].text, []

    async def _call_openai(self, history: list[dict], system: str) -> tuple[str, list]:
        settings = get_settings()
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)

        messages = [{"role": "system", "content": system}] + [
            {"role": m["role"], "content": m["content"]}
            for m in history
            if m["role"] in ("user", "assistant")
        ]
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
        )
        return resp.choices[0].message.content, []

    async def _call_local(self, history: list[dict], system: str) -> tuple[str, list]:
        from core.llm import local_provider
        # Build messages list for chat template
        messages = [{"role": "system", "content": system}] + [
            {"role": m["role"], "content": m["content"]}
            for m in history
            if m["role"] in ("user", "assistant")
        ]
        text = await local_provider.generate_chat(messages)
        return text, []

    # ── History & Context ─────────────────────────────────────────────────────

    async def _load_history(self, limit: int = 40) -> list[dict]:
        result = await self._session.execute(
            select(ChatMessage)
            .where(ChatMessage.project_id == self._project.id)
            .order_by(ChatMessage.created_at.asc())
        )
        messages = result.scalars().all()
        # Keep last `limit` messages for token budget
        return [
            {"role": m.role.value, "content": m.content}
            for m in messages[-limit:]
        ]

    def _build_context_string(self, context: dict) -> str:
        parts = [f"**Project:** {self._project.name}", f"**Status:** {self._project.status.value}"]
        if context.get("endpoints_count"):
            parts.append(f"**Endpoints analyzed:** {context['endpoints_count']}")
        if context.get("active_snapshot"):
            parts.append(f"**Active snapshot:** v{context['active_snapshot']}")
        if context.get("last_test"):
            t = context["last_test"]
            parts.append(f"**Last test run:** {t.get('passed', 0)}/{t.get('total', 0)} passed")
        return "\n".join(parts)

    # ── Storage helpers ───────────────────────────────────────────────────────

    async def _save_message(
        self, role: MessageRole, content: str, metadata: dict | None = None
    ) -> ChatMessage:
        msg = ChatMessage(
            project_id=self._project.id,
            role=role,
            content=content,
            metadata=metadata or {},
        )
        self._session.add(msg)
        await self._session.flush()
        return msg

    async def _create_notification(
        self,
        ntype: NotificationType,
        title: str,
        message: str,
        requires_response: bool = False,
    ) -> Notification:
        from core.notifier import tab_link
        n = Notification(
            project_id=self._project.id,
            type=ntype,
            title=title,
            message=message,
            requires_response=requires_response,
            link=tab_link(self._project.id, 'chat'),
        )
        self._session.add(n)
        await self._session.flush()
        return n

    async def _extract_and_save_clarifications(self, text: str) -> list[dict]:
        """Save structured [CLARIFICATION]...[/CLARIFICATION] questions from the agent."""
        import re
        # Only extract questions the agent explicitly marked as needing user input
        questions = re.findall(r"\[CLARIFICATION\]\s*(.*?)\s*\[/CLARIFICATION\]", text, re.DOTALL)
        results = []
        for q in questions[:3]:  # Max 3 per message
            q = q.strip()
            if len(q) > 5:
                c = Clarification(
                    project_id=self._project.id,
                    question=q,
                    context={"source": "agent_response"},
                )
                self._session.add(c)
                results.append({"id": None, "question": q})
        if results:
            await self._session.flush()
            # Back-fill IDs after flush so the caller can reference them
            result_rows = await self._session.execute(
                select(Clarification)
                .where(Clarification.project_id == self._project.id)
                .where(Clarification.is_resolved == False)
                .order_by(Clarification.created_at.desc())
            )
            recent = result_rows.scalars().all()
            for i, row in enumerate(recent[: len(results)]):
                results[i]["id"] = row.id
        return results

    async def _execute_tool_call(self, tool_call: dict) -> dict:
        name = tool_call.get("name")
        args = tool_call.get("arguments", {})
        if name in self._action_callbacks:
            try:
                result = await self._action_callbacks[name](**args)
                return {"tool": name, "status": "success", "result": str(result)}
            except Exception as e:
                return {"tool": name, "status": "error", "error": str(e)}
        return {"tool": name, "status": "not_registered"}
