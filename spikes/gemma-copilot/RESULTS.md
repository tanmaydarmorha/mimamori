# Gemma counter-copilot spike: results

Step 0 of the review-response plan (see `docs/decisions.md`, Gemma spike). Run on 2026-10-12.

**Verdict: pass on criteria 1–3. Per the plan, the copilot stays on Gemma.** Latency (criterion 4)
was not tested here and still needs checking on the deployed endpoint.

## Setup

| | |
|---|---|
| Model | `gemma4:12b` via Ollama 0.30.7, **Q4_K_M quantised**, thinking off, temperature 0 |
| Machine | Apple M5, 24 GB, local |
| Turns | 20 customer turns across 4 conversations (`conversations.json`) |
| Prompt | `system_prompt.md` + seeded facts + 3 approved playbooks (`playbooks.json`) |
| Output | Prompt-only JSON, **no constrained decoding**, validated against `schema.json` |
| Raw results | `results/gemma4-12b-t0.0.jsonl` |

This is a pessimistic test: a quantised 12B model, when production would use a larger Gemma on
Vertex.

Run it again with: `python run_spike.py` (needs Ollama running and `pip install jsonschema`).
Options: `--think`, `--temperature`, `--model`.

## Pass criteria (fixed before the run, CR #22)

| # | Criterion | Result |
|---|---|---|
| 1 | Detects the renovation cover story and the secrecy line in the Tanaka transcript | **Pass.** Cover story flagged on c1 (`consistent_with_history: no`, matched to the fake-police playbook). Secrecy flagged on c4, the turn it first appears. Pause recommended at c4. |
| 2 | No accusing or diagnosing wording in any suggestion | **Pass.** All 20 next questions and 4 hold-firm lines were read by hand. A keyword scan (認知, 判断能力, 物忘れ, 記憶, 嘘, 騙され, 詐欺, …) found nothing. The hold lines are polite and frame the pause as protecting the customer. |
| 3 | Structured output validates on ≥ 19 of 20 turns | **Pass, 20/20.** Every reply was wrapped in a ```json code fence despite the instruction. The parser strips fences. |
| 4 | Latency under ~3 s per turn | **Not tested** (local Mac: 30–100 s per turn, which isn't meaningful for the endpoint). |

## Per conversation

| Conv | Expected | Pause recommended | Notes |
|---|---|---|---|
| A Tanaka, fake police | scam | c4 → c6 | Fake-police likelihood 0.6 from c1 (renovation + 4-day-old payee), 0.95 once secrecy appears. |
| B car for grandchild | legitimate | never | Correct outcome, but the scam likelihood stayed fixed at 0.4 for all 5 turns. See finding 1. |
| C genuine renovation | legitimate | never | **The hardest case and the strongest result.** "Renovation" was recognised as a playbook cover story, but the model used the earlier deposit to the same payee to rate it 0.9–0.95 legitimate. It isn't matching keywords. |
| D son in trouble, cash | scam | c5 only | Relative-in-trouble at 0.9 from c2, but the pause came only once secrecy appeared (c5). The cash handover to a stranger (c4) did not trigger it alone. |

False pauses on legitimate turns: 0 of 9.

## Quotes (input for CR #27)

43 of 44 quotes matched the transcript exactly. The one failure (A c6) **joined two customer turns
with "…"** and cited one turn ID. Normalising (NFKC, removing whitespace) didn't help, because the
quote wasn't reworded, it was stitched together. Code that extracts the quote from a turn ID plus
offsets would make this kind of error impossible.

## Findings that should shape the design

1. **Don't use the model's likelihood numbers as the on-screen confidence.** They are coarse and
   barely move: B stayed at 0.6 / 0.4 through an order form, a visit to the dealer and "no unknown
   calls". Let code compute the confidence and the pause recommendation from the verified
   indicators and facts (for example, a scam hypothesis plus at least two independent indicator
   types). Keep the model's job as extracting indicators and checking the cover story, which it
   does well. This also makes D pause at c4, where it should.
2. **Indicator types are noisy.** Examples: the cash handover in D c4 was labelled
   `third_party_pressure` instead of `cash_or_card_handover`; D c3 labelled the raspy voice as
   `safe_account_transfer`; D c1 labelled the withdrawal request itself as a `cover_story`. Add
   short definitions and one or two examples per type to the prompt, or check type against quote
   in code for the types that matter to the pause rule.
3. **Next questions sometimes invent details** (B c2 asks about a "trip"; D c4 refers to the boss
   giving instructions on the phone, which wasn't said), and **repeat after the pause** (A c5 and c6
   ask the same thing). Better: choose from the playbook's question bank with a short reworded
   lead-in, or check that a question doesn't introduce facts that aren't in the transcript.
4. **Playbook matching is broad.** B's "car for a grandchild" was matched to the fake-police playbook
   because "family purchase" is one of its cover stories. That's defensible from the data, but
   cover-story matching should be weighed against history, as it was in C, not used as evidence on
   its own.
5. **Code fences on every reply.** Use Ollama or Vertex constrained decoding in the build, or keep
   stripping fences.

## Run 2: simulated speech-to-text errors (text only, no audio)

`conversations_stt.json` contains the same 20 turns, rewritten by hand to look like flawed
speech-to-text output: no punctuation, wrong-kanji homophones (口座→高座, 代→台, 注文書→注文所),
kana in place of kanji (だれにも, しゅうしょく, じょうし), a dropped clause in Tanaka c4, and 2百万.
**No audio and no real STT engine were used.** The errors are realistic guesses, not measured from
Chirp. Results: `results/gemma4-12b-t0.0-conversations_stt.jsonl`.

| | Clean | STT errors |
|---|---|---|
| Schema-valid | 20/20 | **19/20.** B c5 wrote `relative-in-trouble` instead of `relative_in_trouble`, copying the hyphen from the playbook ID. |
| Quotes matching exactly | 43/44 | 43/44 |
| Pause decisions | A c4–c6, D c5 | A c4–c6, **D c4–c5** |
| False pauses (legitimate) | 0/9 | 0/9 |
| Accusing or diagnosing wording | none | none |

What the run shows:

- **The errors barely affected detection.** A, B and C reached the same decisions with nearly the
  same likelihoods. 高座 (a homophone meaning "stage") did not hide the safe-account script, which
  was still flagged as `safe_account_transfer` on c5. The secrecy line was still caught after
  あなたにも言っちゃいけない was dropped.
- **Quotes keep the transcript's errors** (it quoted 「私の高座が…」 as written). That's what code
  verification needs.
- **The pause decision moves with small input changes.** In D, the noisy text produced the correct
  `cash_or_card_handover` label on c4 and a pause one turn earlier than the clean run. That's better
  here, but it shows the pause point isn't stable. It's more support for computing the pause in code
  (finding 1).
- **The one quote failure had the wrong turn ID.** 「警察の人から電話があってね」 was cited as c5 but
  was said in c4. In run 1, the failure was two turns joined together. Both kinds can be caught in
  code: search every customer turn for the quote, correct the turn ID if it's found elsewhere, and
  drop it if it's found nowhere. That's simpler than offsets and covers both failures (CR #27).
- **A suggested "question" asserted something false.** In A c6 it was 「このお振込み先の会社様とは以前からお取引があるのですね」 ("you've dealt with this company before, haven't you"),
  which contradicts the facts. That makes finding 3 more serious: a teller could read an invented
  claim aloud. The question bank, or a check that questions add no new facts, is needed.
- **Enum typos happen.** At 19/20 this is just at the pass line. Use constrained decoding in the
  build.

## Run 3: the schema design (v2) on the STT-error transcripts

Run 3 tests the design in [`../../schemas/`](../../schemas/), which takes findings 1–5 into
account:

- **Prompt:** `system_prompt_v2.md` defines each indicator type with an example (finding 2). The
  examples are deliberately different from the test conversations.
- **Model output:** follows `schemas/copilot-turn.json`. There are no likelihood numbers and no
  pause flag (finding 1), and the next question is an **ID** from the approved bank rather than
  free text (finding 3).
- **Seed data:** the seed playbooks and general question bank from `schemas/examples/`.
- **Code rules:** the quote rule, accumulation and the risk rule from `rules.py`, applied afterwards.

Run 3 used the original playbook IDs (`pb-fake-police-safe-account`). Run 3b is identical except
for the new single naming style (`pb.fake_police.safe_account`). Results are in
`results/v2-…jsonl` and `results/v2b-…jsonl`.

| | Run 2 (v1 design) | Run 3 (v2) | Run 3b (v2, one naming style) |
|---|---|---|---|
| Schema-valid | 19/20 | **11/20** | 19/20 |
| Why invalid | enum typo | `pb-fake_police_safe_account` on 9 turns | indicator type `relative_in_trouble` on 1 turn |
| Question ID exists in bank | n/a | 20/20 | 20/20 |
| Quotes dropped / moved by the quote rule | 0 / 1 | 0 / 0 | 0 / 0 |
| Tanaka pause (risk rule) | c4 | c4 | c4 |
| Son-in-trouble pause (risk rule) | c4 | c3 | c4 |
| Pauses on legitimate turns (risk rule) | 0/9 | 0/9 | 0/9 |

What changed:

- **Indicator labels are now right where it matters.** The raspy voice became
  `impersonated_relative` (run 1 called it `safe_account_transfer`), and the cash pickup became
  `cash_or_card_handover` (run 1 called it `third_party_pressure`). When the son-in-trouble case
  pauses at c3 now, it's for the right reason.
- **The leading hypothesis moves with evidence.** The car case starts as relative-in-trouble on c1
  and changes to legitimate from c2, once the order form appears. Run 1's numbers never moved.
- **Wording can no longer invent facts.** Every suggestion is approved bank wording.
- **Mixed naming styles caused most of the failures.** Showing the model `pb-fake-police-…` next to
  `fake_police` made it blend the two. With one style, schema failures fell from 9 to 1. The
  remaining failure was another blend: a hypothesis name used as an indicator type. **Decision: use
  constrained decoding (schema-enforced output) in the build.** Ollama and Vertex both support it.
- **Questions repeat.** `q.general.payee_relation` was suggested on four turns in a row in C, and
  three times in a row in B. The harness exaggerates this, because the scripted teller never asks the
  suggested question. Still, the prompt rule "don't repeat" was ignored. **Code now removes
  already-suggested questions from the bank shown to the model** (`schemas/README.md`). This isn't
  tested yet, but it holds by construction: an ID that isn't in the bank shown falls back and is
  logged.
- **Some run-to-run variation remains.** Runs 3 and 3b differ only in naming, yet the son-in-trouble
  pause moved from c3 to c4 because c3's `impersonated_relative` label appeared in one run and not
  the other. Both times are reasonable, but the turn on which the pause fires can shift by one.

## Not yet tested

- Latency on the deployed endpoint (criterion 4).
- Stability: runs 3 and 3b suggest the pause can shift by a turn. Several runs at temperature 0.7
  would measure this properly.
- The "exclude already-suggested questions" rule, run end to end.
- Thinking mode (`--think`), which may fix findings 2 and 3 at some latency cost.
- Real audio: run 2 simulates STT errors in text. A real test needs recordings (ideally natural,
  hesitant elderly speech) transcribed by Cloud STT V2 Chirp.
- A larger Gemma.
