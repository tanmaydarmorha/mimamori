# Decisions

> **This file overrides `Mimamori_Solution.pdf` where they differ, until the deck is regenerated.**
> Deck edits are listed in [`deck-changes.md`](deck-changes.md).

Sources:
- [`reviews/devils-advocate-review.md`](reviews/devils-advocate-review.md) (DA #1–20)
- [`reviews/review-response-plan-critique.md`](reviews/review-response-plan-critique.md) (CR #1–28)
- [`plans/review-response-plan.md`](plans/review-response-plan.md)

Applied to the architecture docs on 2026-10-12.

**Status key:**
- **doc:** reflected in the architecture docs
- **build:** built in the prototype
- **designed:** designed, not built
- **research:** needs sourcing before use

## Design decisions (user, 2026-10-11 / 2026-10-12)

| Topic | Decision |
|---|---|
| Spec and region | PDF is the spec; `PROPOSAL.md` deprecated. Prototype region `asia-south1`, production `asia-northeast1`. |
| Deployables | Split by trust boundary. Firestore `case-db` / `intel-db` / `ref-db`, with IAM conditions per database. |
| Hero case | ¥3,000,000 **counter transfer to a same-bank mule account**. Cover story: renovation contractor. |
| Pause basis | With wishes: pre-agreed cooling-off pause: at least `minimum_hours`, extended to the next business-day close, capped at 24 h (CR 25). **A delay, not a prohibition:** she can override once the nominated contact has been reached, or after manager review with a second confirmation (R5, 2026-10-12). Without wishes: voluntary wait under bank policy, plus police. |
| Police handover | Teller **notifies** the police. The evidence summary goes to attending officers **on request**, limited to what they ask; officer name and title logged. Basis: APPI Art. 27(1)(i) via CCP Art. 197(2); (iv) secondary (R4, 2026-10-12). |
| Freeze basis | Furikome Sagi Relief Act Art. 3(1): suspension measures on the bank's own account on suspicion; police information not required. Transfer-based fraud only (R3, confirmed). |
| Contact reply | **Information** (`contact_view`), never an instruction. |
| Callback | Answered by the **AI agent**, which first says it is an automated assistant and that the call is recorded (CR 26). Checks caller number = locked number on file **and** case code. This lets the family verify the bank and blocks strangers; it is not proof of the contact's identity, which rests on the number verified at registration and locked during the case (CR 24). |
| Voice path | STT → Gemini Flash intent → code templates → rule check → TTS. **No Live API.** |
| Evaluation | Three-way (today's counter check / statistics only / Mimamori), date-split public held-out set, failure analysis. Arm (a) = NPA request + Akita five-step routine + Okayama practice (R1). T = 2026-04-01, held-out set to be completed from Tokyo, Saitama and Osaka bulletins (R2). |
| Copilot model | **Gemma** (step-0 spike passed criteria 1–3 on 2026-10-12, local `gemma4:12b` Q4; latency on Vertex still to check). The model extracts indicators, checks the cover story and picks a question ID. **Code computes risk and the pause**, and all teller wording comes from approved banks. Constrained decoding is required. See [`../schemas/README.md`](../schemas/README.md) and [`../spikes/gemma-copilot/RESULTS.md`](../spikes/gemma-copilot/RESULTS.md). |

## Devil's-advocate review (DA)

| # | Issue | Resolution | Where | Status |
|---|---|---|---|---|
| DA 1 | Cash withdrawal has no counterpart account | Counter transfer to a same-bank mule. Cash handover: language layer only | dynamic B, C; context | doc, build |
| DA 2 | Gemma/Gemini privacy split overstated | Claim reframed as "reasoning self-hostable with open weights". Every egress path listed. Managed-STT caveat, Kotoba-Whisper option | context | doc |
| DA 3 | Attacker text reaches Gemma | Untrusted data block, read-only tools, schema output, model only suggests | containers | doc, build |
| DA 4 | Yuki has no authority; live wishes overridden | Pre-agreed cooling-off pause as a delay with a defined override. `contact_view` is information | dynamic B, C | doc, build |
| DA 5 | Nobody checks who answers | Notice reveals nothing. Callback verified by number + case code. Contact-suspected triggers | dynamic C | doc, build |
| DA 6 | Brief leaks other customers' data | Brief built in code without the balance or other customers' facts | containers, dynamic C | doc, build |
| DA 7 | Case service on every transaction's path | Separate Scoring (min 1 instance, no LLM). Pre-transaction only for counter / large transfers. Fails open to existing controls | containers, dynamic A | doc, build |
| DA 8 | "Cost grows with alerts" false for Gemma | Fixed GPU floor stated. Undeploy between sessions | containers | doc |
| DA 9 | ATM / app alerts have nowhere to go | Rules-only post-transaction path | context, containers | designed |
| DA 10 | Citation check is format-only | Fact / inference claim types with value checks (see CR 8, 17) | dynamic B | doc, build |
| DA 11 | "Single source" vs "human decides" | Teller never blocked. Single-source pause logged as a warning | dynamic B | doc, build |
| DA 12 | Wishes are an attack surface | Changes during an open case frozen. Previous contact notified | dynamic C | doc; designed |
| DA 13 | Disclosure checker shares failure modes; latency; Live API | Intent + templates + rule check. No second Gemini check. No Live API | containers, dynamic C | doc, build |
| DA 14 | Missing auth, baseline job, watchlist refresh, mutable audit | IAP with roles. Baselines in Scoring. Watchlist loader job. Append-only audit sink designed | containers | doc; audit designed |
| DA 15 | Learning loop mixes data classes | Proposals in `case-db`. Only structured fields to `intel-db` | containers 2c | doc; designed |
| DA 16 | IAM statements wrong | Only Scoring and the case service can use `case-db`, via IAM conditions. Model endpoint has no grant. Simulation job runs in a synthetic-only environment | containers | doc |
| DA 17 | Age-rule baseline is a strawman | Three-way evaluation (see CR 6, 7, 16, 19) | deck-changes | doc; research |
| DA 18 | "Elderly", "protects seven", APPI consent | Removed / "surfaces six others" / consent line added | dynamic, deck-changes | doc |
| DA 19 | Region contradictions | Prototype `asia-south1`, production `asia-northeast1` | all docs, deck-changes | doc |
| DA 20 | REST for audio, missing callback arrow, stale "Next" | WebSocket audio. Brief and outcome as separate arrows. "Next" rewritten | containers, context | doc |

## Plan critique (CR)

| # | Issue | Resolution | Where | Status |
|---|---|---|---|---|
| CR 1 | Mule must be same-bank | Same-bank mule. Cross-bank fan-in needs industry sharing | dynamic B, C | doc; cross-bank designed |
| CR 2 | Most victims lack wishes | Copilot and card are the headline value for everyone. Wishes offered at routine counter visits | context, deck-changes | doc |
| CR 3 | Police missing | Teller notifies police. Summary to officers on request (APPI 27(1)(i), R4) | context, dynamic B | doc, build |
| CR 4 | AI call sounds like a scam | Notice reveals nothing, asks for a callback on the published number with a case code | dynamic C | doc, build |
| CR 5 | Brief alone can't stop invention | Gemini classifies intent. Code fills approved templates. Gemini writes connecting phrases only | dynamic C | doc, build |
| CR 6 | Age rule is the wrong counter baseline | Arm (a) = today's counter check. Age rule only for the §1 ATM argument | deck-changes | doc; research |
| CR 7 | n=25 can't support rates | Held-out set adapted from public cases, reported as failure analysis | deck-changes | build; research |
| CR 8 | Inferences can't be value-checked | `fact` vs `inference`. Inferences cite verified facts or quotes and are shown as hypotheses | dynamic B | doc, build |
| CR 9 | Baselines in the simulation job | Baselines in Scoring | containers | doc, build |
| CR 10 | Watchlist loader in the intelligence job | Separate loader job (corrected by CR 20) | containers 2c | doc, build |
| CR 11 | Who anonymises learning-loop data | Only structured playbook fields cross | containers 2c | doc; designed |
| CR 12 | Run the Gemma spike first | Spike run: passed criteria 1–3, the copilot stays on Gemma | spikes/gemma-copilot | done; latency pending |
| CR 13 | Which document wins | Override line at the top of this file | this file | doc |
| CR 14 | Over-broad grep check | Grep for "withdrawal of ¥3,000,000" | plan | doc |
| CR 15 | Who answers the callback; identity check unbuilt | AI agent, number + case code, both built. Notice consent in wishes. Suspicion triggers | dynamic C, containers 2b | doc, build |
| CR 16 | Test leakage from shared sources | Date split: playbooks before T, test cases after T. `published_at` kept | containers 2c, deck-changes | build; research |
| CR 17 | Transcript can't be cited | `transcript:{turn_id}` + quote, checked by the quote rule (see CR 27) | dynamic B | doc, build |
| CR 18 | Cooling-off vs no-wishes path | With wishes: delay up to 24 h, override after contact reached or manager review (R5). Without: voluntary wait | dynamic B, C | doc; legal review |
| CR 19 | Status-quo baseline is a strawman | Arm (a) from NPA request + Akita five-step routine + Okayama practice (R1). Amount threshold is a stated parameter. One shared teller assumption | deck-changes | doc |
| CR 20 | Loader in Scoring opens internet access | Separate loader job, no `case-db` grant, writes `ref-db` | containers 2c | doc, build |
| CR 21 | Freeze needs a human decision | Analyst approves the freeze. Logged | dynamic C | doc, build |
| CR 22 | Spike pass criteria | Fixed before the run; 1–3 passed, 4 (latency) not tested locally | spikes/gemma-copilot/RESULTS.md | done; latency pending |
| CR 23 | Build list needs priority order | Ordered list below | this file | doc |
| CR 24 | Callback check overclaims | Described as "lets the family verify the bank, blocks strangers", not identity verification | dynamic C, deck-changes | doc |
| CR 25 | End-of-day pause can be 30 min | `minimum_hours`, extended to next business-day close, capped at 24 h | schemas/advance-wishes.json, dynamic B | doc, build |
| CR 26 | Callback needs AI and recording notice | Agent's first callback turn says so | dynamic C, deck-changes | doc, build |
| CR 27 | Absence facts and fragile quote matching | Tools return counts (e.g. `contractor_payments_count_12y = 0`). Quote rule: exact, then NFKC + whitespace-stripped, across customer turns; wrong turn ID corrected, unfound quote dropped (spike: 2 failures, both handled) | schemas/README.md, dynamic B | doc, build |
| CR 28 | Seeded playbook must follow the date split | Every playbook source has `published_at`. Seeded playbook dated before T and not from a held-out case | schemas/playbook.json | build |

## Build order

Each step leaves a working end-to-end demo.

1. **Teller console + Scoring + counter copilot.** Typed input as a fallback. Seeded evidence card.
2. **Investigation agent** with fact / quote verification.
3. **Contact call:** notice, verified callback, intent → templates.
4. **Evaluation:** three-way on synthetic data, plus date-split public-case failure analysis.
5. **Live intelligence job.** A seeded approved playbook stands in until then.

**Designed, not built:**
- learning loop
- ATM / app path
- cross-bank fan-in
- append-only audit sink
- voice onboarding for advance wishes (wishes seeded as data)
- real phone menu and telephony (simulated in the browser)

## Open research

Briefed in [`research.md`](research.md) (R1–R5).


- ~~**Arm (a):** published teller-check guidance~~ Done (R1, likely): no national question list exists; arm (a) is built from the NPA request, Akita's five-step routine and Okayama practice.
- **Evaluation data:** T = 2026-04-01 kept. About 10 detailed cases found; **R2b** harvests Tokyo, Saitama and Osaka bulletins to reach 20.
- **Legal checks:**
  - ~~Furikome Sagi Relief Act basis for freezing~~ Confirmed, Art. 3(1) (R3)
  - ~~APPI basis for the police handover~~ Confirmed, Art. 27(1)(i) via CCP 197(2); design changed to "on request" (R4)
  - Cooling-off pause enforceability: unresolved; risk reduced by making it a delay with an override (R5). Still needs legal review
  - Whether a prefectural ordinance (Osaka Art. 21(3) report duty) counts as "法令" under APPI 27(1)(i)
- **Spot-check before slides:** every source marked "[summary only]" in `research.md`.
- **Availability in `asia-south1`:** Gemma GPU quota and streaming ja-JP Chirp.
- **Gemma, still untested** (see `spikes/gemma-copilot/RESULTS.md`): latency on the Vertex endpoint (criterion 4), pause stability across runs, the "exclude already-suggested questions" rule end to end, real audio through Chirp, and a larger Gemma.
