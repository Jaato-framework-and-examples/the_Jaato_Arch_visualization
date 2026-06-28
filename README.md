# the Jaato Arch — visualization source pack

Per-component, **standalone** architecture documentation for the Jaato framework. Each file in
`components/` is self-contained and can be fed independently to an image-generation agent: every doc
ends with a **"Diagram brief (for illustration)"** section describing the exact visual to produce for
a PPT/HTML slide. Combine each doc's prose + its generated image per slide.

## Layout

This repo contains only the documentation:

```
the_Jaato_Arch_visualization/        # this repo
├── README.md            ← this index
├── TEMPLATE.md          ← the shared section structure + style spec every doc follows
├── components/          ← the 24 standalone component docs (00 overview + 01–23)
└── sdk-comparisons/     ← usage-oriented, example-based SDK comparisons vs other frameworks
```

## SDK comparisons

A separate genre from the architecture docs above: **side-by-side, example-driven** SDK-usage
comparisons of jaato-sdk against other agent frameworks (10 examples each, simplest → most complex).
A growing series — this first iteration covers LangChain; the rest are planned:

| Framework | Status | Doc |
|-----------|--------|-----|
| **LangChain / LangGraph** | ✅ available | [langchain](sdk-comparisons/langchain.md) — hello-world → streaming → typed output → tools → agent loop → HITL → multi-agent → cascade → production/recovery |
| **Mastra** | ✅ available | [mastra](sdk-comparisons/mastra.md) — TS-both: hello-world → streaming → memory → typed output → tools → agent loop → HITL → multi-agent → workflow/cascade → production |
| **Pydantic AI** | ✅ available | [pydantic-ai](sdk-comparisons/pydantic-ai.md) — Python-both: hello-world → streaming → memory → typed output → tools → agent loop → deferred-tools HITL → delegation → graph/cascade → production |
| **Agno** | ✅ available | [agno](sdk-comparisons/agno.md) — Python-both: hello-world → streaming → memory → typed output → tools → agent loop → HITL → Teams → workflow/cascade → production |
| **Strands** | ✅ available | [strands](sdk-comparisons/strands.md) — Python-both: hello-world → streaming → memory → typed output → tools → agent loop → HITL → multi-agent → graph/cascade → production |
| **OpenAI Agents SDK** | planned | — |
| **Claude Agent SDK** | planned | — |

The docs are grounded in three source trees that are cloned **locally** for reference and are
**git-ignored — not part of this repo** (two are private):

```
jaato/             public source repo (github: Jaato-framework-and-examples/jaato)
jaato-premium/     PRIVATE — premium source (reactor engine; cascades are reactor-driven)
kb-enablement-2.0/ PRIVATE — reference deployment: the production cascade (.jaato/ + driver) used by 09/10
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
| [09-cascades](components/09-cascades.md) | **Cascades** | Async, reactor-driven multi-stage agent workflows (headless sessions chained on completion events) |
| [10-cascade-stages](components/10-cascade-stages.md) | **Cascade stages** | Anatomy of one stage; typed in/out boundaries |
| [11-reactors](components/11-reactors.md) | **Reactors** | Event→condition→action rules in the daemon |
| [12-prefetch-scripts](components/12-prefetch-scripts.md) | **Pre-fetch scripts** | Persona context-fetching at bootstrap (input boundary) |
| [13-completion-schemas](components/13-completion-schemas.md) | **Completion schemas** | Typed output contract via `signal_completion` |
| [14-completion-processors](components/14-completion-processors.md) | **Completion processors** | Post-processing of the validated completion payload |
| [15-workspace](components/15-workspace.md) | **Workspace** *(cross-cutting)* | Per-session root scoping filesystem + AppArmor + warm-runner reuse |
| [16-lifecycle-and-events](components/16-lifecycle-and-events.md) | **Lifecycle & events** *(cross-cutting)* | The ~110 SDK events and their temporal ordering across a session's life |
| [17-telemetry](components/17-telemetry.md) | **Telemetry** *(cross-cutting)* | Opt-in OpenTelemetry → OpenInference spans to Arize Phoenix; null-default, zero-overhead |
| [18-redaction](components/18-redaction.md) | **Anonymization** *(cross-cutting, premium)* | Presidio + NaCl pseudonymization wired at four seats (history · tools · output · telemetry) |
| [19-secrets](components/19-secrets.md) | **Secrets** *(cross-cutting)* | `scheme://path#key` resolver plugins + `*_auth` family + leak-proof `AuthAttempt` |
| [20-memory](components/20-memory.md) | **Memory** *(subsystem)* | "The School" — raw authoring + curator-driven validate/escalate/dismiss |
| [21-resilience-drift](components/21-resilience-drift.md) | **Resilience / drift** *(cross-cutting)* | Behavior-drift detection & steering: drift monitor, reliability reactor (migrating), continuity scopes, tag/embedding injection |
| [22-gossip](components/22-gossip.md) | **Gossip / federation** *(cross-cutting, premium)* | Multi-daemon federation: peer heartbeat/liveness, remote subagent delegation, git workspace sync, dashboard |
| [23-scaffold](components/23-scaffold.md) | **jaato-scaffold** *(tooling)* | Authoring CLI: `explain`/`validate`/`new` over an introspection core that reflects the installed framework; surfaces silent-ignore asset failures |

## Notes on accuracy

Each doc is grounded in the actual source (real class/function names, `.jaato/` paths, `path:line`
anchors) and flags anything that is design-stage-only or not yet implemented. Two terminology points to
keep in mind when reading: a **persona** is agent Markdown (not a class; the spawn/completion schemas
live on the **profile**), and a **cascade** is an *asynchronous, reactor-driven* chain of headless agent
sessions — each stage's `agent.completed` event triggers a reactor that spawns the next stage.
