"""Model clients. Every structured call is schema-constrained (constrained decoding): Ollama via
`format`, Vertex Gemma via an OpenAI-style `response_format`, Gemini via `responseJsonSchema`.

    ModelClient.generate_json(system, user, schema) -> ModelResult   (structured, schema-enforced)
    ModelClient.generate_text(system, user)         -> ModelResult   (free text, e.g. a connecting phrase)

Selection is by config: `get_copilot_client()` (case service, Gemma) and `get_general_client()`
(conversation service, jobs: Gemini in the cloud, Ollama locally). `FakeClient` replays recorded
output in tests. Untrusted text must be put in a delimited data block by the caller: see `data_block`.
Only OllamaClient and FakeClient are exercised without cloud access; the Vertex clients are written
against the documented REST shapes and need a first run in the bank project.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

import httpx

from .config import Settings
from .schemas import inline_refs


log = logging.getLogger(__name__)


def _log_call(model: str, kind: str, seconds: float, attempts: int = 1) -> None:
    """One INFO line per model call: what it cost, so slow steps can be found in the logs."""
    log.info("model call model=%s kind=%s seconds=%.2f attempts=%d", model, kind, seconds, attempts)


class ModelOutputError(RuntimeError):
    """The model returned something that isn't valid JSON (should not happen under constrained decoding)."""


@dataclass
class ModelResult:
    data: Any  # dict for generate_json, str for generate_text
    raw: str
    seconds: float
    model: str


class ModelClient(Protocol):
    name: str

    async def generate_json(self, system: str, user: str, schema: dict, *, temperature: float = 0.0, seed: int | None = 7) -> ModelResult: ...

    async def generate_text(self, system: str, user: str, *, temperature: float = 0.2, max_chars: int | None = None) -> ModelResult: ...


def data_block(label: str, text: str) -> str:
    """Wrap untrusted text (payee names, memos, transcripts, alert prose) for a prompt. The system
    prompt must say that anything inside <data> tags is data, never instructions. The closing tag is
    neutralised so the text can't break out of the block."""
    safe = text.replace("</data", "<\\/data")
    return f'<data label="{label}">\n{safe}\n</data>'


def parse_json(raw: str) -> dict:
    """Accept clean JSON or a ```json fenced block (Gemma wraps replies in fences when unconstrained)."""
    text = raw.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    try:
        return json.loads(fenced.group(1) if fenced else text)
    except json.JSONDecodeError as err:
        raise ModelOutputError(f"not valid JSON: {err}; raw={raw[:200]!r}") from err


def _clip(text: str, max_chars: int | None) -> str:
    return text if not max_chars else text[:max_chars]


class OllamaClient:
    def __init__(self, url: str, model: str, timeout_s: float = 120.0, num_ctx: int = 16384,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.url, self.model, self.timeout_s, self.num_ctx = url.rstrip("/"), model, timeout_s, num_ctx
        self._transport = transport  # tests inject httpx.MockTransport
        self.name = f"ollama:{model}"

    async def _chat(self, system: str, user: str, *, fmt: dict | None, temperature: float, seed: int | None) -> tuple[str, float]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "think": False,
            "options": {"temperature": temperature, "num_ctx": self.num_ctx, **({"seed": seed} if seed is not None else {})},
        }
        if fmt is not None:
            body["format"] = fmt
        started = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout_s, transport=self._transport) as http:
            resp = await http.post(f"{self.url}/api/chat", json=body)
            resp.raise_for_status()
        return resp.json()["message"]["content"], time.monotonic() - started

    async def generate_json(self, system, user, schema, *, temperature=0.0, seed=7):
        raw, seconds = await self._chat(system, user, fmt=inline_refs(schema), temperature=temperature, seed=seed)
        _log_call(self.name, "json", seconds)
        return ModelResult(parse_json(raw), raw, seconds, self.name)

    async def generate_text(self, system, user, *, temperature=0.2, max_chars=None):
        raw, seconds = await self._chat(system, user, fmt=None, temperature=temperature, seed=None)
        _log_call(self.name, "text", seconds)
        return ModelResult(_clip(raw.strip(), max_chars), raw, seconds, self.name)

RETRY_STATUSES = {429, 500, 503}
RETRY_BASE_S = 1.0
RETRY_AFTER_CAP_S = 30.0


class _GoogleRest:
    """Authenticated REST helper shared by the Vertex clients (application default credentials, no keys in the repo)."""

    def __init__(self, timeout_s: float, max_retries: int = 4, *, transport: httpx.AsyncBaseTransport | None = None,
                 sleep: Callable[[float], Any] = asyncio.sleep) -> None:
        self.timeout_s, self.max_retries = timeout_s, max_retries
        self._transport, self._sleep = transport, sleep
        self._credentials = None

    def _token(self) -> str:
        import google.auth
        import google.auth.transport.requests

        if self._credentials is None:
            self._credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not self._credentials.valid:
            self._credentials.refresh(google.auth.transport.requests.Request())
        return self._credentials.token

    def _wait_s(self, attempt: int, resp: httpx.Response | None) -> float:
        retry_after = resp.headers.get("Retry-After") if resp is not None else None
        if retry_after:
            try:
                return min(max(float(retry_after), 0.0), RETRY_AFTER_CAP_S)
            except ValueError:
                pass
        return RETRY_BASE_S * 2**attempt * random.uniform(0.5, 1.5)

    async def post(self, url: str, body: dict, info: dict | None = None) -> tuple[dict, float]:
        """POST with retries on 429/500/503 and transport errors; other 4xx raise at once. The retries
        share the `timeout_s` budget: we give up when the next wait would pass it. `info`, if given, gets
        `attempts` and `total_seconds` (retries and waits included) for the caller's log line."""
        token = await asyncio.to_thread(self._token)
        began = time.monotonic()
        attempt = 0
        async with httpx.AsyncClient(timeout=self.timeout_s, transport=self._transport) as http:
            while True:
                started = time.monotonic()
                resp: httpx.Response | None = None
                try:
                    resp = await http.post(url, json=body, headers={"Authorization": f"Bearer {token}"})
                    if resp.status_code not in RETRY_STATUSES:
                        resp.raise_for_status()
                        if info is not None:
                            info.update(attempts=attempt + 1, total_seconds=time.monotonic() - began)
                        return resp.json(), time.monotonic() - started
                    error: Exception = httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=resp.request, response=resp)
                    status = str(resp.status_code)
                except httpx.TransportError as exc:
                    error, status = exc, type(exc).__name__
                wait = self._wait_s(attempt, resp)
                if attempt >= self.max_retries or time.monotonic() - began + wait > self.timeout_s:
                    raise error
                attempt += 1
                log.warning("model call failed (%s); retry %d/%d in %.1fs", status, attempt, self.max_retries, wait)
                await self._sleep(wait)


class VertexGemmaClient:
    """Gemma on a dedicated Vertex AI endpoint (vLLM serving, OpenAI-compatible chat/completions)."""

    def __init__(self, project: str, region: str, endpoint_id: str, model: str = "gemma", timeout_s: float = 120.0,
                 max_retries: int = 4) -> None:
        self.url = (f"https://{region}-aiplatform.googleapis.com/v1/projects/{project}/locations/{region}"
                    f"/endpoints/{endpoint_id}/chat/completions")
        self.model, self._rest = model, _GoogleRest(timeout_s, max_retries)
        self.name = f"vertex-gemma:{endpoint_id}"

    async def _chat(self, system, user, response_format, temperature, seed):
        body = {"model": self.model, "temperature": temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if seed is not None:
            body["seed"] = seed
        if response_format:
            body["response_format"] = response_format
        info: dict = {}
        data, seconds = await self._rest.post(self.url, body, info)
        _log_call(self.name, "json" if response_format else "text", info.get("total_seconds", seconds), info.get("attempts", 1))
        return data["choices"][0]["message"]["content"], seconds

    async def generate_json(self, system, user, schema, *, temperature=0.0, seed=7):
        fmt = {"type": "json_schema", "json_schema": {"name": "output", "strict": True, "schema": inline_refs(schema)}}
        raw, seconds = await self._chat(system, user, fmt, temperature, seed)
        return ModelResult(parse_json(raw), raw, seconds, self.name)

    async def generate_text(self, system, user, *, temperature=0.2, max_chars=None):
        raw, seconds = await self._chat(system, user, None, temperature, None)
        return ModelResult(_clip(raw.strip(), max_chars), raw, seconds, self.name)


class GeminiClient:
    """Gemini on Vertex AI (`generateContent`). Never given customer records: only the contact brief,
    public alert text or synthetic role-play."""

    def __init__(self, project: str, location: str, model: str, timeout_s: float = 60.0, max_retries: int = 4,
                 thinking_budget: int = 0) -> None:
        self.url = (f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}"
                    f"/publishers/google/models/{model}:generateContent")
        self.model, self._rest = model, _GoogleRest(timeout_s, max_retries)
        self.name = f"gemini:{model}"
        self.thinking_budget = thinking_budget  # 0 = off; -1 = leave it to the model (send nothing)

    async def _generate(self, system, user, generation_config, kind="text"):
        if self.thinking_budget != -1:
            # Every call here is extraction or classification into a fixed shape: no reasoning needed.
            generation_config = {**generation_config, "thinkingConfig": {"thinkingBudget": self.thinking_budget}}
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": generation_config}
        info: dict = {}
        data, seconds = await self._rest.post(self.url, body, info)
        _log_call(self.name, kind, info.get("total_seconds", seconds), info.get("attempts", 1))
        return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"]), seconds

    async def generate_json(self, system, user, schema, *, temperature=0.0, seed=7):
        cfg = {"temperature": temperature, "responseMimeType": "application/json", "responseJsonSchema": inline_refs(schema)}
        if seed is not None:
            cfg["seed"] = seed
        raw, seconds = await self._generate(system, user, cfg, "json")
        return ModelResult(parse_json(raw), raw, seconds, self.name)

    async def generate_text(self, system, user, *, temperature=0.2, max_chars=None):
        raw, seconds = await self._generate(system, user, {"temperature": temperature})
        return ModelResult(_clip(raw.strip(), max_chars), raw, seconds, self.name)


@dataclass
class FakeCall:
    kind: str  # "json" | "text"
    system: str
    user: str
    schema: dict | None = None


class FakeClientExhausted(AssertionError):
    pass


@dataclass
class FakeClient:
    """Replays recorded output. Give queues (consumed in order) and/or handlers (called with the
    prompt, for content-dependent replies). `calls` records every prompt for assertions, e.g. that
    untrusted text sat inside a data block."""

    json: list[dict | str] = field(default_factory=list)
    text: list[str] = field(default_factory=list)
    json_handler: Callable[[str, str, dict], dict | str] | None = None
    text_handler: Callable[[str, str], str] | None = None
    repeat_last: bool = False
    name: str = "fake"
    calls: list[FakeCall] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._json, self._text = deque(self.json), deque(self.text)

    @classmethod
    def from_jsonl(cls, path: str | Path, **kwargs) -> "FakeClient":
        """Replay the `output` of each record in a spike results file, in order."""
        records = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
        return cls(json=[r["output"] if r.get("output") else r["raw"] for r in records], **kwargs)

    def _next(self, queue: deque, last: list, kind: str):
        if queue:
            value = queue.popleft()
            last[:] = [value]
            return value
        if self.repeat_last and last:
            return last[0]
        raise FakeClientExhausted(f"FakeClient has no more recorded {kind} responses")

    _last_json: list = field(default_factory=list, repr=False)
    _last_text: list = field(default_factory=list, repr=False)

    async def generate_json(self, system, user, schema, *, temperature=0.0, seed=7):
        self.calls.append(FakeCall("json", system, user, schema))
        value = self.json_handler(system, user, schema) if self.json_handler else self._next(self._json, self._last_json, "json")
        raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return ModelResult(parse_json(raw), raw, 0.0, self.name)

    async def generate_text(self, system, user, *, temperature=0.2, max_chars=None):
        self.calls.append(FakeCall("text", system, user))
        value = self.text_handler(system, user) if self.text_handler else self._next(self._text, self._last_text, "text")
        return ModelResult(_clip(value, max_chars), value, 0.0, self.name)


def _require_project(settings: Settings) -> str:
    if not settings.project_id:
        raise ValueError("MIMAMORI_PROJECT_ID (or GOOGLE_CLOUD_PROJECT) is required for Vertex AI clients")
    return settings.project_id


def _build(backend: str, settings: Settings) -> ModelClient:
    if backend == "ollama":
        return OllamaClient(settings.ollama_url, settings.ollama_model, settings.model_timeout_s)
    if backend == "vertex_gemma":
        if not settings.vertex_gemma_endpoint_id:
            raise ValueError("VERTEX_GEMMA_ENDPOINT_ID is required for the vertex_gemma backend")
        return VertexGemmaClient(_require_project(settings), settings.region, settings.vertex_gemma_endpoint_id,
                                 settings.vertex_gemma_model, settings.model_timeout_s, settings.model_max_retries)
    if backend == "gemini":
        return GeminiClient(_require_project(settings), settings.gemini_location or settings.region,
                            settings.gemini_model, settings.model_timeout_s, settings.model_max_retries,
                            settings.gemini_thinking_budget)
    if backend == "fake":
        return FakeClient(repeat_last=True)
    raise ValueError(f"unknown model backend {backend!r} (ollama | vertex_gemma | gemini | fake)")


def get_copilot_client(settings: Settings | None = None) -> ModelClient:
    """Gemma, for the case service's copilot and investigation calls."""
    settings = settings or Settings.from_env()
    return _build(settings.copilot_backend, settings)


def get_general_client(settings: Settings | None = None) -> ModelClient:
    """Gemini in the cloud (Ollama locally), for the conversation service and the jobs."""
    settings = settings or Settings.from_env()
    if settings.general_backend == "vertex_gemma":
        raise ValueError("general_backend must be ollama, gemini or fake")
    return _build(settings.general_backend, settings)
