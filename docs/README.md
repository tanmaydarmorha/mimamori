# Mimamori docs

Spec: `../Mimamori_Solution.pdf` (`../PROPOSAL.md` is deprecated), amended by
[`decisions.md`](decisions.md) until the deck is regenerated.

| Path | Contents |
|---|---|
| [`decisions.md`](decisions.md) | Design decisions, every review item → resolution, build order, open research |
| [`deck-changes.md`](deck-changes.md) | Checklist of edits for the PDF |
| [`research.md`](research.md) | Research brief for the open items (R1–R5), with findings |
| [`architecture/`](architecture/) | C4 model: [context (L1)](architecture/c4-context.md), [containers (L2: counter, family call, offline)](architecture/c4-containers.md), [Tanaka case flow](architecture/c4-dynamic-tanaka.md). Rendered PNGs in `architecture/diagrams/`. |
| [`reviews/`](reviews/) | [Devil's-advocate review](reviews/devils-advocate-review.md) (DA #1–20), [plan critique](reviews/review-response-plan-critique.md) (CR #1–23) |
| [`plans/`](plans/) | [Review-response plan](plans/review-response-plan.md) |
| [`../schemas/`](../schemas/) | Data contracts (JSON Schema), Tanaka examples, the copilot rules, `validate.py` |
| [`../spikes/gemma-copilot/`](../spikes/gemma-copilot/) | Step-0 Gemma spike: test conversations, runner, [results](../spikes/gemma-copilot/RESULTS.md) |

Re-render a diagram: extract its mermaid block to a `.mmd` file, then
`npx -y @mermaid-js/mermaid-cli@11.4.2 -i <file>.mmd -o architecture/diagrams/<name>.png -w 2000 -b white`.
