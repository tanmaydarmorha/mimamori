# Deck changes for `Mimamori_Solution.pdf`

Edits needed so the deck matches [`decisions.md`](decisions.md). Until they're made,
`decisions.md` wins wherever the two differ.

## Region
- [ ] Cover: "Deploy: Cloud Run, asia-northeast1" → prototype `asia-south1`; production `asia-northeast1`.
- [ ] §8 table: drop "in-country data residency" for the prototype; keep it as the production target.
- [ ] §11 requirements: "Deployed on Google Cloud: Cloud Run, asia-south1 (production: asia-northeast1)".
- [ ] §6.1: drop "speech-to-text in-region".

## Problem section (§1, §2) — from research R1, R2
- [ ] §1 Osaka: the ordinance caps **ATM transfers** at ¥100,000/day for people aged 70+ with no ATM
      transfer in 3 years (Art. 23), removable on request. It is not a cap on "anyone over 70". Osaka
      also imposes a binding duty on institutions to report suspected victims (Art. 21(3)).
- [ ] §1 figures: the NPA made ニセ警察詐欺 its own category only in 2026. Verify the PDF's "2025:
      ¥100.5bn" and "Jan–Jul 2026: ¥61.7bn". Latest NPA figure: **6,346 cases / ¥72.86bn to end-Aug 2026,
      amount +27.0% y/y** (NPA, 2026-10-02). H1 2026: 4,466 cases / ¥50.79bn; transfer 65.6%, cash
      handover 15.6%, crypto 13.9%; phone first contact 98.2%.
- [ ] §2: quote the NPA's own statement of the gap: at a staffed counter a basic confirmation allows
      payout, but scammers coach victims on what to say, so confirmation takes time (NPA,
      特殊詐欺の手口と対策, 2023-04-13).
- [ ] §2: banks are adding age/inactivity ATM limits (e.g. MUFG Trust, effective 2027-01-25; verify the
      issuer before citing).

## Value framing (§3, §5)
- [ ] The copilot and evidence card protect **every** customer. Advance wishes are an upgrade,
      offered during routine counter visits.
- [ ] Add what the wishes add over bank policy:
  - a pre-agreed cooling-off pause (at least 4 h, extended to the next business-day close, at most 24 h; the minimum avoids a 30-minute pause before closing). A delay, not a prohibition: she can override once the nominated contact has been reached, or after manager review with a second confirmation. Enforceability under the Consumer Contract Act Art. 10 needs legal review
  - the trusted contact
  - the disclosure rules
  - consent to the notice call
- [ ] "A human decides every hold" also covers account freezes (decided by an analyst).

## Tanaka case (§9)
- [ ] Step 3: a ¥3,000,000 **counter transfer** to a **same-bank** account, 4 days old, 7 payers this week. Remove "elderly".
- [ ] Step 5: the inference cites the customer's own words (transcript quote) plus the account facts.
- [ ] Step 6: the pause basis is her cooling-off wish. The teller also **notifies the police**. Officers get the evidence summary on request (APPI Art. 27(1)(i) via CCP Art. 197(2)).
- [ ] Step 7:
  - the notice reveals nothing
  - Yuki calls back on the published number with a case code
  - the agent opens by saying it is an automated assistant and that the call is recorded
  - the agent checks the number and the code before disclosing anything. Describe this as "lets the family verify the bank, blocks strangers", not as identity verification
  - Yuki's reply is recorded as information, not an instruction
- [ ] Step 8: the analyst approves freezing the mule account under the **Furikome Sagi Relief Act Art. 3(1)**. "One detection protects seven" → "surfaces six other payers for outreach".
- [ ] Note: in cash-handover cases, only the language layer applies.

## Components (§6)
- [ ] §6.1: the copilot model extracts indicators and picks approved questions. **Code** computes the risk level and the
      pause recommendation. No model confidence numbers on screen. Every word the teller reads comes from an approved bank.
- [ ] §6.2: the evidence card has **facts** (checked against tool fields), **quotes** (checked against
      the transcript) and **inferences** (shown as hypotheses, grounded in a verified fact or quote).
- [ ] §6.4: "Gemini understands what the family member asks; approved wording answers." Voice path:
      STT → intent → templates → rule check → TTS. Remove the "second check reviews each outgoing turn" model step.
- [ ] §6.5: onboarding is designed. Wishes are seeded in the prototype.
- [ ] §6.7: learning-loop changes to playbooks are structured fields only.

## Privacy and architecture (§7, §8)
- [ ] Replace "no third-party model API" with "reasoning over customer records is self-hostable with open weights".
- [ ] Add: "Speech-to-text is a managed regional API. A self-hosted Japanese ASR is a designed option."
- [ ] §8 rule: customer records → Gemma (or the copilot fallback). People-facing speech → Gemini, which receives only the filtered brief.
- [ ] Scoring is separate and always on. Cost: model calls scale with alerts, plus a fixed GPU floor.

## Evaluation (§10)
- [ ] Compare (a) today's counter check (NPA request to banks, Akita police five-step routine, Okayama case practice: ask the purpose, check documents, sometimes phone a relative, call police if suspicious); (b) statistics only; (c) Mimamori. The amount threshold is a stated parameter, the same for all arms.
      One teller-behaviour assumption applies to all three.
- [ ] Keep the age rule only for the ATM-restriction argument in §1.
- [ ] Held-out set: public fake-police cases published **after date T**. Playbooks come only from alerts before T.
      Report a case-by-case failure analysis, not rates.
- [ ] State the circularity of synthetic-population results. Use a separate judge prompt or model.
- [ ] Rename "Explainability 100%" → "facts and quotes verified against source; every inference grounded".
- [ ] "Reach per detection > 1" → report the measured number.

## Additions
- [ ] APPI: customer consent to transcribe the counter conversation. The family callback says it is automated and recorded.
- [ ] Limits: cash handover (language layer only), ATM / app path (designed), cross-bank fan-in (needs industry sharing).
- [ ] §12 risks: Gemma spike passed capability criteria 1–3 on a local 12B Q4 model; latency on Vertex untested. Legal review of the cooling-off pause and the freeze basis.

## Q&A prep
- **Why an AI call rather than the branch manager?**
  - It saves staff time at a busy counter.
  - It covers after-hours cases.
  - Disclosure is consistent and audited.
  - The manager can take over at any time.
- **What if she has no advance wishes?** The copilot, evidence card, pause under bank policy and police still apply.
- **Can she cancel the pause?** Yes, but not immediately: once her nominated contact has been reached, or after a manager review with a second confirmation. Without wishes, the wait is voluntary.
- **Can the model's confidence be trusted?** It isn't used. The model finds indicators and quotes; a fixed rule in code sets the risk level, and the teller decides.
- **Don't tellers already call family?** Sometimes, ad hoc. What's new is a contact the customer chose in advance, with consent and a disclosure policy, plus the evidence card.
