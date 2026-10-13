# Devil's-advocate review: review-response plan

> Resolutions: see [`../decisions.md`](../decisions.md).

Reviews of [`docs/plans/review-response-plan.md`](../plans/review-response-plan.md), against [`devils-advocate-review.md`](devils-advocate-review.md) and
`Mimamori_Solution.pdf`. Each round covers only the points that would change what gets built or how
it is presented, each with a better option, strongest first.

Items are numbered continuously across rounds (CR #1–14 in round 1, CR #15–23 in round 2,
CR #24–28 in round 3), so references in the plan and in `decisions.md` stay valid.

- [Round 1](#round-1-first-version-of-the-plan): CR #1–14
- [Round 2](#round-2-updated-plan): CR #15–23
- [Round 3](#round-3-final-plan): CR #24–28

---

## Round 1: first version of the plan

Date: 2026-10-12. Most of the plan held up.

### Points that change the solution

#### 1. The new hero case only works if the mule account is at the same bank

Account age ("4 days old") and fan-in ("7 payers this week") are only visible when the receiving
account is at Keiko's own bank. In a normal transfer to another bank, the sending bank sees neither.

**Better:**
- Make the mule account explicitly same-bank in the Tanaka case. This also strengthens step 8: the
  bank can then freeze the account it actually holds, which beats an outreach list.
- State that cross-bank fan-in needs industry information sharing, and list it as designed, not
  built.

#### 2. Most victims won't have advance wishes, so the core value has to work without them

The cooling-off pause, the verified contact and the family call only cover customers who onboarded
earlier. The likely victim mostly hasn't. In the plan, that path is just "teller escalates," which
looks like today's practice.

**Better:**
- Make the copilot and evidence card the headline value for every customer, and present wishes as
  an upgrade.
- Add a line on how onboarding reaches people, e.g. offering it at existing counter visits rather
  than waiting for an incident.

#### 3. Police are missing from the response

At Japanese counters, the usual escalation for suspected fake-police fraud is teller → manager →
call the police. The plan's no-wishes branch says "escalate per bank policy," and the main path only
calls family.

**Better:** add a "notify police" step alongside the family call, with the evidence card as what
gets handed over.

This also fixes a weak spot in the story. Keiko trusts the "police" on the phone, and a call from
the real police counters that directly. Yuki can't.

#### 4. Yuki may think the AI call is itself a scam

Japan has trained families to be suspicious of calls about a parent and money. Starting with
knowledge-based questions ("before I explain, what's your mother's…?") will sound exactly like a
scam.

**Better:**
- The first turn says only that the call is from branch X about your mother, and asks Yuki to call
  back the branch's published number. Disclosure happens on the callback, or once Yuki has verified
  the bank.
- This also replaces most of the identity-check problem (review #5). The number on file should be
  verified when it's registered and locked against changes during an open case, which the plan
  partly has already.

#### 5. Make the contact call structured instead of relying on the brief alone

"The main defence is the brief's content" stops data leaking. It doesn't stop Gemini inventing
things, like "your mother may have dementia" or a wrong amount the rule check misses.

**Better:**
- Gemini only classifies Yuki's turn into an intent: *what happened / is she safe / how much / what
  should I do / other*.
- Code fills in the facts from the brief and uses templates written in polite Japanese.
- Gemini writes free text only for the connecting phrases.

"Zero disclosure violations" then becomes true by design rather than a hope. It's also a better
Gen-AI story, because the model does the understanding and code controls what gets said.

#### 6. "Age rule" is the wrong main baseline for counter transfers

The Osaka cap applies to ATMs. At the counter, the status quo is the generic check tellers already
run on older customers' large transactions, using the poster and script.

**Better:** compare:

- (a) today's generic counter check
- (b) statistics only
- (c) full Mimamori

Keep the age rule only for the ATM-restriction argument in §1. Mimamori is more likely to win
against (a), and judges will accept the comparison.

#### 7. 20–30 team-written conversations can't support rates

At n=25, a detection rate has a confidence interval of roughly ±18 points. And the people who
designed the detector wrote the cases.

**Better:**
- Report it as a case-by-case failure analysis, not a percentage.
- Base the held-out set on publicly reported fake-police cases from police and news write-ups. That
  gives you an independent source, and it addresses the circularity problem more convincingly than
  stating it.

#### 8. Claim verification works for facts, not inferences

A rule that says "the cited `tool_result.field` must match the value" can verify "account age =
4 days." It can't verify "likely coached cover story," and that's the claim that matters most.

**Better:** give the evidence card two claim types:

- **fact**: checked against a tool field
- **inference**: must cite at least one verified fact and is shown as a hypothesis, never as a
  finding

Rename the metric to "facts verified against source; every inference grounded in a verified fact."

### Placement errors in the plan

#### 9. Baselines belong on the customer-data side, not in the simulation job

In production, baselines are computed from real transactions. The simulation job is synthetic-only,
uses Gemini and has no `case-db` grant.

**Better:** put baseline computation in Scoring, or in its own scheduled job with `case-db` access.
The simulation job only seeds synthetic transactions.

#### 10. The watchlist loader should be deterministic code, not part of the intelligence job

It's public data, so loading it there isn't a privacy risk. But the intelligence job is the
untrusted-text-plus-LLM container, and a list used for exact matching shouldn't share a container
with it.

**Better:** use a small loader step, or keep it in Scoring.

> Corrected in round 2 (CR #20): keeping it in Scoring was wrong. Use a separate loader job.

#### 11. Pick one owner for anonymising learning-loop data

"An anonymised playbook change goes to intel-db" doesn't say who removes personal details from
teller free text.

**Better:** an analyst-approved learning-loop proposal can only change structured playbook fields
(new cover-story phrase, payee pattern, payment method). No free text from cases passes into
`intel-db`.

### Process

#### 12. Run the Gemma spike first, not after the doc rewrite

If Gemma can't follow colloquial elderly Japanese, the copilot moves to Gemini and you'd rewrite the
privacy section and the 2a diagram a second time.

**Better:** run about 20 handwritten turns against a Gemma endpoint before any rendering work. It
takes about half a day.

#### 13. Say which document wins until the deck is updated

The plan makes the C4 docs disagree with the PDF, which the project treats as the spec.

**Better:** add one line at the top of `decisions.md`: "Overrides `Mimamori_Solution.pdf` where they
differ, until the deck is regenerated."

#### 14. One verification check needs tightening

Grepping for `withdraw` in the Tanaka case will flag step 2, where the school-fee withdrawal is
correct.

**Better:** grep for "withdrawal of ¥3,000,000" instead.

### A question to have an answer ready for

Why use an AI voice agent for the family call at all, rather than having the branch manager phone
Yuki? Judges will ask this.

A good answer exists: staff time at a busy counter, after-hours cases, consistent disclosure and an
audit trail. The structured call in point 5 makes that answer stronger.

### What's solid and worth keeping as is

- Treating Yuki's reply as information, not an instruction
- The three-way ablation idea, with only the baseline needing to change (point 6)
- Dropping the Live API
- Never blocking the teller, with a logged warning instead
- Splitting Scoring out with a stated failure mode
- Freezing wishes during an open case
- The `decisions.md` traceability file

---

## Round 2: updated plan

Date: 2026-10-12. The plan is in good shape. Most of what's left would only show up once it's
built, so this should be the last review round before the Gemma spike and the schemas.

### Design gaps

#### 15. Nobody has decided who answers Yuki's callback, and the version you'd build has no identity check

The callback pattern sends Yuki to the branch's published number, which goes to the bank's phone
system, not to the conversation service. Choose one:

- **(a) The callback reaches the agent.** The published number's phone menu routes "returning a call
  about a case" to the agent. It matches the caller's number against the locked number on file, plus
  a short case code given in the outbound notice. Caller ID can be spoofed, so the case code matters.
- **(b) A human answers.** The manager takes the callback, and the agent prepares the brief and
  suggests wording on screen, checked against the disclosure policy. This reuses the copilot pattern
  and avoids most of the AI-voice risk.

Either way, the cut list builds the callback conversation but leaves "callback identity locking" as
designed-not-built. As written, the demo would disclose to anyone who calls.

**Better:** build a caller-number check against the number on file. It costs almost nothing in the
simulation.

Two smaller gaps in the same flow:

- The outbound line "Branch X calling about your mother" is itself a small disclosure. It reveals
  that Keiko banks there and that something happened, so the wishes should cover it explicitly.
- "Contact suspected → no call" doesn't say what signal triggers the suspicion.

#### 16. The evaluation can leak the answers into the test

The held-out cases come from public police and news reports. The intelligence job builds playbooks
from those same kinds of public alerts. If a test case and a playbook share a source, the copilot is
being tested on material it was trained on.

**Better:** use a date split. Playbooks come only from alerts published before date T, and held-out
cases only from after T. State the split in §10. That one sentence makes the failure analysis
credible.

#### 17. The copilot's most important inferences cite the transcript, which isn't a tool result

"Secrecy instruction, impersonated police" rests on the customer's words, not on
`tool_result.field`. Under the current rule, which only accepts verified tool-result facts as
citations, those inferences get dropped.

**Better:** make transcript turns a citable source: turn ID plus the quoted span, checked in code by
exact substring match.

#### 18. The cooling-off pause and the no-wishes path don't fit together

If bank policy alone can pause a transaction, as in the no-wishes path, the cooling-off pause adds
nothing. If bank policy can't, the no-wishes path has no legal basis.

**Better:** spell out what the wishes add on top of bank policy:

- a duration the customer pre-agreed to and **can't cancel at the counter during that window**
- the family contact and what may be disclosed to them

The plan still doesn't say whether Keiko can cancel the pause on the spot. That's the question a
bank's lawyer will ask first.

### Evaluation fairness

#### 19. The status-quo baseline is now the strawman

"Release if any reason is given" will lose to anything, and judges will see that.

**Better:**

- Build arm (a) from published guidance for teller checks (police or bankers' association checklist
  items), and cite the source.
- State one teller-behaviour assumption and apply it to all three arms. For example: "the teller
  follows the system's recommendation," or a stated compliance rate.

Without that, Mimamori's gain is partly an assumption about tellers, not a result.

### Correction to round 1

#### 20. Move the watchlist loader out of Scoring

Round 1 (CR #10) suggested "or keep it in Scoring," and that was wrong. Scoring has `case-db` access,
and the loader fetches from public websites. Putting both in one container gives the most trusted
container outbound internet access.

**Better:** use a tiny scheduled job with no `case-db` grant that writes the lists to its own
collection. Scoring reads that collection.

### Smaller points

#### 21. Freezing the mule account needs the same human-decision rule

It freezes another customer's account based partly on statistical evidence.

**Better:** say who decides (a fraud analyst or the operations team) and that the action is logged.
"A human decides every hold" should cover this too.

#### 22. Set the spike's pass criteria before running it

With only 20 turns, it's easy to decide afterwards that it passed.

**Better:** write these down in advance, for example:

- detects the cover story and the secrecy line in the Tanaka transcript
- no accusing or diagnosing wording
- **latency per turn under about 3 s on the endpoint**

Latency could fail the copilot even if Gemma's Japanese is good enough.

#### 23. Order the build list by priority, not just build vs. don't build

If time runs out, the demo should still work end to end.

**Better:** build in this order:

1. Teller console + Scoring + copilot, **with typed input as a demo fallback** in case
   speech-to-text misbehaves
2. Investigation card
3. Callback conversation
4. Evaluation
5. Live run of the intelligence job; until then, seed an approved playbook

---

## Round 3: final plan

Date: 2026-10-12. Every round-2 item was resolved, and the decisions now fit together: the pause
basis, the contact call, citations and the evaluation design all agree. The items below are small.
Three of them only need a sentence each, and the other two are notes for the schema step. After
this, more review rounds will cost more than they find. The next step should be the Gemma spike.

### Wording that would overclaim

#### 24. The callback check proves less than it seems

The case code is sent in the outbound notice to the number on file. Whoever holds that phone gets
both the call and the code. So "caller number + case code" is really one factor, possession of
that phone, counted twice. It stops strangers who dial the published number. It doesn't stop
someone who has taken over the contact's number.

Its real value runs the other way: **Yuki verifies the bank.** She calls a number she can look up,
so she knows the call isn't a scam. Protection against a hijacked contact comes from elsewhere:
the number is verified at registration, it's locked during an open case, and the "contact
suspected" checks run before any call.

**Better:** in the docs and the deck, describe the callback as "lets the family verify the bank;
also blocks strangers calling in." Don't call it identity verification of Yuki. Nothing needs to
change in what gets built.

#### 25. "24 h or end of business day" can leave a 30-minute pause

Counters usually close mid-afternoon. If "whichever comes first" is the rule, a visit shortly
before closing gets a pause too short for Yuki to reach the branch, and the scammer only has to
wait it out.

**Better:** set a fixed minimum, for example "until N hours have passed or the next business day
ends, whichever is later, and at most 24 h." Give the exact window in the advance-wishes schema.

### Missing notices

#### 26. The callback should say it's an automated assistant and is recorded

Yuki is a third party. Her speech goes through STT and Gemini, and it is logged. In Japan she would
expect to be told she's talking to an AI and that the call is recorded. The agent should say so in
its first callback turn, and the deck's governance line should mention it next to the APPI consent
for counter transcription.

### Notes for the schema step

#### 27. Two verification rules will drop valid evidence unless the schemas plan for them

- **Facts about absence.** "No renovation or contractor payments in 12 years" supports the key
  cover-story inference. Its value can only be checked if a tool returns it as a field, for example
  `get_baseline.contractor_payments_count = 0`. Have tools return computed counts, not just lists.
- **Matching quotes word for word is fragile in Japanese.** Models often reword slightly when they
  quote (人 / 方, kana vs kanji, spacing). Either have the model cite the turn ID plus character
  offsets and have code extract the quote, or normalise both sides before matching (NFKC, remove
  whitespace). Otherwise the most important inference (fake police, from the secrecy line) may be
  dropped at random.

#### 28. The seeded playbook must also follow the date split

The intelligence job is built after the evaluation (build steps 5 and 4). That means the evaluation
runs against the **seeded** playbook. It also needs a `published_at` before date T, and its source
alert must not be one of the held-out cases. Otherwise the leak that CR #16 closed opens up again.

### Optional

The traceability table in `decisions.md` will have 43 rows. If time is short, you could keep full
rows only for items that changed the design or what gets built, and group the wording-only fixes
into a single row.
