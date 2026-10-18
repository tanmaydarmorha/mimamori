# Mimamori docs

What was built is described in the [repository README](../README.md). These docs hold the design
behind it: the decisions, the research, and the architecture.

| Path | Contents |
|---|---|
| [`decisions.md`](decisions.md) | Design decisions and how each review item was resolved |
| [`research.md`](research.md) | Research on the problem (NPA figures, the counter process, the law), with sources |
| [`architecture/`](architecture/) | C4 model, as built: [system context](architecture/c4-context.md), [containers](architecture/c4-containers.md) (counter path, family call, offline jobs), [the Tanaka case step by step](architecture/c4-dynamic-tanaka.md), and the [API contracts](architecture/api-contracts.md) |
| [`demo/`](demo/) | The [scripted demo scenarios](demo/demo-scenarios.md) as sequence diagrams |
| [`design/`](design/) | The [Aizome theme](design/theme-aizome.md) and the [console design](design/console-design.md) |
| [`screens/`](screens/) | Screenshots of the live prototype used in the README |
| [`plans/`](plans/) | The [build kickoff](plans/build-kickoff.md) for the parallel build sessions (historical) |
| [`../schemas/`](../schemas/) | Data contracts (JSON Schema), Tanaka examples, the copilot rules, `validate.py` |
| [`../spikes/gemma-copilot/`](../spikes/gemma-copilot/) | Step-0 Gemma spike: test conversations, runner, [results](../spikes/gemma-copilot/RESULTS.md) |

Re-render a diagram:
- **C4 context and container views** are draw.io files in `architecture/diagrams/src/`. Edit them in
  draw.io, then export with the desktop app:
  `/Applications/draw.io.app/Contents/MacOS/draw.io -x -f png -s 2 -b 20 -o architecture/diagrams/<name>.png architecture/diagrams/src/<name>.drawio`.
- **Sequence diagrams** (Tanaka case, demo scenarios) are mermaid blocks in the Markdown: extract one to a
  `.mmd` file, then `npx -y @mermaid-js/mermaid-cli@11.4.2 -i <file>.mmd -o architecture/diagrams/<name>.png -w 2000 -b white`.
