"""Google ADK drives the investigation loop (C4: "Python, FastAPI, ADK"), but offline.

ADK is used for orchestration only: an `LlmAgent` with the eight read-only tools as function tools, run by
`InMemoryRunner` with a hard call limit. The model behind it is our own `ModelClient` (Gemma on Ollama or
Vertex, or `FakeClient` in tests) wrapped in a small `BaseLlm` adapter, so every step is schema-constrained
and nothing talks to Google Cloud. ADK imports no credentials and makes no network call here.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from importlib import resources
from typing import Any, AsyncGenerator

from google.adk.agents import LlmAgent
from google.adk.agents.run_config import RunConfig
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

from mimamori_common.llm import ModelClient, data_block

from .tools import TOOL_NAMES, TOOLS, ToolEnv

log = logging.getLogger("case_svc.investigation")

SYSTEM_PROMPT = resources.files("case_svc").joinpath("prompts/investigation_system.md").read_text(encoding="utf-8")
HYPOTHESES = ["legitimate", "fake_police", "relative_in_trouble", "gold_bullion", "other_scam"]
SCALAR = {"type": ["string", "number", "boolean", "null"]}


def step_schema(*, may_call: bool) -> dict:
    """One reply per step, constrained: ask for every tool you need, or finish with the findings. On the last
    allowed step only `finish` is possible (and `tools` must be empty). A `call_tool` step needs no facts or
    inferences: they are only read on `finish`, and the prompt says to leave them empty."""
    return {
        "type": "object", "additionalProperties": False,
        "required": ["action", "tools", "playbook_hypothesis", "facts", "inferences", "leading_hypothesis", "first_question_id"],
        "properties": {
            "action": {"enum": ["call_tool", "finish"] if may_call else ["finish"]},
            "tools": {"type": "array", "items": {"enum": TOOL_NAMES}, "uniqueItems": True,
                      "maxItems": len(TOOL_NAMES) if may_call else 0},
            "playbook_hypothesis": {"enum": [*HYPOTHESES, "none"]},
            "facts": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["tool", "field", "value", "statement_en"],
                "properties": {"tool": {"enum": TOOL_NAMES}, "field": {"type": "string"}, "value": SCALAR,
                               "statement_en": {"type": "string"}}}},
            "inferences": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["statement_en", "grounds"],
                "properties": {"statement_en": {"type": "string", "maxLength": 300},
                               "grounds": {"type": "array", "items": {"type": "string"}}}}},
            "leading_hypothesis": {"enum": HYPOTHESES},
            "first_question_id": {"type": "string", "pattern": "^q\\.[a-z0-9_]+\\.[a-z0-9_]+$"},
        },
    }


def _render(contents: list[types.Content]) -> str:
    chunks: list[str] = []
    for content in contents:
        for part in content.parts or []:
            if part.text:
                chunks.append(part.text if content.role == "user" else f"(your earlier reply) {part.text}")
            elif part.function_call:
                chunks.append(f"(you called the tool {part.function_call.name})")
            elif part.function_response:
                # Tool results can contain payee-controlled text: they go in a data block.
                chunks.append(data_block(f"tool_result:{part.function_response.name}",
                                         json.dumps(part.function_response.response, ensure_ascii=False)))
    return "\n\n".join(chunks)


def _called(contents: list[types.Content]) -> set[str]:
    return {p.function_response.name for c in contents for p in (c.parts or []) if p.function_response}


class ClientLlm(BaseLlm):
    """Adapter: ADK `BaseLlm` over a `mimamori_common.llm.ModelClient` with constrained decoding."""

    model: str = "model-client"
    client: Any = None
    system: str = ""
    max_steps: int = 8
    calls: int = 0
    log_notes: Any = None

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        self.calls += 1
        last = self.calls >= self.max_steps
        result = await self.client.generate_json(self.system, _render(llm_request.contents), step_schema(may_call=not last))
        data = result.data
        asked = [t for t in dict.fromkeys(data.get("tools") or []) if t in TOOL_NAMES]  # unique, in order
        done = _called(llm_request.contents)
        fresh = [t for t in asked if t not in done]
        if data["action"] == "call_tool" and fresh:
            args = {}
            if "search_playbooks" in fresh and data.get("playbook_hypothesis") not in (None, "none"):
                args = {"playbook_hypothesis": data["playbook_hypothesis"]}
            # One function_call part per tool: ADK runs the calls of one response concurrently.
            parts = [types.Part(function_call=types.FunctionCall(name=t, args=args if t == "search_playbooks" else {}))
                     for t in fresh]
        else:
            if data["action"] == "call_tool":
                (self.log_notes if self.log_notes is not None else []).append(
                    f"tool request {asked or 'empty'} had nothing new, treated as finish")
            parts = [types.Part(text=json.dumps(data, ensure_ascii=False))]
        yield LlmResponse(content=types.Content(role="model", parts=parts))


@dataclass
class AgentRun:
    results: dict[str, dict] = field(default_factory=dict)  # what each tool actually returned
    final: dict | None = None  # the model's finish payload (unverified)
    tools_called: list[str] = field(default_factory=list)
    llm_calls: int = 0
    notes: list[str] = field(default_factory=list)


def _tool_functions(env: ToolEnv, run: AgentRun) -> list:
    """Closures with the case bound in. ADK reads the name, docstring and signature to declare each tool."""

    def make(name: str):
        impl = TOOLS[name]

        async def call(**kwargs) -> dict:
            result = await impl(env, **kwargs)
            run.results[name] = result
            run.tools_called.append(name)
            return result

        return call

    async def get_baseline() -> dict:
        """Customer's usual behaviour as computed counts and ratios."""
        return await make("get_baseline")()

    async def recent_transactions() -> dict:
        """Counts of recent activity and earlier payments to this payee."""
        return await make("recent_transactions")()

    async def explain_payee() -> dict:
        """What kind of holder the payee is and the payee account's age."""
        return await make("explain_payee")()

    async def check_lists() -> dict:
        """Number of watchlist entries matching the payee."""
        return await make("check_lists")()

    async def counterpart_graph() -> dict:
        """Payee account age and distinct payers in 7 days (same-bank payees only)."""
        return await make("counterpart_graph")()

    async def search_playbooks(playbook_hypothesis: str = "") -> dict:
        """Approved scam playbooks that fit the payment method."""
        return await make("search_playbooks")(hypothesis=playbook_hypothesis)

    async def get_advance_wishes() -> dict:
        """Whether advance wishes exist and whether the contact's number changed recently."""
        return await make("get_advance_wishes")()

    async def teller_notes() -> dict:
        """Counts of teller notes on this customer."""
        return await make("teller_notes")()

    return [get_baseline, recent_transactions, explain_payee, check_lists, counterpart_graph, search_playbooks,
            get_advance_wishes, teller_notes]


async def run_agent(client: ModelClient, env: ToolEnv, context: str, max_steps: int) -> AgentRun:
    run = AgentRun()
    llm = ClientLlm(client=client, system=SYSTEM_PROMPT, max_steps=max_steps, log_notes=run.notes)
    agent = LlmAgent(name="investigator", model=llm, instruction=SYSTEM_PROMPT, tools=_tool_functions(env, run))
    runner = InMemoryRunner(agent=agent, app_name="case-svc")
    session = await runner.session_service.create_session(app_name="case-svc", user_id="case-svc")
    final_text: str | None = None
    try:
        async for event in runner.run_async(
            user_id="case-svc", session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=context)]),
            run_config=RunConfig(max_llm_calls=max_steps + 1),
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final_text = "".join(p.text or "" for p in event.content.parts)
    finally:
        run.llm_calls = llm.calls
    if final_text:
        try:
            run.final = json.loads(final_text)
        except json.JSONDecodeError:
            run.notes.append("final reply was not JSON")
    else:
        run.notes.append("no final reply (step limit reached)")
    return run
