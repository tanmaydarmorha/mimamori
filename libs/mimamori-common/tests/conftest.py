import json
from pathlib import Path

import pytest

from mimamori_common.store import reset_memory_stores

REPO = Path(__file__).resolve().parents[3]
SPIKE = REPO / "spikes" / "gemma-copilot"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith(("MIMAMORI_", "OLLAMA_", "CORE_BANK", "SCORING_", "CASE_SVC", "CONVERSATION_SVC")):
            monkeypatch.delenv(key, raising=False)
    reset_memory_stores()
    yield
    reset_memory_stores()


def load_json(path: Path):
    return json.loads(path.read_text())
