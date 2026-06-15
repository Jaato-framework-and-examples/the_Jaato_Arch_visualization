# Profiles (Agent Profiles / `SubagentProfile`)

> **A profile is a named YAML file (JSON also accepted) that declaratively parameterizes a session or subagent — which model/provider it runs on, which plugins (tools) it gets, per-plugin config, GC strategy, environment, and completion contracts.**
> **Layer (bottom→top):** the declarative configuration substrate that a session/agent is built from — it sits *below* the runtime that consumes it and *above* nothing (it is hand-authored config). · **Lives in:** PUBLIC `jaato/jaato-server/shared/plugins/subagent/config.py` (canonical `SubagentProfile` dataclass) · profile files in `.jaato/profiles/*.yaml` (YAML preferred; `*.json` also accepted) · premium management in `jaato-premium/jaato_premium/profile_manager/`.

## What it is

In the jaato agent framework, an agent session needs a lot of decisions made before it can run: which LLM and provider to use, which tools (plugins) to expose, how aggressively to garbage-collect context when it fills up, what environment variables to inject, and whether the agent must produce a structured result. A **profile** packages all of those decisions into one declarative file so they are version-controlled, reusable, and selectable by name instead of being hardcoded per launch.

Concretely, a profile is a YAML file in `.jaato/profiles/` (YAML is the preferred authoring syntax; JSON is also accepted and parsed identically). At load time it is parsed into a `SubagentProfile` dataclass (`config.py:872`). The *same* dataclass is used both for the main session created from the CLI/SDK (`session.new --profile <name>`) and for subagents the parent delegates to (`spawn_subagent`) — "agent profile" and "subagent profile" are the same schema (`jaato/CLAUDE.md` "Agent Profiles": "Profile schema (same as `SubagentProfile`)").

A profile carries *runtime configuration only*. The agent's *instructions* (its system prompt / role) are authored separately as Markdown under `.jaato/agents/*.md`; the profile's own `system_instructions` field is explicitly **deprecated** in favor of those agent files (`config.py:889`, `jaato_subagent_profiles_reference.md:52-54`). When both are supplied, the agent's rendered Markdown replaces `system_instructions`.

## Where it sits in the stack

Below the profile there is nothing else to configure — it is the bottom, hand-authored layer. Directly *above* it sits the runtime that consumes it: `discover_profiles()` reads the files, `resolve_profiles()` flattens inheritance, and `JaatoServer` applies the resolved overrides during `initialize()` to spin up a `JaatoSession` on a chosen model provider with the listed plugins wired in (`jaato/CLAUDE.md` "Agent Profiles" → Flow). Sideways, a profile **selects a model provider plugin** (via `provider`/`model`), **lists tool plugins**, and passes each plugin its slice of `plugin_configs`. A profile is the substrate that a role/identity (the agent Markdown, sometimes called a "persona") and a cascade stage build on top of.

## Responsibilities

- Name and describe a reusable agent configuration (`name`, `description` — both required; `description` and `name` are never inherited).
- Select the LLM and provider (`model`, `provider`), or per-turn model tiers (`model_tiers`).
- Declare the tool plugins to expose (`plugins`), with optional preload / tool-allow-list modifiers.
- Carry per-plugin configuration (`plugin_configs`), including provider knobs and permission policy.
- Choose a context garbage-collection strategy (`gc`).
- Inject session-scoped environment variables with `${VAR}` expansion and secret-URI resolution (`env`).
- Compose from other profiles (`inherits`) and constrain output (`completion_payload_schema`, `spawn_payload_schema`).
- Optionally cap resources (`runtime_limits`) and opt into sandboxing (`apparmor`, `apparmor_fragments`).

## Key concepts & structure

### `SubagentProfile` — the canonical schema (`config.py:872`)
The required fields are `name` and `description`. `plugins` is **required** in a profile *file* (absent is rejected; use `plugins: []` for the minimal framework set of permission/reliability/lifecycle only) — see the explicit error at `config.py:1866-1877`. Other notable fields: `model`, `provider`, `max_turns` (default 10), `gc`, `env`, `plugin_configs`, `inherits`, `completion_payload_schema`, `spawn_payload_schema`, `completion_processors`, `runtime_limits`, `model_tiers`, `apparmor`, `apparmor_fragments`, `quirks`, and the derived `preloaded_plugins` / `tool_scopes`.

### `plugins` list syntax + modifiers (`config.py:290-418`)
Each entry is a plugin name that may carry a parenthesised modifier with two orthogonal knobs, parsed by `parse_plugin_entry`:
- **mode** (`preload` | `discover`, default `discover`): `todo(preload)` forces *all* of that plugin's tools (including discoverable ones) into the initial wire context; `discover` leaves discoverable tools deferred until the model introspects.
- **tools** allow-list: `file_edit([readFile,writeFile])` restricts the plugin to exactly those tools; every other tool the plugin ships is dropped from the wire body and grammar surface for this session.
Forms freely mix: `file_edit(mode:preload, tools:[readFile,writeFile])`. Parsing splits these into `plugins` (clean names), `preloaded_plugins` (a set), and `tool_scopes` (plugin → allow-list).

### `plugin_configs` — per-plugin layered config (`config.py:947`, `profile-plugin-configs.md`)
A dict of plugin-name → config dict, passed to each plugin's `initialize(config)` at session creation. Provider plugins are configured the same way. Anthropic config is namespaced into layers: top-level auth (`api_key`, `oauth_token`), `api_params` (Messages-API body fields like `temperature`, `max_tokens`, `enable_thinking`, `thinking_budget`), and a reserved `framework_overrides` (`jaato/CLAUDE.md` "Anthropic Claude" profile knobs). OpenRouter adds a `routing` layer (provider-routing keys like `sort`, `order`, `only`, `data_collection`) on top of `api_params`. Values support `${VAR}` expansion and `vault://`-style secret URIs.

### `gc` — context garbage collection (`GCProfileConfig`, `config.py:736`)
Controls how the context window is kept from overflowing. Keys: `type` (`truncate` | `summarize` | `hybrid` | `budget`), `threshold_percent` (default 80) to trigger, `target_percent` (default 60) after GC, `pressure_percent` (`0`/`null` = continuous mode), `preserve_recent_turns`, `notify_on_gc`, `summarize_middle_turns`, `max_turns`.

### Inheritance & resolution (`config.py:1360` `resolve_profiles`, `config.py:1444` `_merge_profiles`)
Profiles compose via `inherits` (a string or list of parent names). Resolution runs after discovery as a topological flatten with cycle detection; afterward `inherits` is cleared. Merge rules:
- **Collections (union):** `plugins`, `preloaded_plugins`, `env`, `plugin_configs` (deep-merged per plugin/key).
- **Scalars (agreement-or-override):** `model`, `provider`, `gc`, `runtime_limits`, `completion_payload_schema`, `spawn_payload_schema` — parents must agree or the child must override; otherwise it is a hard error.
- **`max_turns`:** most restrictive (minimum) across parents unless the child overrides.
- **Concatenation:** `system_instructions` (parents → child, joined by blank lines).
- **Never inherited:** `name`, `description`, and `model_tiers`.

### Model / provider resolution at apply time (`jaato_subagent_profiles_reference.md:1037-1047`)
For a subagent the active model is resolved `profile.model` → `SubagentConfig.default_model` → parent session's model; provider similarly `profile.provider` → config default → parent. When `model_tiers` is non-empty, `model` is ignored (warning logged) and the per-turn tier model wins.

## Lifecycle / flow

1. **Author** a profile file under `.jaato/profiles/` (or premium registers one via entry points).
2. **Discover** — `discover_profiles()` scans three tiers in precedence order: workspace `.jaato/profiles/` → user `~/.jaato/profiles/` → premium entry-point profiles; higher tier wins on name collision (`config.py:1953`, `jaato_subagent_profiles_reference.md:58-83`).
3. **Parse** each file into a `SubagentProfile` (`_scan_profiles_dir`, `config.py:1793`); `plugins` entries are split into clean names + preload set + tool scopes.
4. **Resolve inheritance** — `resolve_profiles()` flattens parents into children, detecting cycles and scalar conflicts (`config.py:1360`).
5. **Select** — client sends `session.new --profile <name>` (IPC) or `create_session(profile="...")` (SDK); `session.profiles` lists available ones.
6. **Apply** — `JaatoServer` applies the resolved overrides during `initialize()`: variables are expanded, model/provider chosen, plugins exposed with their `plugin_configs`, GC configured, env set (`jaato/CLAUDE.md` Flow).
7. **Run** — the resulting `JaatoSession` runs the agent; subagents share the parent `JaatoRuntime` but get an isolated session and tool subset.

## Configuration / authoring

Files live in `.jaato/profiles/`. Minimal valid profile needs `name`, `description`, and `plugins`. Example (provider knobs + GC + preload + tool scope):

```yaml
name: researcher
description: Deep research profile
model: claude-sonnet-4-20250514
provider: anthropic
plugins:
  - cli
  - web_search
  - memory
  - "todo(preload)"
  - "file_edit([readFile])"
plugin_configs:
  anthropic:
    api_params: { temperature: 0.0, max_tokens: 4096 }
  web_search:
    max_results: 5
    region: us-en
gc: { type: budget, threshold_percent: 80.0, pressure_percent: 0 }
env:
  PROJECT_ROOT: "${workspaceRoot}"
  DB_PASSWORD: "vault://secret/myapp#db_password"
```

(Schema example adapted from `jaato/CLAUDE.md` "Agent Profiles" and `jaato_subagent_profiles_reference.md:100-142`.)

## Relationship to neighboring components

- **Persona / agent identity:** A *profile* is the **technical config**; the *role/identity* (the system prompt that says *how* to behave) lives separately as Markdown under `.jaato/agents/*.md`. The source calls this the "agent persona" only in passing — e.g. the `tool_scopes` comment warns to keep "the agent persona['s]" referenced tools in sync with the allow-list (`config.py:942-945`) — but there is **no dedicated `Persona` class in the profile source**; persona = the agent Markdown that replaces the deprecated `system_instructions`. (Relationship stated; a separate Persona document covers identity in depth.)
- **Model provider plugins:** the profile *selects* one via `provider`/`model` (or `model_tiers`); the provider is itself a plugin configured through `plugin_configs[<provider>]`.
- **Tool plugins / registry:** the `plugins` list drives which plugins the registry exposes and which tools reach the wire.
- **Runtime / session:** `JaatoRuntime` + `JaatoServer` consume the resolved profile to build a `JaatoSession`.
- **Subagents / cascades:** the same profile schema parameterizes delegated subagents; a cascade stage builds on a profile as its substrate.
- **Premium profile_manager:** `jaato-premium/jaato_premium/profile_manager/` provides WS-based CRUD (`profile.list|get|create|update|delete|validate|scaffold|clone`) over a typed `Profile` dataclass (`schema.py:173`) — a leaner mirror of `SubagentProfile` (name, description, inherits, plugins, provider, model, max_turns, plugin_configs, gc) backed by JSON files in `jaato_premium/jaato_premium/profiles/`.

## Example

A real premium profile — `skill-mod-code-002-retry` (premium's `profile_manager` persists it as JSON; shown here in the preferred YAML form) — shows the pieces working together:

```yaml
name: skill-mod-code-002-retry
description: "[GENERATE/ADD Flow] Assist adding retry patterns using mod-code-002 templates and ERI guidance."
plugins:
  - artifact_tracker
  - cli
  - filesystem_query
  - lsp
  - references
  - "template(preload)"
  - memory
  - auto_steering
plugin_configs:
  auto_steering:
    rules:
      - { id: template-preference, inject_every_n_turns: 2, enabled: true }
  references:
    preselected:
      - mod-code-002-retry-java-resilience4j
      - eri-code-009-retry-java-resilience4j
    exclude_tools: [selectReferences]
system_instructions: "Use module templates and ERI to insert retry patterns into codebase."
max_turns: 15
```

Here `template(preload)` forces the templating tools into the initial context, `references` is steered to two preselected knowledge entries with one tool excluded, and `auto_steering` is given a per-turn nudge rule — all without touching any framework code.

## Diagram brief (for illustration)

- **Layout:** Left-to-right flow with a layered detail panel. A single authored file on the left fans through a resolution pipeline into a running session on the right.
- **Boxes:**
  1. `.jaato/profiles/researcher.yaml` (a document icon) — labeled "Profile file (YAML; JSON also accepted)".
  2. A stacked "3-tier discovery" box: top→bottom rows "Workspace .jaato/profiles" / "User ~/.jaato/profiles" / "Premium entry-points" — labeled "discover_profiles()".
  3. "resolve_profiles() — flatten inheritance, detect cycles/conflicts".
  4. **Center, emphasized:** a large box `SubagentProfile` with an inner field list: `name` · `description` · `model` / `provider` · `plugins [todo(preload), file_edit([readFile])]` · `plugin_configs {anthropic.api_params, web_search}` · `gc {type, threshold%}` · `env {${VAR}, vault://}` · `inherits[]` · `completion_payload_schema`.
  5. "JaatoServer.initialize() — apply overrides".
  6. "JaatoSession (running agent)".
  7. A small detached card above box 6 labeled "Agent Markdown .jaato/agents/*.md (role / persona = instructions)".
- **Arrows:**
  - file → discovery (label "scan, precedence").
  - discovery → resolve (label "parse → dataclass").
  - resolve → SubagentProfile (label "flattened").
  - SubagentProfile → JaatoServer.initialize (label "session.new --profile").
  - JaatoServer.initialize → JaatoSession (label "build session").
  - From SubagentProfile, three labeled side-arrows: "selects model provider" → a Provider plugin icon; "exposes tools" → a Plugins/tools icon; "GC strategy" → a GC icon.
  - Agent Markdown card → JaatoSession (dashed arrow, label "supplies instructions (replaces deprecated system_instructions)").
- **Emphasis:** Highlight the central `SubagentProfile` box (it is what this doc is about) and visually separate it (color/border) from the dashed "Agent Markdown / persona" card to make the *config vs. identity* distinction obvious.
- **Caption:** "A Profile is the declarative, version-controlled config (model, plugins, GC, env) that the runtime resolves and applies to build a session — distinct from the agent Markdown that gives the agent its role."

## Source references
- `jaato/jaato-server/shared/plugins/subagent/config.py:872` — `SubagentProfile` dataclass (canonical schema: name, description, plugins, plugin_configs, model, provider, gc, env, inherits, completion/spawn schemas, runtime_limits, model_tiers, apparmor, quirks).
- `…/config.py:290-418` — `parse_plugin_entry` / `parse_plugin_list`: `plugins` modifier syntax (`mode:preload`/`discover`, `tools:[...]` allow-lists).
- `…/config.py:736` — `GCProfileConfig`: GC type/threshold/target/pressure/preserve fields.
- `…/config.py:889` and `…/config.py:1927-1940` — `system_instructions` deprecated in favor of `.jaato/agents/*.md`.
- `…/config.py:1360` `resolve_profiles` & `…/config.py:1444` `_merge_profiles` — inheritance: union collections, agreement-or-override scalars, concatenated instructions, min `max_turns`.
- `…/config.py:1953` `discover_profiles` & `…/config.py:1866-1877` — 3-tier discovery precedence; `plugins` required (absent rejected, `[]` = minimal framework set).
- `jaato/CLAUDE.md` "Agent Profiles" + "Anthropic Claude"/"OpenRouter" knobs — profile schema example, `session.new --profile` flow, `plugin_configs` provider layering (`api_params`, `routing`).
- `jaato/docs/jaato_subagent_profiles_reference.md:52-54, 1037-1049` — profile vs. agent (instructions) distinction; model/provider resolution chain (profile → config default → parent).
- `jaato-premium/jaato_premium/profile_manager/schema.py:173` & `…/profile_manager/extension.py` — premium `Profile` dataclass + WS CRUD; profile JSON files in `jaato-premium/jaato_premium/profiles/`.
