# Plan: Apply the architecture reviews to the Mimamori docs

> **Status: applied 2026-10-12** (except step 0, the Gemma spike). Deviation: L2 ended up as three
> views (2a counter path, 2b family call, 2c offline jobs, with the watchlist loader in 2c) for
> readability. Results are tracked in [`../decisions.md`](../decisions.md).

Inputs: [`reviews/devils-advocate-review.md`](../reviews/devils-advocate-review.md) (20 items, "DA #n") and [`reviews/review-response-plan-critique.md`](../reviews/review-response-plan-critique.md)
(round 1: CR #1–14, round 2: CR #15–23). Updated 2026-10-12.

## Context

The first review found 20 issues in `Mimamori_Solution.pdf` and the C4 docs. Two rounds of
critique on this plan followed:
- **Round 1** found the same-bank mule requirement, the over-reliance on advance wishes, the
  missing police step, the scam-sounding call, the weak evaluation baseline, and two
  misplaced responsibilities.
- **Round 2** found that nobody had decided who answers the callback, that the evaluation could
  leak answers into its own test set, that transcript evidence couldn't be cited, that the pause
  had no clear legal basis, that the status-quo baseline was a strawman, and that the watchlist
  loader was in the wrong container.

The user made six design decisions across these rounds.

Outcome:
- The three C4 docs and their diagrams agree with all decisions below.
- `decisions.md` traces each review item to how it was resolved.
- `deck-changes.md` lists the edits for the PDF.
- A **priority-ordered build list** keeps the demo working end to end if time runs out.

No application code is written in this plan.

## Decisions

| Ref | Decision |
|---|---|
| DA #1, CR #1, CR #21 | Tanaka case = **¥3,000,000 counter transfer to a same-bank mule account** (4 days old, 7 payers this week). Cover story: paying the renovation contractor. In step 8, **a fraud analyst decides to freeze** the mule account the bank holds (logged; cite the Furikome Sagi Relief Act after verifying it) and the six other payers surface for outreach. Cross-bank fan-in needs industry data sharing (designed, not built). Cash handover: language layer only, stated. |
| DA #4, CR #18 | **Basis for the pause.**<br>- **With advance wishes:** Keiko pre-agreed a cooling-off pause she **cannot cancel at the counter**, capped at 24 h or end of business day. The teller applies it. This is what the wishes add over bank policy, together with the family contact and the disclosure rules. It's stated as a contractual arrangement that needs legal review.<br>- **Without wishes:** bank policy can only ask her to wait voluntarily, plus police notification.<br>- Yuki's reply is **information** (`contact_view`), never an instruction. |
| CR #2 | **The copilot and evidence card are the headline value for every customer.** Advance wishes are an upgrade, offered at routine counter visits. |
| CR #3 | **Police notification** is a teller action alongside the family call. The handover is a printable evidence-card summary. APPI basis: property-protection exception (verify before citing). |
| DA #13, CR #4, CR #5, CR #15 | **Contact call.**<br>- **Outbound turn 1:** "Branch X calling about your mother. Please call back on our published number and quote case code NNNN." The wishes must explicitly consent to this notice, because it is itself a small disclosure.<br>- **Callback:** the phone menu on the published number routes "returning a call about a case" to the **conversation agent**. The agent verifies **caller number = the locked number on file AND the case code**. Both checks are **built**. The manager can take over at any time.<br>- **Each turn:** STT → Gemini classifies the intent (what happened / is she safe / how much / what should I do / other) → code fills Japanese templates from the brief → Gemini writes connecting phrases only → rule check → TTS. No Live API.<br>- **"Contact suspected" triggers** (no call is made): the contact's number was changed recently, the contact is linked to the payee or counterpart, or a teller or customer note flags them. |
| DA #10, CR #8, CR #17 | Evidence-card claims come in **two types**, and citations can point to **two kinds of source**.<br>- **Claim types:** a `fact` cites `tool_result.field` and code checks the value. An `inference` must cite at least one verified fact or quote, and is shown as a hypothesis.<br>- **Quote sources:** `transcript:{turn_id}` plus the quoted words, checked by exact substring match in code.<br>- **Metric:** "facts and quotes verified against source; every inference grounded". |
| DA #17, CR #6, CR #7, CR #16, CR #19 | **Three-way evaluation.**<br>- **Arms:** (a) today's counter check, built from **published teller-check guidance** (police or bankers' association; source to be found and cited); (b) statistics only; (c) full Mimamori.<br>- **One teller-behaviour assumption** applies to all three arms (e.g. "teller follows the recommendation").<br>- The age rule is kept only for the ATM argument in §1.<br>- **Held-out set:** adapted from public fake-police cases, using a **date split**: playbooks only from alerts published before date T, test cases only from after T. Reported as a case-by-case failure analysis.<br>- **Synthetic population:** rates reported with the circularity stated. A separate judge model or prompt is used. |
| CR #9, CR #10, CR #20 | **Scoring** owns baseline computation, smart limits and the counterpart graph. A separate **watchlist loader job** (deterministic, scheduled, no `case-db` grant, outbound internet) writes the lists to its own collection, and Scoring reads it. The simulation job only seeds synthetic transactions. |
| DA #15, CR #11 | Learning-loop proposals live in `case-db`. Only **structured playbook fields** cross into `intel-db`, after analyst approval. |
| CR #13 | `decisions.md` opens with: "Overrides `Mimamori_Solution.pdf` where they differ, until the deck is regenerated." |

## Step 0: Gemma spike (first, about half a day)

**Pass criteria, fixed before running (CR #22).** On about 20 handwritten counter turns in colloquial elderly Japanese:
1. Detects the renovation cover story and the secrecy line in the Tanaka transcript.
2. No accusing or diagnosing wording in any suggestion.
3. Structured output validates against the schema on at least 19 of 20 turns.
4. Under about 3 s per turn on the deployed endpoint.

**Outcomes:**
- **Pass:** the copilot stays on Gemma.
- **Fail on 1–3:** the copilot moves to Gemini in-region.
- **Fail on 4 only:** try a smaller Gemma or a bigger GPU before switching.
- **If GPU quota blocks the spike:** the docs use the label "copilot model (Gemma; fallback Gemini)", to be settled after the spike.

## Files

Under `docs/`:
- `architecture/c4-context.md`, `architecture/c4-containers.md`, `architecture/c4-dynamic-tanaka.md`; PNGs in `architecture/diagrams/`
- **new** `decisions.md`
- **new** `deck-changes.md`
- `reviews/devils-advocate-review.md` and `reviews/review-response-plan-critique.md`: add one link line to `decisions.md` at the top of each

**Rendering:** extract the mermaid blocks to the scratchpad, then run
`npx -y @mermaid-js/mermaid-cli@11.4.2 -i <mmd> -o architecture/diagrams/<png> -w 2000 -b white`. Don't put `;` inside
message text in sequence diagrams.

## Changes by file

### `c4-context.md`
- **Boundary notes (DA #2):**
  - List every path by which case information leaves the bank's project: STT, Gemini (filtered brief, the contact's speech), TTS and telephony.
  - Reframe the claim as "reasoning over customer records is self-hostable with open weights".
  - Add the managed-STT caveat, with Kotoba-Whisper as the designed self-host option.
- **Police:** add as an external person (CR #3).
- **Telephony:** now carries the outbound notice and the inbound callback (CR #15).
- **Transaction paths:** note the pre-transaction path (counter and large transfers) and the post-transaction path (ATM/app) (DA #7, #9).
- **"Next" section:** replace the stale version (DA #20).

### `c4-containers.md`
**Diagram 2a (live):**
- **Scoring:** new container. Cloud Run with a minimum of one instance and no LLM. It holds baselines, smart limits and the counterpart graph. Flow: Core banking → Scoring → case service.
- **Watchlist loader job:** new container. It writes to its own collection, and Scoring reads it (CR #20).
- **Conversation service:**
  - Tech: "Python, Gemini Flash · intent → templates · rule check".
  - Uses STT and TTS.
  - Handles the outbound notice and the verified inbound callback (CR #15).
- **Web UI → case service:** counter audio over **WebSocket**, card updates over SSE. Draw the brief and the outcome as separate arrows (DA #20).
- **Identity-aware login** (IAP / roles) as a note (DA #14).
- If 2a goes over 20 elements, move the loader job to 2b.

**Diagram 2b (offline):**
- **Simulation job:** seeds synthetic transactions only, in a synthetic-only environment (DA #16).
- **Learning loop:** case service → proposals in `case-db` → analyst → structured fields → `intel-db` (CR #11).
- **Intelligence job:** records each alert's publication date, which supports the date split (CR #16).

**Text sections:**
- **IAM (DA #16):** only Scoring and the case service can use `case-db`, through **IAM conditions on each Firestore database**. Neither the loader job nor the Gemma endpoint has a database grant.
- **Untrusted inputs (DA #3):** payee names, memos and transcripts go in a delimited data block. Tools are read-only. Output must match a schema. The model only suggests.
- **Failure modes (DA #7):** scoring runs before the transaction only for counter and large transfers. If scoring is down, the transaction proceeds under existing controls.
- **Cost (DA #8):** model calls scale with alerts. The GPU endpoint has a fixed floor, so undeploy it between sessions.
- **Production design (not built):** append-only audit sink, ATM/app rules path, cross-bank fan-in.
- **Tables and lists:** update the container table, the PDF-component mapping and the open items.

### `c4-dynamic-tanaka.md`
**A, step 2:** Scoring monitors the school-fee withdrawal after the transaction. There's no "allow" round-trip (DA #7).

**B, step 3:** counter transfer of ¥3,000,000 to a **same-bank** account named カ）…, 4 days old, with 7 payers (no "elderly"). Audio streams over WebSocket.

**B, step 4:** code checks every fact against its field and every quote by exact substring, and drops any inference without verified grounding (CR #8, CR #17).

**B, step 5:** the "fake-police" inference cites `transcript:t3`「警察の人に、誰にも言うなと」plus the counterpart facts.

**B, step 6:** the pause.
- **Basis:** either the non-cancellable cooling-off pause from Keiko's wishes or a voluntary wait under bank policy (CR #18).
- **Single-source pause:** allowed, with a logged warning (DA #11).
- **Police:** the teller notifies them with the printed summary (CR #3).

**C, step 7:** the family call.
- **Suspicion check:** run the "contact suspected" check first.
- **Brief:** built in code, without other customers' facts or the balance (DA #6).
- **Outbound notice:** includes the case code. Yuki calls the published number, the phone menu routes her to the agent, and the agent checks the caller number and the case code (CR #15).
- **Turn loop:** STT → intent → template fill → connecting phrases → rule check → TTS.
- **Outcome:** `contact_view {concerned, coming_to_branch}`.
- **Alt branches:**
  - no wishes → police and manager only
  - contact suspected → no call
  - verification fails → no disclosure, flagged to the teller
  - wishes changed in-branch during an open case → frozen, previous contact notified (DA #12)

**C, step 8:** the analyst decides to freeze the mule account, which is logged. Six others surface for outreach (CR #1, CR #21).

**Design points:** update the list to match.

### `decisions.md` (new)
- Override line (CR #13).
- The decisions table.
- One row for each DA #1–20 and CR #1–23: resolution → file(s) → status (doc / designed-not-built / build-time / cut).

### `deck-changes.md` (new)
A checklist of PDF edits:
- **Region:** cover, §8 and §11 → prototype `asia-south1`, production `asia-northeast1`.
- **§3:** the copilot is the value for every customer, and wishes are an upgrade. Add the cooling-off pause and what it adds over bank policy.
- **§9:**
  - same-bank transfer
  - the police step
  - the case-code callback
  - Yuki's reply is information, not instruction
  - the analyst-decided freeze, with "surfaces six"
  - remove "elderly"
- **§6.4:** the voice path, and "Gemini understands what the family member asks; approved wording answers".
- **§8:** reframe the privacy claim and add the managed-STT line.
- **§10:**
  - three-way comparison against cited teller-check guidance
  - the shared teller assumption
  - the date-split public-case failure analysis
  - the circularity statement
  - the renamed metric
- **Additions:**
  - APPI consent for counter transcription
  - cash-handover and ATM/app limits
  - cross-bank fan-in as future work
- **Q&A prep:** why an AI call rather than the manager. Answer: staff time, after-hours cases, consistent disclosure, an audit trail, and the manager can take over at any time.

### Memory
Update `mimamori-project-decisions.md` with a summary of the decisions table.

## Build order (CR #23; recorded in `decisions.md`)

Each step leaves a working end-to-end demo.
1. **Teller console + Scoring + counter copilot.** Typed input is the demo fallback in case STT misbehaves. The evidence card is seeded data at this stage.
2. **Investigation agent** with fact and quote verification. It replaces the seeded card.
3. **Contact call:** outbound notice, verified callback (number + case code), intent → templates.
4. **Evaluation:** three-way comparison on synthetic data, plus the date-split public-case failure analysis.
5. **Live intelligence job.** Until it's built, a seeded approved playbook stands in.

**Designed, not built:**
- learning loop
- ATM/app path
- cross-bank fan-in
- append-only audit sink
- the voice version of advance-wishes onboarding (Keiko's wishes are seeded as data)
- the real phone menu (simulated in the browser)

## Out of scope (next, after this plan)
1. **Schemas:**
   - evidence card (fact/inference claims; tool and transcript sources)
   - playbook (structured fields, `published_at`)
   - advance wishes (cooling-off window, contact, disclosure, notice consent, locked number)
   - `contact_view`
   - call intents and templates
2. **Research:** find and cite the published teller-check guidance for arm (a), choose date T, and source the post-T public cases.

## Verification
- **Rendering:** all 6 PNGs render without parse errors. Check each one by eye for overlapping or illegible labels.
- **Leftover wording:** `grep` across `docs/architecture/*.md`, `docs/decisions.md` and `docs/deck-changes.md` finds none of:
  - `Live API`
  - `instruction: hold`
  - `protects seven`
  - `elderly customers paying`
  - `only path by which`
  - `withdrawal of ¥3,000,000` / `¥3,000,000 in cash`
  - `Gemma endpoint can read`
  - `asia-northeast1` (except where it's labelled production)
  - "release if any reason"
- **Traceability:** every DA #1–20 and CR #1–23 appears in `decisions.md` with a resolution.
- **Diagram size:** diagram 2a has 20 elements or fewer.
