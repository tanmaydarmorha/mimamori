# Scripted demo

A one-command demo that drives the **real app** in visible Chrome windows at a readable pace, with an
English caption bar that tells judges what is happening. It can record a video of each window. The
app code is not touched: the script only clicks and types, as a person would.

## Setup (once)

```bash
cd demo && npm ci
```

Needs Node 20+ and Google Chrome installed (the script uses it; no browser is downloaded). To
**record**, Playwright also needs its small video encoder, once: `npx playwright install ffmpeg` (1.4 MB). The stack
must be running (`scripts/dev.sh up`, Gemini by default), or pass `--fresh`.

## Commands

```bash
scripts/demo.sh                          # list the scenarios
scripts/demo.sh hero                     # one scenario
scripts/demo.sh all                      # reset the local stack, then run every scenario in order
scripts/demo.sh hero --record            # also save a video of each window
scripts/demo.sh hero --speed slow        # slow | normal (default) | fast
scripts/demo.sh hero --url https://…     # point it at another deployment (not with --fresh)
```

- `--fresh` runs `scripts/dev.sh down --wipe && scripts/dev.sh up` first (local stack only).
- `--speed` scales every pause: normal types at 35 ms per character, pauses 600 ms before a click and
  holds 2.5 s after each step; `slow` doubles that, `fast` halves it.
- Two windows open side by side: the **teller console** on the left (1280×800) and, for scenarios that
  use it, **the daughter's phone** (`/phone`) on the right (480×800). A screen about 1800 px wide shows both.
- Recordings go to `demo/out/<scenario>-<window>-<timestamp>.webm` (git-ignored). A failed step saves a
  screenshot and the page HTML there too, and the command exits non-zero naming the step.

## Scenarios

| id | Story | Needs `--fresh`? |
|---|---|---|
| `split` | Splitting a sum doesn't hide it: a second ¥90,000 payment opens a case on the running total. | Yes: the first payment must be accepted, so no earlier payments to that account in the last 7 days. If it is not, the scenario is **skipped** with a message. |
| `small` | No friction for small payments: ¥300 to a suspicious account goes straight through. | No |
| `genuine` | No false alarm: a real renovation with a consistent story is not paused. | No |
| `impostor` | A stranger can't get information by calling back with a wrong code. | No |
| `hero-en` | The headline flow in English (a language pack, not a rebuild), up to the end of the family call. | No |
| `hero` | Tanaka, fake police, Japanese: alert, copilot, pause, family call, freeze, outreach. About 3 min. | No, but it freezes the payee account, so every scenario run after it needs `--fresh` (see below) |

`all` runs them in the order above. On a fresh stack every one runs to the end (about 12 min).

**`all` resets the local stack first** (as if `--fresh` were given; not with `--url`). `hero` ends by
freezing the payee account, and the bank then refuses every later transfer to it, so a single scenario
run after `hero` without `--fresh` is skipped with the message "payee account was frozen by an earlier
`hero` run". Running totals also carry over for 7 days
(they are the point of `split`), so `split` skips itself if earlier payments are still in the window.
Each scenario creates its own transfer and reads the case code from the notice on the phone.
Don't run scenarios against a stack with unanswered notices from aborted runs: the phone service ties
a callback to the oldest open call for that number.

## Editing the captions

Each scenario is a data file, `demo/scenarios/<id>.json`: a list of **steps**, and each step has a
`caption` (what the judge reads) and `do` (what the script does). Change the words in `caption`
without touching code.

```json
{
  "caption": "The customer says it's for a renovation. The copilot quotes her words.",
  "do": [
    { "a": "turn", "who": "customer", "text": "リフォーム代なんです" },
    { "a": "wait", "target": "[data-testid=why] .quote", "text": "リフォーム", "thinking": true }
  ],
  "hold": 2500
}
```

- `caption` is a string (shown in the teller window) or `{ "phone": "…" }` for the phone window.
- `hold` is the time to keep the step on screen after it ends, in ms at normal speed (default 2500).
- `thinking: true` on a `wait` shows "The copilot is reading the conversation…" while it waits
  (90 s limit).
- Actions: `goto`, `click`, `type`, `select`, `scroll`, `hold`, `wait`, `expectNot`, `openTransfer`,
  `transfer`, `caseFromUrl`, `turn`, `phoneNotice`, `phoneDial`, `phoneSay`. They are defined in
  `demo/lib/driver.mjs`. A target is a CSS selector or `button:Name`, `link:Name`, `tab:Name`.
- Waits are on the app's `data-testid`s and attributes, never on fixed sleeps.

## Recording

`scripts/demo.sh hero --record` saves `hero-teller-….webm` and `hero-phone-….webm`. The videos have no
sound and are not edited. Use `--speed slow` for a calmer recording.
