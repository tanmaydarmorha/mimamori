# Mimamori schemas

JSON Schema (draft 2020-12) for the data that moves between containers. These are the contracts the
build implements. Design decisions are in [`../docs/decisions.md`](../docs/decisions.md). The rules
below come from the Gemma spike ([`../spikes/gemma-copilot/RESULTS.md`](../spikes/gemma-copilot/RESULTS.md)).

Check the schemas and examples with `python schemas/validate.py` (needs `pip install jsonschema`).

| Schema | Written by → read by | Store | What it holds |
|---|---|---|---|
| [`copilot-turn.json`](copilot-turn.json) | Gemma → case service | — | Model output per customer turn: indicators with quotes, cover-story check, leading hypothesis, chosen question ID |
| [`evidence-card.json`](evidence-card.json) | case service → teller console | `case-db` | Verified facts, quotes and inferences; hypotheses; **risk computed in code**; next question; dropped claims |
| [`question-bank.json`](question-bank.json) | analyst-approved → copilot, console | `intel-db` | All approved counter wording: questions and hold-firm lines |
| [`playbook.json`](playbook.json) | intelligence job → analyst → copilot | `intel-db` | Structured scam playbook with dated sources and its own question bank |
| [`advance-wishes.json`](advance-wishes.json) | onboarding (seeded) → case service | `case-db` | Contacts, cooling-off delay and override, disclosure choices, notice consent |
| [`contact-brief.json`](contact-brief.json) | case service (code) → conversation service | — | The only case data Gemini ever sees on the family call |
| [`call-turn.json`](call-turn.json) | Gemini → conversation service | — | Intent of the contact's turn, an optional connecting phrase, signals. Also the reply-template format |
| [`contact-view.json`](contact-view.json) | conversation service → case service | `case-db` | Call outcome as **information**, with verification results |

`examples/` has a Tanaka example of each, plus the seed playbooks, general question bank and call
templates. The spike uses the same seed data.

## What the model decides and what code decides

| | Model | Code |
|---|---|---|
| Indicators and quotes | Extracts them | Verifies quotes, accumulates them on the card |
| Cover-story check | Judges consistency with history and playbooks | — |
| Leading hypothesis | Names it | Shows it next to the evidence |
| Confidence and pause recommendation | — | **Risk rule** |
| Words the teller says | Chooses a question **ID** | Fills it from the approved bank, picks the hold line |
| Family call | Classifies intent, writes ≤ 30-character connecting phrase | Picks and fills the template, rule check |

The spike showed the model is good at the left column. Its own likelihood numbers didn't move with
evidence, its pause timing shifted with trivial input changes, and its free-text questions
sometimes stated things that weren't true. So those moved to code or to approved wording.

## Rules (reference implementation: [`../spikes/gemma-copilot/rules.py`](../spikes/gemma-copilot/rules.py))

### Quote rule

For each indicator the model returns:
1. The quote is an exact substring of the cited customer turn → keep.
2. Otherwise it's found (exactly, then after NFKC normalisation and removing whitespace) in another
   customer turn → keep, and move the turn ID (`turn_id_corrected: true`).
3. Otherwise → drop, and record it under `dropped` with `quote_not_found`.

Only customer turns are searched. This handles both failures seen in the spike: a quote joined
across two turns (dropped) and a quote cited to the wrong turn (moved). STT errors stay in the
quote, because the model copies the transcript as written.

### Accumulation

Verified indicators stay on the card for the whole case. A later turn can add indicators but
can't remove them because the model stopped listing them. Only a teller dismissal removes one, and
that is logged. Without this, the risk level flickered high → elevated → high in the spike.

### Risk rule (`risk-v1`)

Indicator groups:
- **core:** impersonation (`impersonated_official`, `impersonated_relative`), secrecy
  (`secrecy_instruction`), mechanism (`safe_account_transfer`, `cash_or_card_handover`)
- **pressure:** `urgency`, `third_party_pressure`, `changed_contact_number`

Facts: **cover mismatch** = `cover_story.consistent_with_history == "no"`. **Risky counterpart** =
same-bank payee account ≤ 30 days old or ≥ 5 distinct payers in 7 days.

| Level | When | Teller sees |
|---|---|---|
| **high** (pause recommended) | H1: two or more core groups, **or** H2: one core group + pressure + (cover mismatch or risky counterpart) | Pause recommendation, hold line, the claims that fired |
| **elevated** | Any core group, cover mismatch, or risky counterpart | "Ask more", with the next question |
| **low** | Otherwise | Nothing intrusive |

Applied to the 80 recorded spike outputs (runs 1, 2, 3 and 3b): no pause on any legitimate turn,
Tanaka pauses at c4 in every run, and the son-in-trouble case pauses at c3 or c4.
These thresholds were tuned on that small set, so treat them as a starting point for the evaluation,
not a result.

The pause is a recommendation. The teller decides, and a pause with only one source is allowed with
a logged warning (DA 11).

### Approved wording

Anything the teller reads out comes from a question bank: the general bank or an approved
playbook's bank. The model returns an ID. Code checks the ID exists (otherwise the turn falls back
to `q.general.purpose` and the miss is logged) and fills slots like `{payee_name}` from verified
case data.

Each turn, the bank shown to the model **leaves out questions already suggested in this case**. In
spike run 3 the model suggested the same question on four turns in a row, despite being told not
to, so code enforces it. If every question has been used, the console shows no new question. Banks follow the R1 guidance: ask what the money is for, never "are you being scammed?"
(だまされていませんか), check documents, call the family member on a number the customer already
knows.

`validate.py` rejects banned wording (dementia, memory, lying, "are you being scammed?") and slots
that don't match their placeholders.

## Boundaries the schemas enforce

- **Contact brief:** `additionalProperties: false` and no field for the balance, account numbers,
  the counterpart or other customers, so leaking them would be a schema error (DA 6).
  `validate.py` also checks that the brief discloses nothing the wishes don't allow.
- **Call templates:** contain no amounts (checked), and each template has a fallback used when a
  required field isn't disclosable.
- **Contact view:** `nature` is always `"information"` (DA 4). `reached` is true only when both the
  caller number and the case code matched.
- **Playbooks:** structured fields only (CR 11), and every source has `published_at` for the
  evaluation date split (CR 16, CR 28).
- **Evidence card:** no likelihood numbers, no age, and every inference must cite facts or quotes
  on the card.

## Naming

All IDs use one style, dots between parts and underscores inside them: `pb.fake_police.safe_account`,
`q.fake_police.what_said`, `h.general.protect`, plus the enum values `fake_police`,
`relative_in_trouble`. In spike run 3, mixing hyphens and underscores made 9 of 20 outputs fail,
because the 12B model blended the two styles. With one style, 1 failed (run 3b). The build also uses
**constrained decoding** (schema-enforced output) so these slips can't reach the case service.
