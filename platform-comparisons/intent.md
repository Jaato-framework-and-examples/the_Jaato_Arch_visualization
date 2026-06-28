# Platform comparison: **Intent** vs **jaato**

> The most different entry in this series — and the only **prose-only** one. [Ona](ona.md) is a remote API and [Kiro](kiro.md) is a CLI + config tree, so both could be compared in code. **Intent has no programmatic surface at all** — no CLI, no API, no config files — it's a **desktop application** you drive by hand. So there's nothing to put in a code column; this compares the two purely on **architecture and orchestration model**.

Both are about **orchestrating multi-agent work**, but they sit on opposite sides of a line:

- **Intent** (Augment Code) is a **macOS desktop workspace** — an orchestration *cockpit*. It bundles an IDE, terminal, browser, and git client into one app, and runs a **spec-driven, multi-agent workflow**: a **coordinator** drafts a living specification from your codebase, **specialist agents** execute decomposed tasks **in parallel** (each in its own **git worktree**), and a **verifier** checks the work against the spec before handing back to you. Notably, Intent is a **meta-orchestrator**: the actual agents are *other* backends it drives — **Auggie, Claude Code, Codex, OpenCode**.
- **jaato** is a **headless orchestration engine**. It runs **its own** agents — **personas** (Markdown) under **profiles** (model/provider/plugins/permissions) — as **isolated per-session subprocesses**, and orchestrates multi-stage work through **reactor-driven cascades** and **subagent delegation**. You drive it programmatically (SDK / CLI / raw WS protocol); there is no GUI cockpit.

So both decompose a goal, run specialists in isolation, and verify — but **Intent is a human-operated desktop app that conducts other vendors' agents**, while **jaato is a programmable daemon that runs its own**. One is a cockpit; the other is an engine. Read it as a trade, not a scoreboard.

> **No code here.** Intent exposes no CLI/API/config to show next to jaato's. The comparison below is architectural.

---

## Orchestration model

**Intent** — **coordinator → specialists → verifier**, organized around a **human-approved spec**. The coordinator analyzes the repo and drafts a living specification; you approve the plan; specialist agents then work **in parallel** on decomposed tasks, each isolated in its own worktree; a verifier validates against the spec before it reaches you. Six built-in specialist roles ship in the box: **Investigate, Implement, Verify, Critique, Debug, Code Review**.

**jaato** — the same *decompose → execute → verify* shape, but **event-driven and headless**. A **lead persona** delegates to **subagents** (`spawn_subagent`, daemon-driven, each isolated), or a **reactor-driven cascade** chains persona stages — e.g. `plan → implement → verify` — where each stage's `agent.completed` event triggers a reactor that spawns the next, and each stage is typed by a **completion gate**. Personas/profiles are **arbitrary** (you author them), not a fixed set of six.

**Side by side.** Intent's coordinator/specialist/verifier maps closely onto jaato's lead + subagents (or a plan/implement/verify cascade). The differences: Intent's roster is **fixed and built-in** (six specialists) while jaato's personas are **open-ended**; Intent sequences around a **human-approved spec** in a GUI, while jaato sequences around **events + reactors** with no human in the loop unless a gate asks for one.

## Isolation

**Intent** runs each parallel task in its **own git worktree** — branch-level isolation so specialists don't collide, on your machine.

**jaato** runs each agent in its **own per-session subprocess** — **AppArmor-confinable**, **cgroup-boundable** (`memory.max`), scoped to a **workspace**, on infrastructure you host.

**Side by side.** Same instinct — isolate concurrent agents so they don't step on each other. Intent's unit is a **git worktree** (filesystem/branch isolation, local); jaato's is a **confined runner subprocess** (OS-level isolation, self-hosted, multi-tenant). jaato's is the stronger boundary; Intent's is lighter and git-native.

## Who runs the agents

**Intent** is a **meta-orchestrator** — it doesn't run a model itself; it conducts **external backends** (Auggie, Claude Code, Codex, OpenCode). Its value is the *workspace + orchestration + verification* around whatever agent you plug in.

**jaato** **is** the runtime — it runs the agents directly against any provider (Anthropic, Google, OpenAI, local vLLM/Ollama/…), with its own plugin tools, permissions, and completion gates.

**Side by side.** This is the sharpest divergence. Intent sits **above** agent backends and coordinates them through a desktop UI; jaato **is** the backend (and can itself be one of the things a meta-orchestrator drives). If you already live in Claude Code/Codex and want a cockpit to run several in parallel against a spec, that's Intent's pitch; if you want a hostable, provider-agnostic engine to embed and automate, that's jaato's.

## Interface

**Intent** — a **macOS desktop GUI** (IDE + terminal + browser + git, unified). Human-operated; no headless/programmatic entry point found.

**jaato** — **programmatic only**: an SDK (Python IPC / TypeScript WS), a CLI (`jaato --prompt`), and the raw WS protocol. No GUI cockpit (the federation dashboard aside).

**Side by side.** Opposite ends: Intent is **GUI-first, human-in-the-loop by design**; jaato is **API-first, automatable and unattended by design**. This is why the comparison is prose-only — there's no Intent command or config to set beside jaato's.

---

## When each shines

| You want… | Reach for |
|---|---|
| A **desktop cockpit** to run several agents in parallel against a **human-approved spec**, with built-in specialists, worktree isolation, and verification — conducting Claude Code / Codex / Auggie / OpenCode | **Intent** |
| A reviewed plan + a hands-on, GUI-driven multi-agent workflow over backends you already use | **Intent** |
| A **headless, programmable, provider-agnostic** engine that **runs** the agents — personas/profiles, reactor-driven cascades, completion gates, OS-isolated multi-tenant sessions, driven by SDK/CLI/protocol and automatable end-to-end | **jaato** |

**Honest caveats.**
- **This is an architecture comparison, not a usage one.** Intent has **no CLI, API, or config surface** to compare in code — it's a desktop app driven by hand — so everything above is conceptual. Details are **web-verified** (the coordinator/specialist/verifier model, the six built-in roles, worktree isolation, the supported backends); verify against the current product, which is young and moving.
- **Different layers.** Intent is a **meta-orchestrator + UI** *above* agent backends; jaato is an **engine** that *is* a backend. They overlap on *decompose → isolate → verify* orchestration and diverge on everything around it (who runs the model, GUI vs API, fixed vs open personas).
- **Human-in-the-loop vs autonomous.** Intent centers a person approving a spec in a desktop app; jaato centers **autonomous, event-driven** execution with HITL only where a gate or reactor asks for it. Pick by whether a human cockpit or an automatable engine is what you're after.
