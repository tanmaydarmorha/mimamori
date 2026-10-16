# Demo scenarios: sequence diagrams

One diagram per scenario in the [scripted demo](../../demo/README.md). Each shows what the
judge sees (people and the console) and what happens behind it, with the services as built.
Rendered PNGs are in [`diagrams/`](diagrams/).

**Who decides what:**
- **Code** decides whether a case opens (Scoring) and how risky it is (`risk-v1`).
- **Models** only read language: the copilot reads the counter conversation, and Gemini classifies
  the family's questions.
- **People** make every decision.

| Scenario | Story | Diagram |
|---|---|---|
| `hero` | Tanaka, fake police, Japanese: alert, copilot, pause, family call, freeze, outreach | [hero](#hero) |
| `hero-en` | The same flow in English: a language pack, not a rebuild | [hero-en](#hero-en) |
| `genuine` | A real renovation: no pause | [genuine](#genuine) |
| `impostor` | A stranger calls back with a wrong code: nothing disclosed | [impostor](#impostor) |
| `small` | ¥300 to a suspicious account: no friction | [small](#small) |
| `split` | Two payments of ¥90,000: the running total opens a case | [split](#split) |

## hero

![hero](diagrams/demo-hero.png)

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer (Tanaka)
    actor T as Teller
    participant UI as Console
    participant CB as Core banking
    participant SC as Scoring (rules, no model)
    participant CS as Case service
    participant LLM as Copilot model
    participant CV as Conversation service
    participant G as Gemini
    actor D as Daughter (Yuki)
    actor A as Analyst

    Note over C,T: ¥3,000,000 counter transfer to カ）ミライケンセツ (same bank)
    T->>UI: New counter transfer
    UI->>CB: POST /transfers
    CB->>SC: score before it executes
    SC->>CB: baseline, payee account, payers, recent outflows
    SC->>SC: score-v1: account 4 days old, 7 payers, amount over the floor = alert
    SC->>CS: open case with the signals
    CB-->>UI: transfer pending, case opened
    CS->>CS: investigation agent re-checks every signal with read-only tools
    CS-->>UI: band Elevated, approved question
    T->>C: Say this (approved question)
    C->>T: リフォーム代なんです
    T->>UI: customer turn
    UI->>CS: POST turns
    CS->>LLM: transcript in a data block, schema-constrained
    LLM-->>CS: cover story, quote, next question id
    CS->>CS: quote verified word for word, risk-v1 stays Elevated
    CS-->>UI: cover-story quote on the card
    C->>T: 警察の人から電話があってね、誰にも言うなって
    T->>UI: customer turn
    UI->>CS: POST turns
    CS->>LLM: transcript
    LLM-->>CS: impersonation and secrecy, with quotes
    CS->>CS: quotes verified, risk-v1 rule H1 = High, pause recommended
    CS-->>UI: band High, hold line to read out
    T->>C: reads the approved hold line
    T->>UI: Place pause (basis advance wishes, rationale)
    UI->>CS: decision
    CS->>CB: place hold (at least 4 h, at most 24 h)
    CS-->>UI: band says paused
    T->>UI: Call the family
    UI->>CS: contact call
    CS->>CV: brief only (no records, no amount)
    CV-->>D: notice: call our published number, quote code
    D->>CV: calls back, menu 1, code
    CV->>CV: caller number = locked number AND code
    CV-->>D: automated assistant, this call is recorded
    loop each question
        D->>CV: 何があったんですか？ / いくらの振込ですか？
        CV->>G: classify the question
        G-->>CV: intent (what happened / how much)
        CV->>CV: approved template, rule check (no amounts)
        CV-->>D: reply (how much = polite refusal)
    end
    D->>CV: すぐ支店に行きます
    CV->>CS: contact view: concerned, coming to the branch
    CS-->>UI: Called: coming to the branch
    T->>UI: Freeze the payee account (reason)
    UI->>CS: freeze request
    A->>UI: Approve freeze (rationale)
    UI->>CS: freeze decision
    CS->>CB: freeze the mule account
    CS->>CB: payers of that account, last 7 days
    CS-->>UI: Outreach: 6 other customers paid it
```

## hero-en

![hero-en](diagrams/demo-hero-en.png)

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer
    actor T as Teller
    participant UI as Console
    participant CS as Case service
    participant LLM as Copilot model
    participant CV as Conversation service
    participant G as Gemini
    actor D as Daughter

    Note over C,UI: Same transfer and same alert as hero
    T->>UI: Conversation in: English (before the first turn)
    UI->>CS: set case language en
    CS->>CS: language locked after the first turn, change audited
    CS-->>UI: approved question from the English pack
    C->>T: It's for my home renovation.
    T->>UI: customer turn
    UI->>CS: POST turns
    CS->>LLM: shared rules + English examples
    LLM-->>CS: cover story, exact English quote
    C->>T: The police called me and told me not to tell anyone
    UI->>CS: POST turns
    CS->>LLM: transcript
    LLM-->>CS: impersonation and secrecy
    CS->>CS: same risk-v1 rule = High (the rule has no language)
    CS-->>UI: band High, English hold line
    T->>UI: Place pause, Call the family
    UI->>CS: decision, contact call
    CS->>CV: brief with language en
    CV-->>D: English notice and code
    D->>CV: calls back, menu 1, code
    CV-->>D: English opening (automated, recorded)
    D->>CV: How much is the transfer?
    CV->>G: classify (call language en)
    G-->>CV: intent how much
    CV->>CV: English template, English rule check (no number words)
    CV-->>D: I'm unable to share the amount over the phone
    Note over CS,CV: A new country adds a language pack, its playbooks and its legal basis
```

## genuine

![genuine](diagrams/demo-genuine.png)

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer
    actor T as Teller
    participant UI as Console
    participant CS as Case service
    participant LLM as Copilot model

    Note over C,UI: Same transfer, same flagged account: band Elevated
    T->>C: Say this (what is the money for?)
    C->>T: 業者さんとは先月から何度も会って、見積もりももらっています
    T->>UI: customer turn
    UI->>CS: POST turns
    CS->>LLM: transcript
    LLM-->>CS: cover story only, no impersonation, secrecy or handover signs
    CS->>CS: risk-v1: no core indicator, so no pause recommendation
    CS-->>UI: band stays Elevated, next approved question
    Note over T,UI: The teller carries on normally. A flagged account alone never pauses a customer
```

## impostor

![impostor](diagrams/demo-impostor.png)

```mermaid
sequenceDiagram
    autonumber
    actor S as Stranger
    participant CV as Conversation service
    participant CS as Case service
    participant UI as Console

    Note over S,CV: The notice went to the family. Someone else tries the published number
    S->>CV: calls back, menu 1, code 1111
    CV->>CV: caller number = locked number AND code: no match
    CV-->>S: could not confirm, ending the call
    Note over S,CV: Nothing disclosed. A wrong number and a wrong code look the same
    CV->>CS: verification failed
    CS-->>UI: family call: verification failed
```

## small

![small](diagrams/demo-small.png)

```mermaid
sequenceDiagram
    autonumber
    actor T as Teller
    participant UI as Console
    participant CB as Core banking
    participant SC as Scoring (rules, no model)

    T->>UI: New counter transfer, ¥300 to the same mule account
    UI->>CB: POST /transfers
    CB->>SC: score before it executes
    SC->>SC: young account and 7 payers, but ¥300 is under the ¥100,000 floor
    SC-->>CB: allow (signals still stored)
    CB->>CB: transfer executes, still counts toward the account's payers
    CB-->>UI: accepted
    UI-->>T: Nothing unusual. The transfer was accepted.
```

## split

![split](diagrams/demo-split.png)

```mermaid
sequenceDiagram
    autonumber
    actor T as Teller
    participant UI as Console
    participant CB as Core banking
    participant SC as Scoring (rules, no model)
    participant CS as Case service

    T->>UI: ¥90,000 to the mule account
    UI->>CB: POST /transfers
    CB->>SC: score
    SC->>SC: total to this payee in 7 days = ¥90,000, under the floor
    SC-->>CB: allow
    CB-->>UI: accepted
    T->>UI: ¥90,000 again
    UI->>CB: POST /transfers
    CB->>SC: score
    SC->>CB: this customer's outflows, last 7 days
    SC->>SC: total to this payee = ¥180,000, over the floor = alert
    SC->>CS: open case, signal: 2 payments, ¥180,000 in total
    CS->>CS: investigation recomputes the total from the bank and verifies the fact
    CS-->>UI: case opens, Why shows the running total
```
