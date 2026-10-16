# Mimamori docs

Spec: `Mimamori_Solution.pdf` (kept outside this repo, in `ctrl+risk/`; `PROPOSAL.md` is deprecated), amended by
[`decisions.md`](decisions.md) until the deck is regenerated. Working notes (reviews, deck edits, work items) are kept outside this repo, in `ctrl+risk/mimamori-notes/`.

| Path | Contents |
|---|---|
| [`decisions.md`](decisions.md) | Design decisions, every review item → resolution, build order, open research |
| [`research.md`](research.md) | Research brief for the open items (R1–R5), with findings |
| [`architecture/`](architecture/) | C4 model: [context (L1)](architecture/c4-context.md), [containers (L2: counter, family call, offline)](architecture/c4-containers.md), [Tanaka case flow](architecture/c4-dynamic-tanaka.md), [API contracts](architecture/api-contracts.md). Rendered PNGs in `architecture/diagrams/`. |
| [`plans/`](plans/) | [Build kickoff for parallel sub-agents](plans/build-kickoff.md) |
| [`demo/`](demo/) | [Demo scenarios](demo/demo-scenarios.md) as sequence diagrams |
| [`design/`](design/) | [Aizome theme](design/theme-aizome.md), [console design](design/console-design.md), screens |
| [`../schemas/`](../schemas/) | Data contracts (JSON Schema), Tanaka examples, the copilot rules, `validate.py` |
| [`../spikes/gemma-copilot/`](../spikes/gemma-copilot/) | Step-0 Gemma spike: test conversations, runner, [results](../spikes/gemma-copilot/RESULTS.md) |

Re-render a diagram: extract its mermaid block to a `.mmd` file, then
`npx -y @mermaid-js/mermaid-cli@11.4.2 -i <file>.mmd -o architecture/diagrams/<name>.png -w 2000 -b white`.
