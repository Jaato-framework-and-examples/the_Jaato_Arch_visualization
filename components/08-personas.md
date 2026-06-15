# Personas

> **A persona is the *identity* of a jaato agent — its role, voice, knowledge and lifecycle behaviour — authored as a Markdown file under `.jaato/agents/<name>.md` whose rendered text becomes the session's system instructions.**
> **Layer (bottom→top):** sits *above* the Profile (the technical config) and *below* the cascade stages / reactors that invoke agents · **Lives in:** `jaato` (rendered by `jaato-server/server/session_manager.py`, expanded by `jaato-server/shared/dynamic_instructions.py`; persona files live in `.jaato/agents/`)

## What it is

A jaato **Profile** answers *"what can this agent do and with what knobs?"* — model, provider, plugin list, GC strategy, schemas. A **persona** answers the orthogonal question *"who is this agent?"* — its role declaration, tone, domain knowledge, and what it should do at the start and end of a run. In jaato the persona is **not a Python class**. It is the agent's **system instructions**, authored as Markdown.

The key mechanism: the Profile field `system_instructions` is **deprecated**. The docstring for `SubagentProfile` states plainly that you should "Use agents (`.jaato/agents/`) instead… When an agent is specified via `--agent`, its rendered markdown replaces this field. Profiles should contain runtime config only" (`config.py:889-891`). Loading a profile that still carries an inline `system_instructions` emits a `DeprecationWarning` telling the author to "Move the prompt to `.jaato/agents/{name}.md`" (`config.py:1930-1932`). So the persona has been deliberately split out of the Profile into a file of its own.

Because the persona is plain Markdown rendered into the prompt, it can be enriched at render time: it carries `{{param}}` placeholders (filled from caller-supplied `agent_params`) and `{{!py:script.py}}` **prefetch** placeholders that run framework-authority scripts whose output is embedded before the agent's first turn (`dynamic_instructions.py:1-39`). The persona thus *bundles together*, at the authoring layer, the role prose, the prefetched live context, and — by convention — the continuity behaviour, while the matching **Profile** supplies the spawn schema and completion schema that bracket the agent's input and output.

## Where it sits in the stack

Directly **below** a persona is its **Profile** (`.jaato/profiles/<name>.json`, schema `SubagentProfile`), which supplies the technical substrate: model, provider, plugins, `spawn_payload_schema`, `completion_payload_schema`, GC. An agent Markdown file may name its substrate via a `default_profile` frontmatter key. Directly **above**, personas are consumed by whatever drives a session: the main session via `session.new --agent <name>`, cascade stages, and **reactors** that spawn headless sessions. Sideways, the persona's text is read by enrichment plugins — most importantly the **memory** plugin, which scans the rendered prompt for tags (the basis of cross-session continuity).

## Responsibilities

- Define the agent's **role, voice and domain knowledge** as system-instruction prose.
- Declare authoring-time **`{{param}}` placeholders** and optional `params` frontmatter (with `required` / `default` / `enum`).
- Optionally embed **prefetch** (`{{!py:script.py}}`) to inject mandatory live context at session start.
- Carry the **continuity** convention (`{{continuity_scope}}` + a store/retrieve postamble) when the agent should remember prior runs.
- Optionally name a **`default_profile`** so the persona pulls in the right technical substrate when no `--profile` is given.

## Key concepts & structure

### Persona file: `.jaato/agents/<name>.md`
A persona is a single `<name>.md` (or a directory `<name>/PROMPT.md` / `SKILL.md`) resolved by `SessionManager._resolve_agent()` (`session_manager.py:423`). The search path is, in order: a `config_root` override, then `<workspace>/.jaato/agents/` and `.../prompts/`, then `~/.jaato/agents/` and `.../prompts/` (`session_manager.py:451-460`).

### Optional YAML frontmatter
If the file starts with `---`, a YAML block is parsed (`session_manager.py:491-499`). Recognised keys: `params` (placeholder definitions with `default`/`required`/`enum`), `description`, and `default_profile` (`session_manager.py:503-512, 550-551`). Note: spawn/completion **schemas are NOT in the persona frontmatter** — they live on the Profile (`SubagentProfile.spawn_payload_schema`, `.completion_payload_schema`, `config.py:967-968`); the persona reaches them via `default_profile`.

### Prefetch placeholders
`{{!py:script.py args}}` runs a kb-authored `render(context, args)` script on the framework's authority *before* the first turn, embedding its output into the prompt (`dynamic_instructions.py:1-39, 68`). Strict by default — a failed prefetch aborts session creation; the `?` form (`{{!py?:...}}`) is best-effort (`dynamic_instructions.py:59-67`).

### Continuity scope
`{{continuity_scope}}` is **not** a special framework token — it is an ordinary `{{param}}` plus the memory plugin's `enrich_prompt`. The caller passes a stable scope-id via `agent_params`; the literal value lands in the prompt; the memory plugin paragraph-coherently matches it against stored tags and surfaces an `💡 Available Memories` hint (`agent-continuity.md:49-101`). A persona postamble nudges the agent to `store_memory` under the same tag before completing, closing the loop across sessions.

## Lifecycle / flow

1. Caller invokes `session.new --agent code-reviewer continuity_scope=acme-customer-api`; the `key=value` tail becomes `agent_params` (`agent-continuity.md:157-163`).
2. `_resolve_agent()` finds `.jaato/agents/code-reviewer.md`, parses frontmatter, applies `params` defaults, substitutes `{{param}}` placeholders, and returns `system_instructions` + `default_profile` (`session_manager.py:423-447, 501-551`).
3. If no explicit `--profile` was given, the persona's `default_profile` selects the Profile; the rendered text is written onto `profile.system_instructions`, replacing the deprecated field (`session_manager.py:4414-4437`).
4. During `JaatoSession.configure()`, the framework assembles the full system prompt and runs `expand_py_placeholders()` to execute any `{{!py:...}}` prefetch (`dynamic_instructions.py:33-38`).
5. Memory enrichment scans the assembled prompt; matching memories surface as a hint.
6. The agent runs; on completion it stores a continuity memory and calls `signal_completion` (validated against the Profile's `completion_payload_schema`).

## Configuration / authoring

```markdown
---
description: Reviews PRs with project-level memory
default_profile: code-reviewer
params:
  continuity_scope:
    required: true
    description: Stable scope id (repo slug, ticket)
---
You are the code-reviewer agent.

Your continuity scope is `{{continuity_scope}}`.  If memory hints
surface under that tag, retrieve them — they carry prior conventions
and known anti-patterns for this scope.

## Before signal_completion
Store a memory tagged `{{continuity_scope}}` summarising new
decisions and recurring issues, then call signal_completion.
```
(Pattern and worked example: `agent-continuity.md:445-509`.)

## Relationship to neighboring components

A persona is built **on** a Profile: the Profile is the chassis (model, plugins, schemas) and the persona is the driver's identity painted on top — the two are bound when `_resolve_agent` stamps the rendered Markdown onto `profile.system_instructions`. Personas are **consumed by** cascade stages and reactors, which spawn sessions naming an agent and passing `agent_params`. They **use** the prefetch mechanism (`dynamic_instructions.py`, documented separately) for input-side context and the completion-schema / `signal_completion` mechanism (in `lifecycle_tools.py`) for the output boundary — both of which the persona's prose can reference and reinforce.

## Example

The NIM smoke-test ships a real persona, `nim-tools.md`: a no-frontmatter Markdown body that declares the role ("smoke-test responder for an NVIDIA NIM endpoint exercising tool-calling + schema-driven completion"), prescribes a workflow (call one tool, summarise, then `signal_completion` with a payload matching the profile's `completion_payload_schema` whose fields are `summary`, `status` enum, optional `word_count`). The persona prose names the schema fields, but the schema itself is enforced by the Profile — a clean illustration of the identity/config split.

## Diagram brief (for illustration)

- **Layout:** a vertical layered stack with one side-pointing arrow to a plugin, and a horizontal session timeline at the bottom.
- **Boxes (bottom→top of the stack):**
  - `Profile (.jaato/profiles/<name>.json)` — sub-label "model · provider · plugins · spawn_payload_schema · completion_payload_schema · GC". This is the chassis.
  - `Persona (.jaato/agents/<name>.md)` — HIGHLIGHTED box. Sub-label "role · voice · knowledge · {{params}} · {{!py:prefetch}} · {{continuity_scope}}".
  - Above the persona, three small consumer boxes side by side: `Main session (--agent)`, `Cascade stage`, `Reactor (headless spawn)`.
  - To the right of the Persona box, a separate box `Memory plugin (enrich_prompt)`.
- **Arrows:**
  - From each consumer box DOWN into Persona, edge label "spawn + agent_params".
  - From Persona DOWN to Profile, edge label "default_profile → profile.system_instructions".
  - From Persona RIGHT to Memory plugin, edge label "rendered prompt scanned for {{continuity_scope}} tag".
  - From Memory plugin back LEFT to Persona, edge label "💡 Available Memories hint".
  - A bottom timeline arrow left→right with three ticks: "render persona ({{param}} + {{!py:prefetch}})" → "agent runs" → "store_memory + signal_completion (validated vs completion_payload_schema)".
- **Emphasis:** the Persona box (identity layer) is the focus — bold border / accent colour; the Profile box is muted to show it is the substrate beneath.
- **Caption:** "Persona = the agent's identity (authored Markdown), rendered onto the Profile's chassis and enriched at runtime with params, prefetch and cross-session memory."

## Source references
- `jaato-server/shared/plugins/subagent/config.py:889-891` — `system_instructions` deprecated; persona moved to `.jaato/agents/`, rendered Markdown replaces the field via `--agent`.
- `jaato-server/shared/plugins/subagent/config.py:1930-1938` — DeprecationWarning instructing authors to move the prompt to `.jaato/agents/{name}.md`.
- `jaato-server/server/session_manager.py:423-499` — `_resolve_agent()`: search path (`.jaato/agents/`, `prompts/`, user tier), `<name>.md` / `PROMPT.md` / `SKILL.md`, YAML frontmatter parse.
- `jaato-server/server/session_manager.py:503-551` — frontmatter `params`/`default_profile`/`description`; `{{param}}` substitution; returned `system_instructions`.
- `jaato-server/server/session_manager.py:4414-4437` — persona's rendered text stamped onto `profile.system_instructions`; `default_profile` selection.
- `jaato-server/shared/dynamic_instructions.py:1-39, 59-68` — input-side `{{!py:script.py}}` prefetch expansion, strict-vs-best-effort, run during `configure()`.
- `jaato/docs/design/agent-continuity.md:49-101, 445-509` — `{{continuity_scope}}` as param + memory `enrich_prompt`; persona-level continuity pattern and worked example.
- `jaato-server/shared/plugins/subagent/config.py:967-968` — `spawn_payload_schema` / `completion_payload_schema` live on the Profile, not the persona frontmatter.
