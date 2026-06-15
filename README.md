# the Jaato Arch — visualization source pack

Per-component, **standalone** architecture documentation for the Jaato framework. Each file in
`components/` is self-contained and can be fed independently to an image-generation agent: every doc
ends with a **"Diagram brief (for illustration)"** section describing the exact visual to produce for
a PPT/HTML slide. Combine each doc's prose + its generated image per slide.

## Layout

```
the_Jaato_Arch_visualization/
├── README.md            ← this index
├── TEMPLATE.md          ← the shared section structure + style spec every doc follows
├── components/          ← the 17 standalone component docs (00 overview + 01–16)
├── jaato/               ← public source repo (github: Jaato-framework-and-examples/jaato)
├── jaato-premium/       ← premium source (reactor engine; cascades are reactor-driven) [synced]
└── kb-enablement-2.0/   ← reference deployment: the production cascade (.jaato/ + driver) used by 09/10 [synced, read-only]
```

## Components (bottom → top)

| Doc | Component | What it covers |
|-----|-----------|----------------|
| [00-overview](components/00-overview.md) | **Stack overview** | The whole bottom→top map + a title-slide diagram brief |
| [01-daemon](components/01-daemon.md) | **Daemon** | Long-lived server process, IPC/WS transports, session manager |
| [02-pool-runner](components/02-pool-runner.md) | **Pool runner** | Pre-warm runner pool — template fork, READY handshake, telemetry |
| [03-runners](components/03-runners.md) | **Runners** | Per-session isolated subprocess, RPC surface, AppArmor confinement |
| [04-runtime-session-client](components/04-runtime-session-client.md) | **Runtime/Session/Client** | Shared runtime + per-agent session + the function-call loop |
| [05-plugins](components/05-plugins.md) | **Plugins** | Four plugin kinds + enrichment, registry, traits, auto-wiring |
| [06-model-providers](components/06-model-providers.md) | **Model providers** | Provider-agnostic protocol over every LLM backend |
| [07-profiles](components/07-profiles.md) | **Profiles** | Declarative agent config (model/provider/plugins/GC/schemas) |
| [08-personas](components/08-personas.md) | **Personas** | Agent identity as Markdown; persona vs profile |
| [09-cascades](components/09-cascades.md) | **Cascades** | Multi-stage agent workflows (premium `flow_runner` / Flows) |
| [10-cascade-stages](components/10-cascade-stages.md) | **Cascade stages** | Anatomy of one stage; typed in/out boundaries |
| [11-reactors](components/11-reactors.md) | **Reactors** | Event→condition→action rules in the daemon |
| [12-prefetch-scripts](components/12-prefetch-scripts.md) | **Pre-fetch scripts** | Persona context-fetching at bootstrap (input boundary) |
| [13-completion-schemas](components/13-completion-schemas.md) | **Completion schemas** | Typed output contract via `signal_completion` |
| [14-completion-processors](components/14-completion-processors.md) | **Completion processors** | Post-processing of the validated completion payload |
| [15-workspace](components/15-workspace.md) | **Workspace** *(cross-cutting)* | Per-session root scoping filesystem + AppArmor + warm-runner reuse |
| [16-lifecycle-and-events](components/16-lifecycle-and-events.md) | **Lifecycle & events** *(cross-cutting)* | The ~110 SDK events and their temporal ordering across a session's life |

## Notes on accuracy

Each doc is grounded in the actual source (real class/function names, `.jaato/` paths, `path:line`
anchors) and flags anything that is design-stage-only or not yet implemented. Two terminology points to
keep in mind when reading: a **persona** is agent Markdown (not a class; the spawn/completion schemas
live on the **profile**), and a **cascade** is an *asynchronous, reactor-driven* chain of headless agent
sessions — each stage's `agent.completed` event triggers a reactor that spawns the next stage.

> **Not documented here, on purpose:** the premium `flow_runner` / `kind: Flow` / `ScriptedFlowRunner`
> engine ("flows") is a **separate mechanism from cascades** and is slated to be dropped — do not
> conflate the two. These docs cover cascades (the reactor-driven model), not flows.
