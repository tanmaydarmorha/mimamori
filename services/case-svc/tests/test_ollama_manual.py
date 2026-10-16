"""Manual check, not run in CI:  python -m pytest services/case-svc/tests -m ollama -s

The same flow as the replay test, but the copilot is the real `gemma4:12b` behind `OllamaClient` (constrained
decoding to copilot-turn.json). The spike saw 30-100 s per turn locally. Asserts only what the design guarantees
(valid cards, risk computed in code); prints when the pause fired so the result can be compared with the recording
(c4). Conversations B and C must not pause."""

import time

import pytest
from conftest import REPLAYS, SCENARIOS, STAFF  # noqa: E402

from mimamori_common.llm import OllamaClient, get_copilot_client
from mimamori_common.config import Settings

pytestmark = pytest.mark.ollama

# Read at import: the autouse _clean_env fixture removes MIMAMORI_* before each test runs.
_SETTINGS = Settings.from_env()


@pytest.mark.parametrize("conv_id", [
    "A",
    pytest.param("B", marks=pytest.mark.xfail(reason="seen 2x with gemma4:12b: c4 'ないしょ' (a harmless surprise) is labelled secrecy_instruction "
                                                      "and the grandchild as impersonated_relative -> H1 -> false pause. Not seen in spike run 3b.", strict=False)),
    "C",
])
@pytest.mark.parametrize("language", ["ja", "en"])
def test_real_gemma_through_the_service(make_env, conv_id, language):
    settings = _SETTINGS
    # MIMAMORI_COPILOT_BACKEND=gemini runs the same check against Gemini (fast); default is local Gemma.
    copilot = (OllamaClient(settings.ollama_url, settings.ollama_model, timeout_s=600)
               if settings.copilot_backend == "ollama" else get_copilot_client(settings))
    env = make_env(copilot=copilot)
    kwargs = dict(SCENARIOS[conv_id])
    case_id = env.open_case(**kwargs) if conv_id == "A" else env.open_case(signals=[], **kwargs)
    if language != "ja":
        assert env.client.patch(f"/cases/{case_id}/language", json={"language": language, "actor": "teller-sato"}, headers=STAFF).status_code == 200
    first_pause, seconds = None, []
    for i, text in enumerate(REPLAYS[language][conv_id]["customer_turns"], start=1):
        started = time.monotonic()
        card = env.turn(case_id, text)["card"]
        seconds.append(round(time.monotonic() - started, 1))
        print(f"  c{i}: {[(c['indicator'], c['source']['text'][:20]) for c in card['claims'] if c['kind'] == 'quote']} "
              f"fired={[f['condition'] for f in card['risk']['fired']]}")
        if card["risk"]["pause_recommended"] and first_pause is None:
            first_pause = f"c{i}"
    print(f"\n{language} {conv_id}: first pause = {first_pause}; seconds per turn = {seconds}")
    if conv_id == "A":
        assert first_pause is not None
    else:
        assert first_pause is None
