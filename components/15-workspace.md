# The Workspace

> **The workspace is the per-session working root — one directory tree per agent session — that everything in jaato treats as the unit of filesystem scope: the runner cwd, the AppArmor confinement boundary, and the affinity key for reusing a warm runner.**
> **Layer (bottom→top):** a *cross-cutting* entity. It threads through the runner tier (warm-slot reuse), the security tier (per-session AppArmor profile), the plugins (which contribute default rules scoped to it), and the cascade (which contributes custom rules and reuses a runner across sessions). · **Lives in:** `jaato` (PUBLIC) — `jaato-server/server/apparmor.py`, `jaato-server/shared/session_envelope.py`, `jaato-server/shared/config_resolver.py`, `jaato-server/shared/plugins/registry.py`; the per-plugin `get_apparmor_rules` classmethods under `jaato-server/shared/plugins/*/plugin.py`.

## What it is

When the jaato daemon hosts an agent session, the agent does its file work inside one directory: the **workspace**. The daemon resolves an absolute `workspace_path`, hands it to the runner subprocess in the session-bootstrap envelope, and from then on the workspace defines three things at once: (1) what the agent's tools read and write, (2) what the kernel lets the process touch (the per-session AppArmor profile is generated *around* this path), and (3) which warm runner the daemon can reuse for the next session.

The workspace is not a single class — it is a value (`workspace_path`) that is plumbed everywhere. It arrives on `SessionInitEnvelope.workspace_path` (`session_envelope.py:84`), is broadcast to every plugin via `PluginRegistry.set_workspace_path(path)` (`registry.py:1347`), anchors framework config lookup at `<workspace_path>/.jaato/` (`config_resolver.py:121-122`), and is the value substituted into every `{workspace_path}` placeholder in the AppArmor profile template (`apparmor.py:318`).

Its purpose is **multi-tenant isolation**: many sessions run on one host, and each must be unable to read or write another's files. The kernel — not application-level path checks — enforces this when AppArmor is available.

## Where it sits in the stack

Directly *below* the workspace is the **runner** subprocess (the confined process whose cwd and AppArmor profile are bound to the workspace) and the **daemon** (the unconfined orchestrator that resolves the path and provisions the profile). Directly *above* it are the **plugins** (`file_edit`, `lsp`, `cli`, …) that perform workspace-relative I/O and contribute rules scoped to it. Sideways it talks to the **AppArmor profile** `jaato-ws-{session_id}` and, in cascade workloads, to the **runner pool** that keys warm-slot reuse on the workspace/cascade identity.

## Responsibilities

- Define the agent's filesystem scope: `<workspace_path>/` rw, everything else default-deny.
- Anchor framework config discovery at `<workspace_path>/.jaato/` (profiles, agents, schemas, fragments).
- Serve as the substitution value for the per-session AppArmor profile so the kernel boundary wraps exactly this tree.
- Act as the affinity/reset key when a warm runner is reused.

## Key concepts & structure

### The path plumbing
- `SessionInitEnvelope.workspace_path` (`session_envelope.py:84`) — absolute path, or `None` for headless/no-workspace sessions. The `session_id` matches the profile name suffix `jaato-ws-{session_id}` (`session_envelope.py:83`).
- `PluginRegistry.set_workspace_path(path)` (`registry.py:1347-1368`) — broadcasts to every exposed plugin that implements `set_workspace_path`; re-broadcast on plugin (re)exposure (`registry.py:1108-1113`).
- `config_resolver` tiered lookup: workspace tier `<workspace_path>/.jaato/`, then user tier `~/.jaato/` (`config_resolver.py:121-122`, `:170`).

### The AppArmor profile generated around it
`AppArmorManager` (`apparmor.py:48`) renders `PROFILE_TEMPLATE` per session. The workspace rule is the core:
```
{workspace_path}/   rw,
{workspace_path}/** rwkl,
```
(`apparmor.py:318-319`). Sibling workspaces are **implicitly denied** by AppArmor default-deny — there is deliberately *no* explicit deny on the sessions root, because an explicit deny would override the workspace allow at equal specificity (`apparmor.py:413-417`). Narrow `audit deny ... wlk` rules carve user-authored config (`.jaato/agents/`, `profiles/`, `prompts/`, `scripts/`, `reactors.json`, `completion_schemas/`, `spawn_schemas/`, `instructions/`, `references/`, `apparmor-fragments/`) out of the writable tree (`apparmor.py:320-336`). The profile is written to `/etc/apparmor.d/jaato/jaato-ws-{session_id}` and loaded with `sudo apparmor_parser -r` (`apparmor.py:982-998`).

### Sub-profiles inside the per-session profile
Three nested scopes redeclare the workspace rules (AppArmor sub-profiles do **not** inherit base rules):
- `//tool_hat` (`apparmor.py:2148`) — entered by `ToolExecutor.execute` for in-process tools; adds read-denies so tools can't read other agents' personas/schemas.
- `//child` (`apparmor.py:2296`) — entered by cli/interactive_shell subprocesses via `preexec_fn`; **drops** the three escape-vector rules (`change_profile -> unconfined` + `/proc/self/attr/current w` + task variant) so a model-controlled subprocess cannot break confinement (`apparmor.py:2422-2433`).
- `jaato-ws-{parent}//{subagent}` — standalone sub-profile for an isolated subagent (`apparmor.py:1377`, `_render_sub_profile`).

## Lifecycle / flow

1. **Resolve.** Daemon resolves `workspace_path` and a `session_id`.
2. **Provision profile.** `provision_profile(session_id, workspace_path, …, plugin_rules)` (`apparmor.py:904`) renders the template (`_render_profile`, `apparmor.py:1883`) and loads it via `apparmor_parser -r`. Composition pulls in three contributors (see below).
3. **Spawn / claim runner.** Cold-spawn a runner, or claim a warm pool slot (forked from the template subprocess with plugin imports already warm).
4. **Self-confine.** In bootstrap step 1c the runner calls `confine_to_profile(jaato-ws-{session_id})` → `aa_change_profile` via ctypes, then verifies with `read_current_profile` (`server/runner/bootstrap.py:123,168,188`). Worker threads spawned after this inherit the confined cred.
5. **Bind plugins to the workspace.** `set_workspace_path` is broadcast; tools now operate workspace-relative.
6. **Run.** Tools enter `//tool_hat`; subprocesses enter `//child`. `add_reference_fragment` can hot-add read grants without a restart.
7. **Teardown.** `teardown_profile(session_id)` (`apparmor.py:1475`) sweeps worker threads back to unconfined, runs `apparmor_parser -R`, deletes the file and the `.refs.d/` fragments.

## Relationship 1 — Workspace ↔ warm-runner reuse

A **warm pool slot** is a runner forked from a template subprocess at daemon startup; it is *generic* — it has no workspace and runs unconfined. When a session arrives, the daemon claims a slot and dispatches `session.bootstrap` to it (the same RPC a cold runner gets). On reuse, three things must (re)bind to the new session's workspace:
- **cwd / `workspace_path`** — delivered fresh on the new `SessionInitEnvelope`; `set_workspace_path` re-broadcasts to plugins.
- **AppArmor profile** — the slot self-confines in bootstrap step 1c via `aa_change_profile` to `jaato-ws-{session_id}` (`bootstrap.py:123`). Because a fresh slot starts unconfined, this first transition is unconfined → S1.
- **per-session state** — plugins reset between sessions; warm imports survive.

A **cascade** is a multi-session run (discovery → context → codegen …) that the design intends to keep on **one** runner. Here the slot is already confined to the *previous* session's profile and must switch to the next. The base template carries `change_profile -> jaato-ws-*,` (template v28, `apparmor.py:558`) precisely so a reused slot can `aa_change_profile` from `jaato-ws-{S(N)}` to `jaato-ws-{S(N+1)}` on the next session's bootstrap re-entry; the daemon then unloads the old profile. The `//child` sub-profile does **not** inherit this rule — only the runner main thread can cross profile boundaries, never the LLM-driven scope.

**Risk/constraint:** the transition space is closed — every `jaato-ws-*` profile is framework-composed from the per-session template, so no operator-untrusted profile matches the glob.

**Shipped status (the `runner-cascade-sharing.md` §4.4 "Phase 0" header is stale — verify against code, not the header):**
- Pre-warm pool routing (claim a slot, self-confine via step 1c, unconfined → S1) is **shipped** (`JAATO_RUNNER_POOL_ENABLED=true` default; see `runner_prewarm_pool_plan.md`).
- Per-**cascade** slot affinity is **shipped** — `acquire_slot(cascade_driver_id=...)` is the Phase-2 affinity-aware path (`runner_pool.py:284`).
- Cross-session slot **reuse** across same-cascade sessions is **shipped** — a "Phase 3 cascade-sharing hotfix (server 0.6.150+, PR #173)" reuses the returned slot's `RunnerRPCClient` and clears per-session state via `reset_for_slot_reuse` (`runner_spawn.py:280-312`); covered by `test_pool_cascade_sharing.py`, `test_rpc_client_slot_reuse.py`, `test_cascade_teardown_e2e.py`.
- The cross-session **AppArmor re-confine** on a reused slot (`aa_change_profile` from `jaato-ws-{S(N)}` → `jaato-ws-{S(N+1)}`) has its enabling rule shipped in the template (`change_profile -> jaato-ws-*`, template v28), and bootstrap step 1c does `aa_change_profile` on a fresh confine — but I did **not** confirm from source that the *reuse* path re-runs that step per session (the reuse code above reuses the RPC client and resets state without a visible re-confine call). *This one sub-claim is being verified with the cascade owners (kb-orchestrator / advisor); treat it as "enabling rule shipped, per-reuse re-confine unconfirmed" until then.*

`shape3_workspace_state_relocation_plan.md` is adjacent: it concluded that workspace `.env` reading + secret-URI resolution **stay daemon-side permanently** (a runner-side attempt was reverted because secret resolution can't run under confinement); resolved env reaches the runner via `SessionInitEnvelope.session_env`.

## Relationship 2 — Workspace ↔ AppArmor rules

The profile is *generated to the workspace path*: `_render_profile` substitutes `{workspace_path}` into the base body, the `tool_hat` sub-profile (`_build_tool_hat_subprofile`), and the `child` sub-profile (`_build_child_subprofile`) (`apparmor.py:2103-2119`). The runner **self-confines** to it at bootstrap rather than the daemon confining the runner — `confine_to_profile` writes the change-profile transition and then reads back `/proc/self/attr/current` to verify (`bootstrap.py:188`). Isolation is the kernel's job: only `{workspace_path}/` is in the allow list, so any sibling session's path is denied by default. Reference paths *outside* the workspace can be granted read-only at runtime: `add_reference_fragment(session_id, ref_id, path)` (`apparmor.py:1687`) writes a bare-rule file into `…/jaato-ws-{session_id}.refs.d/`, which the profile's `include if exists` directive (`apparmor.py:569`) splices in on reload.

## Relationship 3 — Custom AppArmor rules of the cascade

A cascade/profile contributes its **own** fragments through `SubagentProfile.apparmor_fragments` (`subagent/config.py:1093`). This is a list of fragment basenames resolved at render time against three search tiers — user `~/.jaato/apparmor-fragments/`, workspace `<workspace>/.jaato/apparmor-fragments/`, and the walker-generated cache `<workspace>/.jaato/.cache/apparmor-fragments/` (cache wins on collision) — by `_render_profile` (`apparmor.py:1967-2042`). The semantics are deliberate for least-privilege: `None` = compose **all** fragments (back-compat); `[]` = compose **none** (maximally locked-down stage); a list = compose **only** those. Inheritance for this field is **child-replaces-parent** (not union) so a cascade stage can scope *down* (`subagent/config.py:1079-1087`). This pairs with template v18's decision that in `//child` the `apparmor_fragments` are the **sole** source of exec authority — the broad `/usr/bin/** ix` grants are intentionally absent there (`apparmor.py:2352-2397`), so a stage with `apparmor_fragments: [host_validator]` can exec only the binaries that fragment declares.

Cascade runner *sharing* interacts with this by keeping AppArmor **per-session, not per-cascade** — each session in a shared-runner cascade still carries its own composed profile and its own fragment set (`runner-cascade-sharing.md` §4.4; the doc's "Phase 0" header is stale — slot affinity/reuse shipped at server 0.6.150+, per-reuse re-confine being verified).

## Relationship 4 — Default AppArmor rules provided by each plugin

Plugins ship their *default* fragments via an optional `get_apparmor_rules` classmethod. At session spawn the daemon walks `profile.plugins`, looks each up in the registry, calls `get_apparmor_rules(workspace_path=…, session_id=…, config_root=…)`, and unions the returned rule strings — `resolve_plugin_apparmor_rules` (`apparmor.py:2516-2570`). A failing plugin is logged but does not abort the session. The unioned list arrives as `plugin_rules` and is spliced into the `{plugin_contributed_rules}` placeholder of the base profile **and** both sub-profiles (`apparmor.py:2049-2054`, `2114`); when empty it renders a greppable `(none for this session)` marker (`apparmor.py:1876`). A separate RPC path, `apparmor.add_reference_fragment` (`runner_rpc_handlers/apparmor_fragment.py`), lets the runner-side `references` plugin request a runtime read grant; validation runs **daemon-side** because the LLM-driven, confined runner cannot be trusted to validate paths it loads (`apparmor_fragment.py:9-20`, `:124-137`).

Why plugins ship fragments — concrete examples (verbatim rule text):
- **file_edit** — needs workspace-tier backup write: `{config_root}/sessions/ rw,` + `{config_root}/sessions/** rw,` (and optional operator `backup_dir`). (Migrated out of the base template into the plugin.)
- **memory** — needs the user memory store: `@{HOME}/.jaato/memories/ rw,`, `@{HOME}/.jaato/memories/** rw,`, `@{HOME}/.jaato/memories.jsonl rw,`.
- **references** — needs ML model caches with lockfiles: `@{HOME}/.cache/huggingface/** rwk,` and `@{HOME}/.cache/torch/** rwk,` (the `k` is the file-lock joblib uses), plus `@{HOME}/.jaato/references/** r,` for the catalog.
- **prompt_library** — read-only discovery across prompts/skills/agents and Claude Code interop: `@{HOME}/.jaato/prompts/** r,`, `@{HOME}/.jaato/skills/** r,`, `@{HOME}/.claude/skills/** r,`, `@{HOME}/.claude/commands/** r,`.
- **service_connector** — read-only service definitions: `@{HOME}/.jaato/services/ r,` + `@{HOME}/.jaato/services/** r,`.
- **lsp** — diagnostic-log write + per-server-binary `ix` exec (e.g. jdtls) + operator `apparmor_extra_rules`.

*(Note: exact line numbers for the per-plugin `get_apparmor_rules` bodies were reported by a search pass, not all re-read in this doc; the rule text above is grounded in those reports and in the template's own migration comments, e.g. `apparmor.py:386-404`, which name memory/prompt_library/references as the plugins that took over those previously-hardcoded paths. The plugin-contribution mechanism itself is design-staged in `plugin-apparmor-contribution.md` but the hook (template v20) and several migrations (v21–v26) are shipped per the `_TEMPLATE_VERSION` history.)*

**Composition — how it all becomes one enforced profile.** The final `jaato-ws-{session_id}` profile is the union of: (a) the **base/workspace rules** (`{workspace_path}/ rwkl`, system/venv reads, transitions, integrity denies) from `PROFILE_TEMPLATE`; (b) **per-plugin default fragments** from `resolve_plugin_apparmor_rules` spliced at `{plugin_contributed_rules}`; and (c) **cascade/profile custom fragments** from `apparmor_fragments`, inlined at `{extension_fragments_inline}`. AppArmor semantics make composition order-insensitive (allow rules union, deny rules union, deny wins at equal specificity). The runner then self-confines to this one composed profile.

## Configuration / authoring

In a profile JSON (`.jaato/profiles/<name>.json`, schema = `SubagentProfile`):
```json
{
  "name": "codegen",
  "plugins": ["cli", "file_edit", "lsp", "memory"],
  "apparmor": true,
  "apparmor_fragments": ["host_validator"]
}
```
- `apparmor: true` opts the session into kernel confinement (`subagent/config.py:1025`; default `false` until the planned PR-B flip).
- `apparmor_fragments: ["host_validator"]` composes *only* `host_validator.rules` from the search path; `[]` composes none; omitting the key composes all (`subagent/config.py:1093`).
- Operator-authored fragments live at `<workspace>/.jaato/apparmor-fragments/*.rules` or `~/.jaato/apparmor-fragments/*.rules`. Confined sessions cannot write there — `audit deny {workspace_path}/.jaato/apparmor-fragments/** wlk` (`apparmor.py:336`) blocks a confined runner from authoring its own future-session rules.

## Example

A `codegen` cascade stage spawns on workspace `/srv/work/sessions/20260615_codegen`. The daemon renders `jaato-ws-20260615_codegen`: base rules grant `/srv/work/sessions/20260615_codegen/** rwkl`; `file_edit` + `memory` contribute `@{HOME}/.jaato/sessions/** rw` and `@{HOME}/.jaato/memories/** rw`; the profile's `apparmor_fragments: [host_validator]` inlines `/usr/bin/java ix, /usr/bin/mvn ix`. The runner self-confines to this profile. When the agent runs `mvn package`, the cli plugin forks and the child transitions into `//child` — which grants only the fragment-declared `java`/`mvn` (no broad `/usr/bin/** ix`), so an improvised `curl` is kernel-denied. A sibling session at `…/20260615_review` is denied by default — its path was never in this profile's allow list.

## Diagram brief (for illustration)

- **Layout:** hub-and-spoke. A central rounded box labeled **"Workspace `/…/sessions/{session_id}/`"** sits in the middle. Three contributor boxes feed a composition node; the composed profile wraps a runner.
- **Boxes:**
  - Center hub: **Workspace** (the per-session working root) — highlighted/emphasized.
  - Contributor 1 (top-left): **Base / workspace rules** — sub-label "`{workspace_path}/** rwkl` + system/venv reads + integrity denies (PROFILE_TEMPLATE)".
  - Contributor 2 (left): **Per-plugin default fragments** — sub-label "`get_apparmor_rules()` → file_edit, memory, references, lsp, prompt_library, service_connector".
  - Contributor 3 (bottom-left): **Cascade / profile custom fragments** — sub-label "`SubagentProfile.apparmor_fragments` (user / workspace / cache tiers)".
  - Composition node (center-right): **Composed profile `jaato-ws-{session_id}`** (a shield icon), containing three nested rectangles labeled **base**, **`//tool_hat`**, **`//child`**.
  - Wrapped node (far right): **Runner process** — a box with a smaller inner box "warm pool slot (reused)" and a cwd tag pointing back at the Workspace hub.
- **Arrows:**
  - Contributor 1 → Composition node, edge label "base body".
  - Contributor 2 → Composition node, edge label "splice `{plugin_contributed_rules}`".
  - Contributor 3 → Composition node, edge label "inline `{extension_fragments_inline}`".
  - Workspace hub → Composition node, edge label "`{workspace_path}` substitution".
  - Composition node → Runner, edge label "self-confine: `aa_change_profile` (bootstrap step 1c)".
  - A curved dashed arrow from Runner looping back to itself, label "reuse: S(N) → S(N+1) via `change_profile -> jaato-ws-*` (slot reuse shipped 0.6.150+; per-reuse re-confine being verified)".
  - Workspace hub → Runner, edge label "cwd + `set_workspace_path` broadcast".
  - A faded sibling box "other session's workspace" with a red ✕ arrow from Runner, label "default-deny".
- **Emphasis:** the central **Workspace** box (bold border, accent fill) and the **Composed profile** shield. Make the "three contributors → one profile" funnel the visual focus.
- **Caption:** "One workspace, one composed AppArmor profile: base + plugin defaults + cascade fragments wrap a runner that may be a reused warm slot."

## Source references
- `jaato-server/shared/session_envelope.py:83-86` — `SessionInitEnvelope.session_id`/`workspace_path`; profile name = `jaato-ws-{session_id}`.
- `jaato-server/shared/plugins/registry.py:1347-1368` — `set_workspace_path` broadcast to plugins.
- `jaato-server/shared/config_resolver.py:121-122,170` — workspace-tier `.jaato/` config lookup.
- `jaato-server/server/apparmor.py:318-336` — workspace rw rule + `.jaato/` integrity denies (no sibling deny: `:413-417`).
- `jaato-server/server/apparmor.py:545-558` — `change_profile -> unconfined` / `//child` / `jaato-ws-*` (v28 cascade-sharing rule).
- `jaato-server/server/apparmor.py:1883-2042,2049-2119` — `_render_profile`: fragment search tiers + plugin/cascade/base composition.
- `jaato-server/server/apparmor.py:2516-2570` — `resolve_plugin_apparmor_rules` (walks `profile.plugins` → unions `get_apparmor_rules`).
- `jaato-server/server/apparmor.py:1687-1767` — `add_reference_fragment` runtime read grant; RPC handler in `runner_rpc_handlers/apparmor_fragment.py:84-163`.
- `jaato-server/shared/plugins/subagent/config.py:1025,1093` — `apparmor` opt-in + `apparmor_fragments` (child-replaces-parent).
- `jaato-server/server/runner/bootstrap.py:123-188` — `confine_to_profile` / `aa_change_profile` self-confine + verify (step 1c).
- Design docs (status markers): `docs/runner-cascade-sharing.md` §4.4 (header reads "Phase 0" but is **stale** — slot affinity `runner_pool.py:284` + reuse `runner_spawn.py:280` shipped at server 0.6.150+ with tests; per-reuse AppArmor re-confine being verified with cascade owners); `docs/design/shape3_workspace_state_relocation_plan.md` (workspace `.env` reading stays daemon-side — **decided/shipped**); `docs/design/plugin-apparmor-contribution.md` (hook v20 shipped, full migration staged); `docs/design/phase5_5_10_apparmor_child_subprofile_audit.md` (`//child` escape closure — shipped per template v14–v15).
