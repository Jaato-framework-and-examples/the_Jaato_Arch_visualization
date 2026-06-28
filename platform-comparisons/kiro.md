# Platform comparison: **Kiro** vs **jaato**

> Like the [Ona comparison](ona.md), this is a **platform** comparison, not an SDK one — but where Ona is a remote API, **Kiro is an agentic IDE**. There's no `Agent(...)` to write; you drive Kiro from its **IDE**, its **CLI**, or **config files** (`.kiro/`). So this compares the two at the **CLI + config-file** level — `.kiro/` vs `.jaato/`, `kiro-cli` vs `jaato` — with **spec-driven vs persona/cascade** as the defining difference.

Both are "agentic engineering" surfaces, but from opposite directions:

- **Kiro** (AWS) is an **agentic IDE** built around **spec-driven development**: it turns a prompt into structured `requirements.md` → `design.md` → `tasks.md` *before* writing code, then implements/verifies against that spec. Its programmatic surface is a **headless CLI** (`kiro-cli`, for CI/CD), plus **JSON/markdown config** — custom agents, **hooks**, **steering files** — and **MCP**. It's built on **Amazon Bedrock** and is **Claude-model-centric**.
- **jaato** is a **self-hosted, provider-agnostic daemon**. Agents are **personas** (Markdown) under **profiles** (model/provider/plugins/permissions), run as **isolated per-session subprocesses**. It's driven by an SDK, by raw protocol — or, like Kiro, **from the CLI** (`jaato --prompt`) + a **`.jaato/` config tree** (personas, profiles, **reactors**). It's model- and runtime-agnostic (any provider, local GPUs).

So both give you file-defined agents you can run headless from a terminal. Kiro is an **IDE-first, spec-driven, Claude/Bedrock** product; jaato is a **daemon-first, persona/cascade, provider-agnostic** engine. Read it as a trade, not a scoreboard.

> **Setup.** Kiro: install the `kiro-cli`; auth via a `KIRO_API_KEY` (headless mode, added 2026); config lives in `.kiro/` (project) or `~/.kiro/` (global). jaato: run the daemon; the `jaato` CLI client drives it (`jaato --prompt …` for non-interactive single-shot); config lives in `.jaato/` (workspace). Because `jaato` is an ordinary CLI, it also composes into CI/scripts — or behind a shebang, like any executable (an emergent use, not a documented feature).

---

## 1. Run an agent headless

**Kiro** — the CLI in non-interactive mode (for CI/pipelines); pre-authorize tools since there's no prompt:
```bash
export KIRO_API_KEY=...
kiro-cli chat --no-interactive "Who are you? One sentence."

# pipe context in + trust a tool category (no interactive approval in headless):
git diff | kiro-cli chat --no-interactive --trust-tools=read,grep "Review these changes for security"
```

**jaato** — the daemon's CLI client, non-interactive single-shot:
```bash
jaato --prompt "Who are you? One sentence."

# composes into pipelines/CI the same way; the agent's tools + permissions come from its profile:
git diff | jaato --prompt "Review these changes for security" --agent reviewer
```

**Side by side.** Both run a file-defined agent **headless from a terminal**, pipe-friendly for CI. Kiro authorizes tools **on the command line** (`--trust-tools` / `--trust-all-tools`) because headless can't prompt; jaato carries tools **and** their permission policy in the agent's **profile** (so the same `jaato --prompt` is safe headless without per-call flags — Example 3). Kiro talks to **Bedrock**; jaato to whatever provider the profile names.

## 2. Define an agent

**Kiro** — one **JSON** file fuses persona + model + tools + permissions:
```jsonc
// .kiro/agents/reviewer.json   (project)   ·   ~/.kiro/agents/ (global)
{
  "name": "reviewer",
  "description": "Reviews diffs for security issues",
  "prompt": "file://./prompts/reviewer.md",   // the persona/soul (inline text or a file)
  "model": "claude-sonnet-4",                 // Bedrock / Claude-centric
  "tools": ["read", "grep", "@git"],
  "allowedTools": ["read", "@git/git_status"],
  "toolsSettings": { "write": { "allowedPaths": ["src/**"] } }
}
```

**jaato** — the same concerns, split across **persona** (soul) and **profile** (substrate):
```markdown
<!-- .jaato/agents/reviewer.md — the persona: role, voice, behaviour (NOT a task) -->
You are a security reviewer. You read diffs and flag injection, authz, and secret-handling
risks succinctly, citing file:line.
```
```yaml
# .jaato/profiles/reviewer.yaml — model / provider / plugins / permissions / schemas
model: claude-sonnet-4-6
provider: anthropic
plugins: [cli, file_edit]
plugin_configs:
  permission:
    policy:
      defaultPolicy: deny
      whitelist:
        tools: [read, grep]
        arguments: { file_edit: { path: ["src/**"] } }   # per-arg path scoping
```

**Side by side.** Kiro packs everything into **one `.kiro/agents/*.json`**; jaato deliberately **separates the persona** (`.jaato/agents/*.md` — the reusable "soul") from the **profile** (`.jaato/profiles/*.yaml` — the swappable runtime), so you can run the same persona on a different model/provider by swapping profiles. Both reference an external prompt file and scope `write` to paths. Kiro is **Claude/Bedrock**; jaato names any provider.

## 3. Tool permissions

**Kiro** — availability vs permission, set in config + on the CLI:
```bash
# headless: pre-authorize (no interactive approval possible)
kiro-cli chat --no-interactive --trust-tools=read,grep "…"     # or --trust-all-tools
```
```jsonc
// or per-agent in the JSON:  "allowedTools" pre-approves; "tools" controls availability
{ "tools": ["read","write","shell"], "allowedTools": ["read"] }
```

**jaato** — a per-session **permission policy** in the profile (and an interactive callback when attended):
```yaml
# .jaato/profiles/reviewer.yaml → the permission plugin's policy
plugin_configs:
  permission:
    policy:
      defaultPolicy: ask              # residual: tools not listed below escalate…
      whitelist: { tools: [read, grep] }   # …read/grep auto-approved
      blacklist: { tools: [shell] }        # …shell blocked
      # write is unlisted → falls through to defaultPolicy: ask
      #   (on_permission when attended, or a reactor gate when headless)
```

**Side by side.** Same two-layer idea — *availability* (which tools exist) vs *permission* (whether a call is approved). Kiro splits it across `tools`/`allowedTools` + the `--trust-*` flags; jaato puts a declarative **whitelist / blacklist + `defaultPolicy`** on the profile, evaluated **server-side per session** (with per-arg value patterns), so headless runs are governed by config rather than command-line trust — and the residual `defaultPolicy: ask` can escalate out-of-band via a reactor when no human is attached.

## 4. Event-driven automation

**Kiro** — **hooks**: run a prompt or shell command at lifecycle trigger points:
```jsonc
// in the agent JSON — fire on tool/turn lifecycle events
"hooks": {
  "postToolUse": [{ "matcher": "write", "command": "npm test" }],
  "preToolUse":  [{ "matcher": "shell", "command": "./guard.sh" }]
}
// trigger points: agentSpawn · userPromptSubmit · preToolUse · postToolUse · stop
```

**jaato** — **reactors**: event → condition → action over the daemon's bus:
```jsonc
// .jaato/reactors/on_write.json — react to a bus event, run a script (which can spawn sessions)
{ "rules": [{ "id": "test.after_write",
              "match": { "event_type": "tool.call_completed", "where": "tool_name == 'file_edit'" },
              "action": { "script": "scripts/run_tests.py" } }] }
```

**Side by side.** The same *event → action* idea, at different scopes. Kiro **hooks** fire on **one agent's tool/turn lifecycle** (config-only, shell/prompt actions). jaato **reactors** fire on the **daemon-wide event bus** and their action is a **script that can spawn whole sessions** — which is exactly how a **cascade** is built (`agent.completed` → spawn the next stage). So Kiro hooks ≈ jaato reactors for local automation, while reactors additionally do multi-agent orchestration.

## 5. Persistent project context

**Kiro** — **steering files**: Markdown in the repo that persists project context across sessions:
```markdown
<!-- .kiro/steering/conventions.md — always-on project guidance -->
Use PEP 8. All new endpoints need a test. Never edit files under vendor/.
```

**jaato** — base instructions + the persona carry standing context:
```markdown
<!-- .jaato/agents/reviewer.md (persona) and/or workspace base instructions -->
House rules: PEP 8; every endpoint needs a test; vendor/ is read-only.
```

**Side by side.** Both inject **standing, file-based guidance** that rides every run without being re-typed. Kiro's **steering files** are a dedicated `.kiro/steering/` layer; jaato folds the same role into the **persona** (and workspace base instructions). Same effect — durable project context as version-controlled Markdown.

## 6. The defining difference: spec-driven vs persona + cascade

**Kiro** — **spec-driven**: the unit of work is a **structured spec**, generated and approved before code:
```text
.kiro/specs/<feature>/requirements.md   ← what + acceptance criteria
                      design.md          ← how (architecture, decisions)
                      tasks.md           ← the ordered work list the agent executes & checks off
```

**jaato** — there's no spec scaffold; structured multi-step work is a **reactor-driven cascade** of personas:
```jsonc
// each stage is a persona+profile session; a reactor spawns the next on completion (see the cascade docs)
{ "rules": [{ "match": { "event_type": "agent.completed", "where": "source_agent == 'plan'" },
              "action": { "script": "scripts/spawn_implement.py" } }] }
```

**Side by side.** This is the real divergence. Kiro makes a **human-approved spec** (`requirements`/`design`/`tasks`) the durable artifact and source of truth — great when you want the *plan* reviewed before the agent acts. jaato has **no spec document**; it structures big work as an **event-driven cascade** of isolated persona stages, each typed by a **completion gate**, chained by **reactors** — great when you want **autonomous, isolated, recoverable** multi-stage execution. Spec-as-artifact vs cascade-as-pipeline.

---

## Coming from Kiro

Not a scorecard — if you work in Kiro, here's what actually changes when you move to jaato, and what it buys you:

- **`kiro-cli chat --no-interactive` becomes `jaato --prompt`.** Same headless, pipe-friendly single-shot you already reach for in CI — but because `jaato` is an ordinary CLI client over the daemon, it also composes into scripts or sits behind a shebang like any executable. The big difference is trust: where Kiro pre-authorizes tools on the command line (`--trust-tools` / `--trust-all-tools`) because headless can't prompt, jaato carries tools *and* their permission policy in the agent's profile — so the same `jaato --prompt` is governed by config, no per-call trust flags.
- **`.kiro/agents/*.json` splits into a persona and a profile.** Kiro fuses persona + model + tools + permissions into one JSON file; jaato deliberately separates the **persona** (`.jaato/agents/*.md` — the reusable "soul": role, voice, behaviour) from the **profile** (`.jaato/profiles/*.yaml` — the swappable substrate: model, provider, plugins, permission policy). Same concepts, but you run one persona on a different model or provider by swapping profiles. The `allowedTools`/`tools` split you know maps onto a declarative **whitelist / blacklist + `defaultPolicy`**, evaluated server-side per session with per-arg value patterns.
- **Kiro hooks become reactors — and reactors go further.** A hook fires on **one agent's** tool/turn lifecycle (`postToolUse`/`preToolUse`/`stop`) and runs a shell command or prompt. A jaato **reactor** fires on the **daemon-wide event bus** (event → condition → action), and its action is a script that can **spawn whole sessions**. So your `postToolUse: npm test` ports almost directly, but the same mechanism also chains multi-stage work: `agent.completed` → spawn the next persona is exactly how a **cascade** is built.
- **Claude-on-Bedrock becomes provider- and runtime-agnostic.** Kiro is Claude-model-centric on Amazon Bedrock; jaato names any provider in the profile (Anthropic, Google, OpenAI, local vLLM/Ollama/…) and runs the daemon and its AppArmor-isolated sessions on your own hardware, local GPUs included. Steering files (`.kiro/steering/`) don't disappear either — that standing, version-controlled project context folds into the **persona** and workspace base instructions.

**What to keep in mind (honest trade-offs).**
- This is a **platform comparison** at the **CLI + config** level: Kiro has no build-an-agent SDK — you drive it via the IDE, `kiro-cli`, and `.kiro/` files, and jaato is shown the same way (`jaato --prompt` + `.jaato/`). But jaato *also* exposes SDKs and a raw WS protocol that Kiro has no equivalent of, if you outgrow the CLI surface.
- Kiro is **IDE-first, Claude/Bedrock-centric, and young** — the headless CLI only landed in 2026, and the IDE plus the spec workflow are the real center of gravity. The snippets here use documented CLI/config shapes (`kiro-cli chat --no-interactive`, `.kiro/agents/*.json`, hooks, steering); verify against the version you install. Going provider-agnostic and self-hosted with jaato is the **opposite trade**: more infrastructure to run, but it's yours and model-portable.
- **The spec-driven IDE is a real strength jaato has no analog for.** Kiro's center of gravity is the **human-approved spec** (`requirements`/`design`/`tasks`) as the durable artifact and source of truth — plan reviewed before the agent acts. jaato has no spec document; it structures big work as an **event-driven cascade** of isolated persona stages, each typed by a server-enforced **completion gate** and chained by reactors — autonomous and recoverable rather than plan-first. They overlap on *file-defined agents you run headless*, and diverge most on how multi-step work is structured. If the reviewed plan-as-artifact is what you value most in Kiro, know that you're trading it for the cascade, not replacing it like-for-like.
