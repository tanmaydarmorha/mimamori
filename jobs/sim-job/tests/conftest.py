import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith(("MIMAMORI_", "OLLAMA_", "CORE_BANK", "SCORING_", "CASE_SVC", "CONVERSATION_SVC")):
            monkeypatch.delenv(key, raising=False)
