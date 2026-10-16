import copy
import re
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from mimamori_common.config import Settings
from mimamori_common.llm import FakeClient
from mimamori_common.models import CallRequest, ContactOutcomeRequest
from mimamori_common.schemas import load_example

from conversation_svc.app import Tunables, create_conversation_app

LOCKED = "+819012345678"
CODE = "4821"
CALLBACK = {"type": "callback", "caller_number": LOCKED, "menu_choice": "returning_a_call_about_a_case", "case_code": CODE}

DISCLOSABLE_ALL = {"transaction_paused": True, "reason_category": "call_from_someone_claiming_authority",
                   "customer_at_branch": True, "police_notified": True}


def make_request(disclosable: dict | None = None, may_disclose: list[str] | None = None, call_id: str | None = None,
                 language: str = "ja") -> CallRequest:
    brief = copy.deepcopy(load_example("contact-brief-tanaka.json"))
    if language == "en":
        brief["language"], brief["customer_reference"] = "en", "your mother"
    if disclosable is not None:
        brief["disclosable"] = disclosable
    if call_id:
        brief["call_id"] = call_id
    allowed = may_disclose if may_disclose is not None else list(brief["disclosable"])
    return CallRequest.model_validate({"brief": brief, "policy": {"may_disclose": allowed}})


def utterance_of(user_prompt: str) -> str:
    m = re.search(r'<data label="caller_utterance">\n(.*?)\n</data>', user_prompt, re.S)
    return m.group(1) if m else ""


def sensible_model(system: str, user: str, schema: dict) -> dict:
    """A well-behaved stand-in for the model: classifies by keywords, writes a harmless lead-in."""
    said = utterance_of(user)
    signals: dict = {}
    if "English lead-in" in system:  # an English call
        low = said.lower()
        intent = ("coming_to_branch" if "coming" in low else "how_much" if "how much" in low else "account_details" if "account" in low
                  else "is_she_safe" if "safe" in low else "what_happened" if "what happened" in low
                  else "what_should_i_do" if "what should" in low else "other")
        return {"intent": intent, "connecting_phrase": "I'm sorry for the worry.", "signals": {"concerned": True}}
    if "心配" in said or "大丈夫" in said or "worried" in said:
        signals["concerned"] = True
    if "行きます" in said or "向かって" in said:
        signals.update(coming_to_branch=True, concerned=True)
    if "行きます" in said or "向かって" in said:
        intent = "coming_to_branch"
    elif "いくら" in said or "how much" in said:
        intent = "how_much"
    elif "口座" in said or "番号" in said:
        intent = "account_details"
    elif "無事" in said or "母は" in said:
        intent = "is_she_safe"
    elif "何があった" in said or "なぜ" in said:
        intent = "what_happened"
    elif "どうすれば" in said:
        intent = "what_should_i_do"
    else:
        intent = "other"
    return {"intent": intent, "connecting_phrase": "ご心配なお気持ち、お察しいたします。", "signals": signals}


class RecordingSink:
    def __init__(self) -> None:
        self.posts: list[tuple[str, ContactOutcomeRequest]] = []

    async def post_outcome(self, case_id: str, outcome: ContactOutcomeRequest) -> bool:
        self.posts.append((case_id, outcome))
        return True


@dataclass
class Harness:
    client: TestClient
    model: FakeClient
    sink: RecordingSink
    spoken: list[str] = field(default_factory=list)

    def post_call(self, request: CallRequest | None = None):
        request = request or make_request()
        return self.client.post("/calls", json=request.model_dump(mode="json"))

    def call(self, messages: list[dict], callback: dict | None = None) -> list[dict]:
        """Open /phone, send the callback, then each message (waiting for the reply), hang up if the
        server hasn't ended the call. Returns every server message received."""
        out: list[dict] = []
        with self.client.websocket_connect("/phone") as ws:
            ws.send_json(callback or CALLBACK)
            out.append(ws.receive_json())  # verification
            if not out[-1]["ok"]:
                out.append(ws.receive_json())  # ended
                return out
            out.append(ws.receive_json())  # opening line
            for message in messages:
                ws.send_json(message)
                out.append(ws.receive_json())
                if out[-1]["type"] == "say" and out[-1].get("template_intent") == "coming_to_branch":
                    out.append(ws.receive_json())  # ended: completed
                if out[-1]["type"] == "ended":
                    return out
            ws.send_json({"type": "hangup"})
            out.append(ws.receive_json())
        return out


def turn(text: str) -> dict:
    return {"type": "turn", "text": text}


@pytest.fixture
def harness():
    model = FakeClient(json_handler=sensible_model)
    sink = RecordingSink()
    app = create_conversation_app(Settings(demo_now="2026-10-13T12:00:00+09:00"), model=model, outcome_sink=sink,
                                  tunables=Tunables(model_timeout_s=5))
    with TestClient(app) as client:
        yield Harness(client, model, sink)
