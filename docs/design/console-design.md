# Console design: teller, analyst, phone

Uses the approved theme in [`theme-aizome.md`](theme-aizome.md); colours, type sizes and spacing come
only from its tokens. Written 2026-10-16 with the frontend-design skill.

## The brief, in one line

**Subject:** a bank teller at a Japanese counter, with an elderly customer in front of them who may
be on the phone with a fake policeman. **Audience:** the teller (and, in the demo, judges watching
over their shoulder). **Primary job:** tell the teller, at a glance from a step back, *how worried
to be* and *what to say next*, and let them act.

Everything else on the screen is secondary to those two things.

## Plan

**Colour** (from the theme): washi `#F6F4EF` ground, paper `#ECE8DF` surface, aizome `#1B2A41`
ink, asagi `#1F7A7A` action, yamabuki and shu only for the risk state.

**Type:** BIZ UDPGothic only. Display 32 is used for exactly one thing per screen; Title 20 for the
question the teller reads aloud and for section headings; Text 15; Small 13.

**Layout concept: the band, then talk on the left and act on the right.**

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ 見守り Mimamori    Counter   Analyst   Phone                    日本語 | EN   teller-01 │  bar: washi, no rule
├────────────────┬─────────────────────────────────────────────────────────────────────┤
│ Today          │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
│                │▓ High: pause recommended                          (Display 32)     ▓│  THE BAND
│ ▌田中 圭子 High │▓ 田中 圭子   ¥3,000,000 to カ）ミライケンセツ                        ▓│  full width of the case,
│  ¥3,000,000    │▓             same-bank account, opened 4 days ago, 7 payers         ▓│  field colour = risk
│                │▓ Say to the customer: 「本日は念のため…」 (approved hold line)      ▓│  (High only)
│  佐藤 一郎  Low │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
│  ¥80,000       │  TALK (left, ~62%)                     │  ACT (right, ~38%, sticky)  │
│                │ ┌────────────────────────────────────┐ │ ┌─────────────────────────┐ │
│ New counter    │ │ Ask next                     paper │ │ │ Your decision     paper │ │
│ transfer       │ │ 差し支えなければ、今回のお金の…  (24) │ │ │ ( Pause ) ( Release )   │ │
│ (opens a form) │ │ If you don't mind, may I ask… (14) │ │ │ Basis  [select]         │ │
│                │ │ [Say this]                         │ │ │ Why    [textarea]       │ │
│                │ └────────────────────────────────────┘ │ │ [Place pause]           │ │
│                │  Conversation                    washi │ └─────────────────────────┘ │
│                │  Customer  リフォーム代なんです          │  Call the family          │
│                │            EN: It's for my renovation. │  Police                   │
│                │  Teller    差し支えなければ…            │  Freeze the payee account │
│                │  [sample lines]                         │  (each a disclosure row,  │
│                │  [Customer|Teller] [ type…    ] [Send]  │   opens in place)         │
│                │                                         │                           │
│                │  Why                             washi  │                           │
│                │  Facts                  Quotes          │                           │
│                │  60× usual withdrawal   「誰にも言うな…」 │                           │
│                │  New payee              EN: …           │                           │
│                │  ▸ Details (rule codes, sources)        │                           │
└────────────────┴─────────────────────────────────────────┴───────────────────────────┘
```

- **Left-aligned everywhere.** No centred text except the phone's keypad digits.
- **Reading order is the teller's loop:** how worried (band) → what to say (Ask next) → what was
  said (Conversation) → why (evidence) → decide (right column).
- **Only two things get the paper surface:** the *Ask next* cue card and the *Your decision* panel.
  Everything else sits on washi, separated by space (48px between groups) and by its heading. This
  avoids the "everything in identical boxes" look.
- **Phone width (≤ 760px):** one column in the order band → Ask next → Conversation → decision →
  Why. The case list becomes a select at the top.

**Principles**
1. **One loud thing:** the band. Its field colour *is* the risk level (paper for Low, yamabuki-tint
   for Elevated, shu-tint for High), its first line is the state in words at Display size. Nothing
   else on the screen uses Display or a risk colour.
2. **Say it, don't label it.** Plain headings that say what the area is for ("Ask next", "Why",
   "Your decision"). No "(approved bank wording)", "(verified)" or "(the teller decides)"
   parentheticals; that information moves into one Small line where it matters.
3. **Customers, not IDs.** The customer's name leads; the case ID, rule version and claim codes go
   into a "Details" disclosure.
4. **Japanese first, English as a quiet second line** (Small, ink-2), as the glosses already do.
5. **Motion answers a change.** One orchestrated moment: when the risk level changes, the band's
   field colour cross-fades and the state line slides up and swaps (240ms). New transcript turns and
   new evidence rise 8px with opacity (160ms). Nothing moves on page load. Everything is static
   under `prefers-reduced-motion`.

## Review against the generic defaults (what I changed)

| Default it drifted towards | Change |
|---|---|
| **SaaS card kit:** every area in an identical rounded panel | Only two surfaces (Ask next, Your decision); the rest is open on washi. Corners stay 4px, but there are far fewer boxes. |
| **Middle-dot meta strings** (`田中 圭子 · cust-… · ¥3,000,000 · 2026/10/13`) everywhere | Structured lines in the band: name, then amount and payee, then one Small line of payee facts. IDs go into Details. |
| **Monospace chips** for claim IDs (`f1`, `E:risky_counterpart`) | Removed from the default view; listed in plain text inside Details. |
| **Warm cream ground** (washi is close to the generic `#F4F1EA`) | Kept, because the client approved it. The ground is never the identity; the band is. No serif display and no clay accent, which are the other two halves of that default. |
| **A banner per alert** (pink "New alert" box in the sidebar) | The case list is one list; a new case enters at the top with its risk word in the right colour, and the rail shows a 4px bar on its left edge in that colour (the only colour in the rail). |

## Teller console details

**Bar** (washi, 56px, no bottom rule): wordmark 見守り Mimamori (Title, 700), links Counter /
Analyst / Phone (Text, asagi when active with an asagi-tint background), on the right the
日本語 | EN segmented control and the user. The role switch (local only) moves into a small "Demo"
menu next to the user.

**Case rail** (240px, paper): heading "Today". Each case is a row: name (Text 700), amount (Small,
tabular figures), risk word (Small, in its colour; Low in ink-2). The selected row is
asagi-tint. "New counter transfer" is a text button at the bottom of the list that opens the
existing form in place.

**The band:** padding 32px 32px 24px.
- Line 1: the state at Display: "Low", "Elevated", "High: pause recommended" (ja: keep the existing `RISK_LABEL`
  values, plus 「一時停止を推奨」 after High).
- Line 2 (Title): customer name, then the amount in Title, then "to" and the payee.
- Line 3 (Small): payee facts in words (same-bank, account age, payers this week).
- When a pause is recommended: the approved hold line, introduced by "Say to the customer:" in
  Small, and the hold line itself in Text 700, Japanese first.
- Status of the case (Open, Paused, Released) sits at the top right of the band as a word, not a pill.
- Before the first turn, "Conversation in: 日本語 | English" sits at the top right of the band as
  a segmented control, and becomes the plain word afterwards.

**Ask next** (paper, padding 24): heading "Ask next" (Small 700, ink-2). The question at Title 700
in the case language; the other language under it at Small. Button "Say this" (asagi, filled).

**Conversation**: heading (Title). Turns as rows, not bubbles: speaker in Small 700 on the left
(80px column), the words in Text, the EN gloss under them in Small ink-2. The teller's rows have a
washi→paper tone step so the two voices separate without lines. Sample lines as small text
buttons (asagi text, no outline) in one wrapping row under the heading "Sample lines". The input
row: segmented Customer | Teller, the field, the Send button.

**Why**: heading (Title). Two columns: Facts (Text, each a plain sentence) and Quotes (each the
Japanese quote in Text with 「」, its gloss in Small). Dropped or dismissed claims and the codes go
under "Details" (a native `<details>`).

**Right column, "Your decision"** (paper, sticky top 16px): the Pause | Release segmented control,
Basis, Why, and the primary button whose label says what happens: "Place pause" / "Release the
transfer". When a pause is recommended, the Pause segment is preselected and the button is shu.
When the case is on hold: "On hold until 15:00" at Title, the override paths as two plain lines.

Under it, three disclosure rows on washi, each opening in place: "Call the family", "Police",
"Freeze the payee account". Each row's summary line shows its current state in Small ("Not
called", "Called: coming to the branch in 20 minutes", "Requested, waiting for the analyst").

## Analyst console

Same bar. Left rail (paper): the three queues as rows with a count: Freeze requests (2), Playbooks
(1), Outreach (6). The main area shows the selected queue:
- **Freeze request:** a band like the teller's (the risk state of the source case) with the payee
  account and the six other payers named; under it the teller's reason, the evidence (the Why
  layout), and the decision panel on the right ("Approve freeze" in shu, "Reject").
- **Outreach:** a real table (rows may have lines: tables are allowed them): payer, amount,
  date, status, action.
- **Playbooks:** title, sources (publisher and date), script phrases, question bank, and the decision.

## Simulated phone

A phone, because it simulates one: a 390×780 device in aizome ink with 40px corners (the one
exception to the 4px rule, because it is an object, not a panel), centred on washi, with the
explanatory text in a column to its left on desktop ("This stands in for the daughter's phone…").
Inside:
- **Messages screen:** the notice as an incoming message bubble (paper), with the case code at Title
  and a "Call the bank" button that dials the published number.
- **Call screen:** the bank's menu as large round keys (3×4), the code entry, then the call: the
  agent's lines as left bubbles, the daughter's as right bubbles (asagi-tint), EN glosses under
  each, sample lines above the input, "Read aloud" as a small toggle, and a red-free "End call"
  button (ink fill; shu is reserved for risk).
- Language toggle at the top of the phone's status bar.

## Copy changes (en / ja)

| Now | New |
|---|---|
| Next question (approved bank wording) / 次に尋ねる質問(承認済み) | Ask next / 次に伺うこと |
| Facts (verified) / 事実(照合済み) | Why: Facts / 根拠: 事実 |
| Customer quotes / お客様の発言(原文) | Why: Quotes / 根拠: お客様の言葉 |
| Decision (the teller decides) / 判断(窓口担当者が決定します) | Your decision / あなたの判断 |
| A pause is recommended. The decision is yours. | (removed; the band says it) |
| Risk: Elevated (risk-v1) / Conditions that fired | Elevated (band); rule and conditions under Details |
| Approved hold line for the customer | Say to the customer / お客様へのご案内 |
| Freeze request for the payee account (analyst decides) | Freeze the payee account / 送金先口座の凍結 |
| Police summary (on the officers' request only) | Police / 警察 (the "on request only" rule moves into the opened panel as one Small line) |
| Select a case on the left. | No case open. New alerts appear in the list on the left. / ケースは開かれていません。新しいアラートは左の一覧に表示されます。 |
| Key in a counter transfer (demo) | New counter transfer / 窓口の振込を入力 |
