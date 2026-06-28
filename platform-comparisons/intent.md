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

**jaato** — the same *decompose → execute → verify* shape, but **event-driven and headless**. A **lead persona** delegates to **subagents** (`spawn_subagent`, daemon-driven and async — *sharing the parent runner*; a per-subagent isolated runner is on the roadmap, not yet shipped), or a **reactor-driven cascade** chains persona stages — e.g. `plan → implement → verify`, **each stage its own independently isolated session** — where each stage's `agent.completed` event triggers a reactor that spawns the next, typed by a **completion gate**. Personas/profiles are **arbitrary** (you author them), not a fixed set of six.

**Side by side.** Intent's coordinator/specialist/verifier maps closely onto jaato's lead + subagents (or a plan/implement/verify cascade). The differences: Intent's roster is **fixed and built-in** (six specialists) while jaato's personas are **open-ended**; Intent sequences around a **human-approved spec** in a GUI, while jaato sequences around **events + reactors** with no human in the loop unless a gate asks for one.

## Isolation

**Intent** runs each parallel task in its **own git worktree** — branch-level isolation so specialists don't collide, on your machine.

**jaato** runs each session in its **own per-session subprocess** — **AppArmor-confinable**, **cgroup-boundable** (`memory.max`), scoped to a **workspace**, on infrastructure you host.

**Side by side.** Same instinct — isolate concurrent agents so they don't step on each other. Intent's unit is a **git worktree** (filesystem/branch isolation, local); jaato's is a **confined runner subprocess** (OS-level isolation, self-hosted, multi-tenant). jaato's is the stronger boundary; Intent's is lighter and git-native.

## Who runs the agents

**Intent** is a **meta-orchestrator** — it doesn't run a model itself; it conducts **external backends** (Auggie, Claude Code, Codex, OpenCode). Its value is the *workspace + orchestration + verification* around whatever agent you plug in.

**jaato** **is** the runtime — it runs the agents directly against any provider (Anthropic, Google, OpenAI, local vLLM/Ollama/…), with its own plugin tools, permissions, and completion gates. And via its **provider abstraction** it can itself **drive other agent CLIs** as backends (e.g. `claude_cli` wrapping Claude Code, plus gemini-cli, antigravity) — so jaato spans both layers: a drivable runtime *and*, when it wants, a meta-orchestrator over CLI agents.

**Side by side.** This is the sharpest divergence. Intent sits **above** agent backends and coordinates them through a desktop UI; jaato **is** the backend (and can itself be one of the things a meta-orchestrator drives). If you already live in Claude Code/Codex and want a cockpit to run several in parallel against a spec, that's Intent's pitch; if you want a hostable, provider-agnostic engine to embed and automate, that's jaato's.

## Interface

**Intent** — a **macOS desktop GUI** (IDE + terminal + browser + git, unified). Human-operated; no headless/programmatic entry point found.

**jaato** — **programmatic only**: an SDK (Python IPC / TypeScript WS), a CLI (`jaato --prompt`), and the raw WS protocol. The interactive client is a **terminal TUI** (`rich_client`); there is **no GUI cockpit** (federation/clustering is the **gossip peer-mesh**, not a UI).

**Side by side.** Opposite ends: Intent is **GUI-first, human-in-the-loop by design**; jaato is **API-first, automatable and unattended by design**. This is why the comparison is prose-only — there's no Intent command or config to set beside jaato's.

---

## Coming from Intent

Not a scorecard — if you orchestrate agents in Intent, here's what actually changes when you move to jaato, and what it buys you:

- **Your cockpit workflow becomes an event-driven cascade.** Intent's coordinator → specialists → verifier, sequenced around a human-approved spec in a desktop app, maps onto jaato's **lead + subagents** or a **reactor-driven cascade** (`plan → implement → verify`) — but headless and completion-gated. Instead of you approving a plan and watching parallel worktrees in a GUI, each stage runs as its own isolated session and its `agent.completed` event fires a reactor that spawns the next stage, typed by a **completion gate**. The same decompose/execute/verify shape, minus the human-in-the-loop window — unless a gate asks for one.
- **You stop conducting other backends and start running them — or running your own.** Intent is a **meta-orchestrator**: it never runs a model, it drives Auggie / Claude Code / Codex / OpenCode. jaato **is** the runtime — it runs personas directly against any provider (Anthropic, Google, OpenAI, local vLLM/Ollama), and via its provider abstraction it can itself **drive agent CLIs** as backends (`claude_cli`, gemini-cli, antigravity). So jaato spans both layers: the engine you embed *and*, when you want it, the meta-orchestrator over CLI agents you came for.
- **Worktree isolation becomes OS-level confinement.** Intent keeps parallel specialists from colliding by giving each its own **git worktree** — branch-level, local, on your Mac. jaato isolates each session in its **own subprocess** — **AppArmor-confinable**, **cgroup-boundable** (`memory.max`), scoped to a workspace, on infrastructure you host and can run multi-tenant. A stronger boundary, and a self-hosted one.
- **A GUI you drive by hand becomes an API you automate.** Intent is **GUI-first, human-in-the-loop by design** — an IDE/terminal/browser/git cockpit with no headless entry point. jaato is **API-first**: an SDK (Python IPC / TypeScript WS), a CLI (`jaato --prompt`), and the raw WS protocol, with a terminal TUI for interactive use. The personas/profiles are open-ended and yours to author, not a fixed roster of six. What was a desktop you sit in front of becomes an engine you embed and run unattended.

**What to keep in mind (honest trade-offs).**
- **This is an architecture comparison, not a usage one.** Intent has **no CLI, API, or config surface** to set beside jaato's — it's a desktop app driven by hand — so everything here is conceptual rather than code. The details (the coordinator/specialist/verifier model, the six built-in roles, worktree isolation, the supported backends) are **web-verified** against a product that is young and moving fast; check them against the current release.
- **You're crossing a layer boundary, not swapping equivalents.** Intent is a **meta-orchestrator plus UI** that sits *above* agent backends; jaato is an **engine** that *is* a backend. They overlap only on the *decompose → isolate → verify* core and diverge on everything around it — who runs the model, GUI versus API, fixed versus open personas — so this is a move between layers, not a like-for-like port.
- **You give up a human cockpit to gain an automatable one.** Intent centers a person approving a spec inside a desktop app, and that GUI cockpit with its human-approved-spec flow is a **genuine strength for hands-on work** — it's not a limitation jaato erases. jaato centers **autonomous, event-driven** execution with a human only where a gate or reactor asks for one. Move for the automatable engine; know that you're trading away the cockpit to get it.
