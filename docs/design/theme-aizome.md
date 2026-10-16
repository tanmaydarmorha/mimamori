# Theme: Aizome (藍染)

The visual theme for every Mimamori screen: the teller console, the analyst console, the simulated
phone and any landing page. Chosen 2026-10-16 with the theme-factory skill (custom theme).

**Idea.** *Mimamori* means "watching over". The palette is indigo-dyed ink (藍, aizome) on washi
paper: quiet, institutional, Japanese. It suits a bank counter where a teller must stay calm in
front of a frightened customer. Colour is spent on one thing only: **how worried should I be**.
Vermilion (朱, shu) appears only when the risk is high.

## Colour

| Role | Name | Hex | Use |
|---|---|---|---|
| Ground | washi | `#F6F4EF` | Page background |
| Surface | paper | `#ECE8DF` | Panels, set apart by tone (no borders, no shadows) |
| Ink | aizome | `#1B2A41` | All text and headings (13.1:1 on washi) |
| Ink, secondary | sumi-grey | `#5A6577` | Secondary notes only, never running text (5.4:1) |
| Accent | asagi | `#1F7A7A` | Primary buttons (white text 5.1:1), links (4.6:1), focus ring |
| Accent tint | asagi-tint | `#DCEDEB` | Selected row, active tab |
| Elevated | yamabuki-deep | `#8A5A0B` | "Elevated" text (5.4:1) |
| Elevated tint | yamabuki-tint | `#F4E6C8` | Elevated risk band (ink on it 11.7:1) |
| High | shu | `#A93226` | "High" text (5.1:1 on its tint); white on it 6.6:1 for the band |
| High tint | shu-tint | `#F7DCD7` | High-risk band background |

Rules:
- **No other colours.** Low risk uses ink on paper: calm is the absence of colour.
- **Shu only for High risk** and for destructive confirmations. Never for decoration.
- No gradients, no shadows at rest, no 1px outlined boxes, no hairline dividers. Surfaces differ by
  tone (washi → paper); a section can change its whole field colour (e.g. the risk band).
- Risk is never colour alone: always the word too ("High: pause recommended").

## Type

One family: **BIZ UDPGothic** (Google Fonts, weights 400 and 700). It's a Japanese *universal design*
typeface, made by Morisawa for readability in public and financial documents, and it covers Latin.
Fallback stack: `"BIZ UDPGothic", "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif`.

| Step | Size / line-height | Weight | Use |
|---|---|---|---|
| Display | 32px / 1.1, tracking -0.02em | 700 | The risk state; the customer's name on the case |
| Title | 20px / 1.3 | 700 | Panel headings, the suggested question (Japanese) |
| Text | 15px / 1.6 | 400 | Running text, transcript, facts |
| Small | 13px / 1.5 | 400 | Secondary notes, English glosses, metadata |

Four sizes, no more. (Reduced from 40/24/17/14 on 2026-10-16 after review: the first sizes read too large on the console.) Numbers use `font-variant-numeric: tabular-nums`. No monospace (internal codes
such as `f3` or `E:risky_counterpart` go behind a "details" disclosure in Text size). No uppercase
letter-spaced labels: sentence case.

## Shape and motion

- Corners: **4px** on panels and buttons, decided once. Inputs share it.
- Spacing scale: 4, 8, 12, 16, 24, 32, 48. Panels pad 24; the gap between panels is 16.
- Motion only where it carries meaning: the risk band changes colour and height when the level
  changes (200ms ease-out), new evidence rises 12px with opacity (160ms), a newly suggested
  question cross-fades. All of it is off under `prefers-reduced-motion`.

## Tokens (paste into `services/web-ui/src/styles.css` `:root`)

```css
:root {
  --washi: #F6F4EF;  --paper: #ECE8DF;
  --ink: #1B2A41;    --ink-2: #5A6577;
  --asagi: #1F7A7A;  --asagi-tint: #DCEDEB;
  --yamabuki: #8A5A0B; --yamabuki-tint: #F4E6C8;
  --shu: #A93226;    --shu-tint: #F7DCD7;
  --font: "BIZ UDPGothic", "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif;
  --fs-display: 32px; --fs-title: 20px; --fs-text: 15px; --fs-small: 13px;
  --radius: 4px;
  --s1: 4px; --s2: 8px; --s3: 12px; --s4: 16px; --s5: 24px; --s6: 32px; --s7: 48px;
}
```
