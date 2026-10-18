# C4 Dynamic — The Tanaka case, end to end

Source: `Mimamori_Solution.pdf` §9, as amended by [`../decisions.md`](../decisions.md).
Containers: [`c4-containers.md`](c4-containers.md).

Tanaka Keiko, 78, a twelve-year customer with a baseline of ¥50,000 monthly withdrawals. Her
advance wishes, recorded at an earlier counter visit, name her daughter Yuki as the trusted
contact. They consent to a notice call and agree to a cooling-off pause (at least 4 h, extended to the next business-day close, at most 24 h). She can
override once the nominated contact has been reached, or after manager review with a second confirmation. All data is synthetic.

This is also the script for the ~3-minute video. Step numbers in the headings match PDF §9. The
flow is split into three diagrams so each stays readable. They show the prototype as built: the
copilot runs on Gemini 2.5 Flash (Gemma designed), the teller and the family member type their
turns (Speech-to-Text planned), and the phone is simulated in the browser. API paths are the proposed contracts
between containers.

**Colour key:** blue boxes are deterministic code, green boxes are model calls, yellow boxes are
human decisions.

---

## A · Before the visit (steps 1–2)

```mermaid
sequenceDiagram
    autonumber
    participant Alerts as Public scam alerts
    participant Intel as Intelligence job
    participant Gemini as Gemini
    participant IntelDB as intel-db
    actor Analyst as Fraud analyst
    participant Case as Case service
    participant Scoring as Scoring
    participant Core as Core banking (mock)

    Note over Alerts,IntelDB: Step 1 · Intelligence
    Intel->>Alerts: Fetch new alerts (scheduled)
    Alerts-->>Intel: Japanese prose (untrusted) + publication date
    rect rgb(232, 245, 233)
    Intel->>Gemini: Extract playbook: impersonation, script, cover story, payment method
    Gemini-->>Intel: Playbook JSON + question bank + counter wording
    end
    rect rgb(227, 242, 253)
    Intel->>Intel: Validate schema, de-duplicate, keep published_at
    end
    Intel->>IntelDB: Write playbook, status = pending
    rect rgb(255, 248, 225)
    Analyst->>Case: PATCH /playbooks/{id} {status: approved}
    end
    Case->>IntelDB: status = approved

    Note over Scoring,Core: Step 2 · Normal day
    Core->>Scoring: Transaction event (post-transaction): ¥400,000 withdrawal, April
    rect rgb(227, 242, 253)
    Scoring->>Scoring: Matches the annual school-fee pattern in her baseline
    end
    Note right of Scoring: No case, no model call. An age cap would have stopped it.
```

Rendered: [`c4-dynamic-tanaka-a.png`](diagrams/c4-dynamic-tanaka-a.png)

## B · At the counter (steps 3–6)

```mermaid
sequenceDiagram
    autonumber
    actor Keiko as Keiko (customer)
    actor Teller as Teller
    participant UI as Web UI (teller console)
    participant Core as Core banking (mock)
    participant Scoring as Scoring
    participant Case as Case service
    participant LLM as Gemini 2.5 Flash (Vertex AI)

    Note over Keiko,Case: Step 3 · Alert
    Keiko->>Teller: Transfer ¥3,000,000 to カ）… (same bank)
    Teller->>Core: Key in the counter transfer
    Core->>Scoring: Pre-transaction check
    rect rgb(227, 242, 253)
    Scoring->>Scoring: 60× baseline, new payee, payee account 4 days old, 7 payers this week
    end
    Scoring->>Case: POST /cases {customer, transfer, signals}
    Case-->>UI: Case opened, alert (SSE)

    Note over Case,LLM: Step 4 · Investigation
    rect rgb(232, 245, 233)
    loop Tool calls (read-only, step limit)
        Case->>LLM: Case context + tool results so far (untrusted fields in a data block)
        LLM-->>Case: Call a tool, e.g. explain_payee, counterpart_graph, search_playbooks
        Case->>Case: Execute tool (code)
    end
    LLM-->>Case: Hypotheses, facts, inferences, question IDs from the bank
    end
    rect rgb(227, 242, 253)
    Case->>Case: Check each fact against its tool field, drop ungrounded inferences
    end
    Case-->>UI: Evidence card + first question (SSE)

    Note over Keiko,LLM: Step 5 · At the counter (one loop per turn)
    Keiko->>Teller: 「リフォーム代です」(it's for the renovation contractor)
    Teller->>UI: Types the customer's words (Speech-to-Text planned)
    UI->>Case: POST /cases/{id}/turns → turn t2
    rect rgb(232, 245, 233)
    Case->>LLM: Copilot turn: transcript + card + approved playbooks
    LLM-->>Case: Cover story inconsistent with history (quote t2), question ID
    end
    rect rgb(227, 242, 253)
    Case->>Case: Quote rule: find quote in customer turns, fix turn ID or drop
    end
    Case-->>UI: Hypotheses updated, approved question from the bank (SSE)
    Teller->>Keiko: Asks the suggested question
    Keiko->>Teller: 「警察の人に、誰にも言うなと…」(the police told me not to tell anyone)
    UI->>Case: Typed turn t3
    rect rgb(232, 245, 233)
    Case->>LLM: Copilot turn
    LLM-->>Case: Indicators: impersonated_official, secrecy_instruction (quote t3)
    end
    rect rgb(227, 242, 253)
    Case->>Case: Risk rule in code: two core groups, so high
    end
    Case-->>UI: Pause recommended, approved hold line, claims that fired (SSE)

    Note over Teller,Core: Step 6 · Human decision
    rect rgb(255, 248, 225)
    Teller->>UI: Pause (cooling-off from her wishes), with rationale
    end
    UI->>Case: POST /cases/{id}/decision {action: pause, basis: advance_wishes, rationale}
    rect rgb(227, 242, 253)
    Case->>Case: Guardrails. A single-source pause is allowed with a logged warning
    end
    Case->>Core: Place hold (4 h min, to next business-day close, 24 h max · override after contact reached or manager review)
    rect rgb(255, 248, 225)
    Teller->>Teller: Notify police. Summary printed for officers on request, officer name logged
    end
```

Rendered: [`c4-dynamic-tanaka-b.png`](diagrams/c4-dynamic-tanaka-b.png)

## C · After the pause (steps 7–8)

```mermaid
sequenceDiagram
    autonumber
    actor Teller as Teller
    participant Case as Case service
    participant Conv as Conversation service
    participant Speech as Text-to-Speech
    participant Gemini as Gemini Flash
    actor Yuki as Yuki (simulated phone)
    actor Analyst as Fraud analyst
    participant Core as Core banking (mock)

    Note over Teller,Yuki: Step 7 · De-isolation
    rect rgb(227, 242, 253)
    Case->>Case: Contact check. Number changed recently? Linked to payee? Flagged in notes?
    end
    alt Wishes on file, contact not suspected
        rect rgb(227, 242, 253)
        Case->>Case: Build brief in code. No balance, no other customers' facts
        end
        Case->>Conv: POST /calls {case_id, brief, policy, case_code}
        Conv->>Speech: Notice text to speech
        Speech-->>Yuki: 「〇〇支店です。お母様の件で、公開番号に折り返しください。番号 NNNN」(branch X about your mother, call back on our published number, code NNNN)
        Yuki->>Conv: Calls published number, menu: returning a call about a case
        rect rgb(227, 242, 253)
        Conv->>Conv: Verify caller number = locked number on file AND case code
        end
        alt Verified
            Conv->>Speech: Opening text to speech
            Speech-->>Yuki: 「自動音声のアシスタントです。通話は録音されます」(automated assistant, call recorded)
            loop Each turn
                Yuki->>Conv: Typed turn on the simulated phone (Speech-to-Text planned)
                rect rgb(232, 245, 233)
                Conv->>Gemini: Classify intent
                Gemini-->>Conv: what_happened, is_she_safe, how_much, what_to_do, other
                end
                rect rgb(227, 242, 253)
                Conv->>Conv: Fill approved Japanese template from the brief
                end
                rect rgb(232, 245, 233)
                Conv->>Gemini: Connecting phrase only
                end
                rect rgb(227, 242, 253)
                Conv->>Conv: Rule check (三百万円, 300万, kana amounts, account numbers)
                end
                Conv->>Speech: Approved text to speech
                Speech-->>Yuki: Japanese speech
            end
            Note over Conv,Yuki: "How much does she have?" → how_much → template: the balance can't be shared
            Yuki->>Conv: 「すぐ支店に行きます」(I'm coming to the branch now)
            Conv->>Case: POST /cases/{id}/contact-outcome {contact_view: {concerned: true, coming_to_branch: true}}
            Case-->>Teller: Outcome on console (SSE)
        else Verification fails
            Conv->>Case: verification_failed (nothing disclosed)
            Case-->>Teller: Flag on console
        end
    else No wishes, or contact suspected
        rect rgb(255, 248, 225)
        Teller->>Teller: No call. Voluntary wait under bank policy, manager and police
        end
    end
    Note over Case: Any change to wishes or the contact number during an open case is frozen, and the previous contact is notified
    rect rgb(255, 248, 225)
    Teller->>Case: Keep pause or release, logged
    end

    Note over Case,Core: Step 8 · Reach
    Case->>Analyst: Freeze request for the mule account, with evidence card
    rect rgb(255, 248, 225)
    Analyst->>Case: Approve freeze, logged
    end
    Case->>Core: Freeze same-bank mule account
    Case->>Core: Who else paid this account?
    Core-->>Case: 6 other customers
    Case-->>Analyst: Outreach list, surfaces six others
```

Rendered: [`c4-dynamic-tanaka-c.png`](diagrams/c4-dynamic-tanaka-c.png)

Step 9 (proof) runs offline in the simulation job. See diagram 2c in
[`c4-containers.md`](c4-containers.md).

## Design points this flow pins down

1. **No model call on a normal day.** Step 2 is post-transaction monitoring in Scoring. Model
   cost grows with alerts, not transactions.
2. **The mule account is at the same bank.** Only then are its age and its payers visible, and
   only then can the bank freeze it. Cross-bank fan-in is designed, not built.
3. **The model never executes anything.** It requests read-only tools and the case service runs
   them. Payee names, memos and transcripts are untrusted data.
4. **Every claim is grounded.**
   - Facts are checked against tool fields.
   - Quotes must appear in a customer turn (exact, then after NFKC and whitespace removal). A wrong turn ID is corrected and an unfound quote is dropped.
   - Inferences ("coached cover story", "fake police") must cite a verified fact or quote, and are shown as hypotheses.
5. **The pause has a stated basis.**
   - With wishes: the pre-agreed cooling-off pause (at least 4 h, extended to the next business-day close, at most 24 h). A delay, not a prohibition: she can override once the nominated contact has been reached, or after manager review with a second confirmation.
   - Without wishes: a voluntary wait under bank policy, plus police.
   - The teller always decides, and is never blocked.
6. **The police are part of the response.** The real police are the answer to a fake-police script.
   The teller notifies them. Officers get the evidence summary on request, limited to what they ask,
   and the officer's name and title are logged (APPI Art. 27(1)(i) via CCP Art. 197(2)).
7. **The family call can't over-disclose by design.**
   - The notice reveals nothing.
   - Disclosure starts only after a callback that matches the number and the case code. This lets Yuki verify the bank and blocks strangers. It isn't proof of her identity, which rests on the number verified at registration and locked during the case.
   - The agent first says it is an automated assistant and that the call is recorded.
   - Gemini classifies intent, and code fills approved templates from a brief that holds no balance and no other customers' data.
8. **Yuki's reply is information** (`contact_view`), never an instruction.
9. **A human decides the freeze.** The same rule as holds: the analyst approves, and the decision is logged.
10. **Code, not the model, decides risk.** The model (Gemini 2.5 Flash as built) extracts indicators and quotes, checks the cover
    story and picks a question ID. Code accumulates verified indicators, computes the risk level
    and the pause recommendation (`risk-v1`), and fills every word the teller says from the
    approved bank. The model's own likelihood numbers are not used (Gemma spike, finding 1).
