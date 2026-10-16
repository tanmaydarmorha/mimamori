"""Build the English replay fixtures (replay_en.json) from the Japanese ones (replay.json).

    python services/case-svc/tests/fixtures/build_replay_en.py

Conversations A, B and C with the same turns and meaning, in natural English (no simulated STT noise). Each
recorded model output is kept as it is, except that the quotes are the exact English words and the stated
reason is English, because quotes must be exact words from the transcript.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

TURNS = {
    "A": [
        "Um, it's for my home renovation. The bathroom.",
        "Well, someone I know recommended them, and I was told I have to pay today.",
        "The quote? Oh, they'll send that later. Anyway, I'm in a hurry.",
        "The police called me and told me not to tell anyone. Really, I shouldn't be saying this.",
        "They said my account is being used in a crime, so I have to move my money to a safe account. They'll give it back when it's over.",
        "Please don't tell my daughter. I don't want her to worry. The police said that too.",
    ],
    "B": [
        "My grandson just started working, so I thought I'd buy him a car.",
        "I went to the dealership with him the other day and we talked it over. This is the order form.",
        "He wanted to come today too, but he's at work. Shall I call him?",
        "No, nobody like that has called. I'd been keeping the car a secret from my grandson, but he knows now.",
        "I think the payee is the dealer's name, but could you check?",
    ],
    "C": [
        "It's the rest of the renovation payment. I paid the deposit last month.",
        "My son and I met the contractor, and I have the quote right here.",
        "The work is already finished. They put in handrails and it's much easier now.",
        "I'm not in a hurry, but I promised to pay by the end of the month.",
    ],
}

# (conversation, indicator type, turn) -> exact words from that English turn
QUOTES = {
    ("A", "cover_story", "c1"): "it's for my home renovation",
    ("A", "urgency", "c2"): "I was told I have to pay today",
    ("A", "impersonated_official", "c4"): "The police called me",
    ("A", "secrecy_instruction", "c4"): "told me not to tell anyone",
    ("A", "safe_account_transfer", "c5"): "my account is being used in a crime, so I have to move my money to a safe account",
    ("B", "cover_story", "c1"): "I thought I'd buy him a car",
    ("C", "cover_story", "c1"): "It's the rest of the renovation payment",
}

STATED = {"A": "Home renovation (bathroom)", "B": "Buying a car for a grandchild who just started working.", "C": "Remaining renovation costs"}


def main() -> None:
    ja = json.loads((HERE / "replay.json").read_text())
    out: dict = {}
    for conv in "ABC":
        entry = {"label": ja[conv]["label"].split(" [")[0] + " (English)", "expected": ja[conv]["expected"],
                 "customer_turns": TURNS[conv], "outputs": [], "patched": []}
        assert len(TURNS[conv]) == len(ja[conv]["customer_turns"])
        for output in ja[conv]["outputs"]:
            o = json.loads(json.dumps(output))
            for ind in o["indicators"]:
                ind["quote"] = QUOTES[(conv, ind["type"], ind["turn_id"])]
                assert ind["quote"] in TURNS[conv][int(ind["turn_id"][1:]) - 1], ind
            if o["cover_story"]["stated_reason"]:
                o["cover_story"]["stated_reason"] = STATED[conv]
            entry["outputs"].append(o)
        out[conv] = entry
    (HERE / "replay_en.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print({k: len(v["outputs"]) for k, v in out.items()})


if __name__ == "__main__":
    main()
