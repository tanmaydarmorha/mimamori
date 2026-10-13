# Devil's-advocate review: Mimamori architecture

> Resolutions: see [`../decisions.md`](../decisions.md).

Reviewed: `Mimamori_Solution.pdf` (all 11 pages) and `docs/architecture/` ([`c4-context.md`](../architecture/c4-context.md),
[`c4-containers.md`](../architecture/c4-containers.md), [`c4-dynamic-tanaka.md`](../architecture/c4-dynamic-tanaka.md)). Date: 2026-10-12.

These are the flaws a sharp judge or a bank's risk team is likely to raise, worst first.

## Tier 1: problems that could break the demo or the pitch

### 1. The hero case has no counterpart account

Keiko asks for ¥3,000,000 in **cash** (PDF §9 step 3). A cash withdrawal has no payee. Even so,
step 3 says "the counterpart account is four days old with seven payers," and step 8 asks "who else
paid this account?" Fake-police scams usually collect cash in person, so the graph layer has nothing
to look at.

**Fix:** either show an earlier transfer from Keiko to the mule account, or make the case a transfer.
As written, the scoring evidence and the "one detection protects seven" payoff come from data that
can't exist.

### 2. The Gemma/Gemini privacy split doesn't hold up

- Keiko's raw speech at the counter, which is the most sensitive data in the system, goes to
  **Cloud STT**. That's a Google-managed API, the same kind of service as Gemini on Vertex.
- The PDF's own fallback in §12 is "Gemini on Vertex in-region for the copilot." If that's
  acceptable, the rule was never a hard requirement.
- Vertex Gemma is also a Google-managed endpoint.

**Fix:** make the argument **"self-hostable with open weights,"** not "no external model API."
Also correct `c4-context.md`, which says telephony is "the only path by which case information
leaves the bank." That's false: STT, TTS and Gemini (with the brief, Yuki's speech and the
onboarding speech) all receive case information.

### 3. Attacker-controlled text reaches Gemma without review

The docs say "public text never reaches the Gemma path unreviewed." But the scammer controls:

- the payee name, which feeds `explain_payee`
- transfer memos
- what the customer has been coached to say, which feeds the copilot

Analyst approval only covers playbooks.

**Fix:** give these inputs the same untrusted-input handling as public alerts.

### 4. Yuki has no legal authority, and Keiko's live wishes get overridden

"Hold it, I'm coming" has no legal effect on Keiko's deposit. She can demand her own money. The PDF
says the call "honours a recorded instruction rather than overriding a live one," but it does
override her live request. Right now `contact-outcome {instruction: hold}` treats Yuki's reply as an
instruction.

**Fix:** have the advance wishes grant a time-limited cooling-off pause ("pause up to N hours and
call my daughter"), and frame Yuki's reply as information, not an instruction.

### 5. Nobody checks who answered the phone

The agent tells whoever picks up that Keiko is at the bank and a large withdrawal was paused. That
could be a wrong number, a changed number, or a scammer who has taken over the contact. There's also
no defence against the trusted contact being the abuser, and family members are a big share of elder
financial abuse.

**Fix:** verify the person who answers before disclosing anything, and plan for a contact who may be
the abuser.

### 6. The brief sent to Gemini leaks other customers' data

The brief is built "from card + disclosure policy," and the card's "why" includes the counterpart's
fan-in. Telling Yuki "seven other people paid this account" discloses information about other
customers. Keiko's disclosure policy can't authorise that.

**Fix:** keep facts about other customers out of the brief.

## Tier 2: architecture problems

### 7. The case service is on the authorisation path for every transaction

Step 2 shows `Core → Case: POST /events/transactions` and `Case → Core: allow`. That makes a
scale-to-zero Cloud Run service, which also runs LLM agent loops, a synchronous dependency for every
transaction. The docs don't say whether it fails open or fails closed.

**Fix:** split scoring from the LLM workloads and state the failure mode. If scoring is meant to be
asynchronous, fix the diagram.

### 8. "Cost grows with alerts" isn't true for Gemma

A Vertex GPU endpoint keeps at least one replica running all the time, so you pay around the clock
regardless of alert volume. Hackathon credits will feel this too.

### 9. ATM and app alerts have nowhere to go

The funnel only reaches a human when "a human is with the customer." Cash-card handovers, ATM
transfers and app transfers raise alerts and then stop. Those are where much of the 2025–26
fake-police money moves.

### 10. The citation guardrail only checks format

"Drop any claim without a citation" confirms a citation is present, not that the cited tool result
supports the claim. So the "Explainability 100%" metric is true by construction and tells a judge
nothing.

**Fix:** add a structured claim → field check, or an entailment pass.

### 11. "Never act on a single source" contradicts "a human decides every hold"

If code blocks a teller's pause because there's only one source, the human isn't deciding.

**Fix:** pick one: block it, or allow it with a logged warning.

### 12. The advance wishes are themselves an attack surface

A coached customer could change the trusted contact's phone number or loosen thresholds on the day.
"Never go against recorded wishes" then works for the scammer.

**Fix:** add a cooling-off period for changes to wishes, and alert the previous contact when they
change.

### 13. The disclosure checker shares failure modes with what it checks

- Gemini checks Gemini.
- The rule check for amounts and account numbers has to handle 三百万円, 300万, spoken numbers and
  readings in kana, which a regex won't.
- The voice loop (Live API → text → second Gemini call → TTS) costs about 2–4 s per turn, which will
  feel slow on a phone call.
- If the output is text anyway, the Live API is just doing STT plus an LLM. Check that your chosen
  Live model actually supports text-only output.

### 14. Containers and responsibilities are missing

- **No authentication or identity anywhere.** One SPA serves the teller, the analyst, the customer
  and "Yuki's phone."
- **No baseline-computation job.** Baselines are stored in `case-db`, but nothing computes them.
- **No watchlist refresh job.**
- **The audit log sits in mutable Firestore.** It should be append-only, for example a log sink to
  BigQuery or GCS with a retention lock.

### 15. The learning loop mixes data classes

Proposals come from teller dismissal reasons, which are customer data, and become playbook updates
in `intel-db`. That database is classified "No customer records," and Gemini-side services read it.
The write path from the case service to `intel-db` for proposals isn't drawn.

### 16. IAM statements are slightly wrong

- "Only the case service **and the Gemma endpoint** can read `case-db`": a model endpoint shouldn't
  hold a database grant.
- Per-database Firestore access needs IAM **conditions**, not plain roles. State that explicitly.
- The boundary is enforced only at the database. Any caller of the case service API, including the
  simulation job, which forwards evidence cards to Gemini for LLM-as-judge, can move customer data
  to Gemini.

## Tier 3: evaluation and claims

### 17. The age-rule baseline is a strawman, and it's the wrong comparison

- "≥50% fewer healthy customers restricted" than a rule that restricts everyone over 70 is almost
  guaranteed.
- The Osaka cap limits ATM transfers, but Mimamori acts at the counter.
- Gemini writes the population, the scam injections and the role-played victims, and also judges
  the cards. That loop is circular.
- Role-played LLM victims have stylistic tells a model can pick up on.

Judges will discount these numbers unless you call out the circularity yourself.

### 18. Small claims that undercut the pitch

- "Seven **elderly** customers paying into it": you've just used age, after saying age is never a
  feature.
- "One detection protects seven": six of them have already paid. Say "surfaces" or "helps recover."
- Recording a customer's voice at the counter needs consent under APPI, and the docs don't mention
  it.

### 19. Region contradictions

The PDF says `asia-northeast1` in three places, including the requirements table ("Deployed on
Google Cloud: Cloud Run, asia-northeast1"), and promises "speech-to-text in-region." The prototype
deploys to `asia-south1`.

**Fix:** correct the deck before submitting. Also confirm early that the Live API, Chirp's ja-JP
streaming and Gemma GPU quota exist in `asia-south1`; Live API region support is narrow.

### 20. Smaller doc inconsistencies

- In L2 the Web UI talks to the case service over REST + SSE, but the copilot needs streaming audio,
  which needs a WebSocket or gRPC.
- The L2 diagram draws `casesvc → contactsvc` as one call that "gets outcome." But the call lasts
  minutes and `Conv → Case` posts the outcome back separately, so the reverse arrow is missing.
- The "Next" section of `c4-context.md` is stale and lists containers that don't match L2.

## Scope check

That's 17 elements, 5 deployables, a GPU endpoint, the Live API, STT, TTS and two databases, all for
a 3-minute video. The highest-risk dependency is whether Gemma understands colloquial elderly
Japanese, and that's also the centrepiece.

**Recommendation:** test Gemma on the Tanaka transcript this week, before building anything else,
and decide on the Gemini fallback now rather than mid-build.

## Doc-only fixes

These items need only documentation changes: 2, 14, 16, 19, 20.
