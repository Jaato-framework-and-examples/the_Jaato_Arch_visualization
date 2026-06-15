# Persona Pre-fetch Scripts

> **A Python script bound to a persona that the framework runs at session bootstrap to gather context (service calls, memory snapshots, forwarded case data) and inject the result directly into the agent's system prompt — before the agent's first turn.**
> **Layer (bottom→top):** input-boundary mechanism attached to a Persona; sits between the spawn payload (what the caller passes in) and the assembled system instructions (what the agent reads). · **Lives in:** PUBLIC `jaato/jaato-server/shared/dynamic_instructions.py`, `jaato/jaato-server/shared/script_loader.py`, `jaato/jaato-server/shared/spawn_schema_loader.py`; authored under `<workspace>/.jaato/scripts/`.

## What it is

A jaato persona is a Markdown template (`.jaato/agents/<name>.md`). A pre-fetch script is a small Python file the persona references with a placeholder — `{{!py:scripts/prefetch_<x>.py}}` — that the framework expands while building that persona's system prompt. The script's job is to *gather context the agent would otherwise have to fetch itself*: call an external service, read a memory snapshot, pull ledger usage, or reformat data the supervisor forwarded on the spawn call.

The motivating principle (subagent `README.md:558-565`) is to move mandatory work from "soul-driven" (a tool the model must remember to call) to "body-wired" (framework execution the model can't skip). When a service call has only one acceptable answer under every valid persona choice, the framework makes it for the agent and embeds the structured response in the prompt. The agent sees the result as input data already present, not as a choice — though it retains the *capability* to call the tool directly; only the *requirement* is removed (`README.md:708-714`).

Pre-fetch is the **input-side** counterpart to completion artifacts/processors (the output boundary). Inputs are body-fetched on the way in; the model's `signal_completion` payload is the judgment it uniquely produces in the middle; outputs are body-rendered on the way out (`README.md:566-571`).

## Where it sits in the stack

Directly **below** a pre-fetch script is the **Persona** that declares it (the `.md` template) and the **Spawn payload** (`agent_params`) the caller passed via `spawn_subagent(...)`. Directly **above** it is the **assembled system instruction** that the script's output is injected into — the prompt the model reads on turn one. Sideways, the script talks to whatever a tool could: the `PluginRegistry` (e.g. `registry.get_plugin("service_connector")`), the `JaatoRuntime`, and the workspace filesystem. Its counterpart on the opposite boundary is the **completion schema / completion artifacts** mechanism.

## Responsibilities

- Resolve a script reference to a real file via the standard `.jaato/` tier (`script_loader.resolve_script_path`).
- Load and execute the script's top-level `render(context, args) -> str` callable at session-configure time.
- Pass the script a `RenderContext` with handles to session, runtime, registry, workspace/config paths, `agent_params`, and an `os.environ` snapshot.
- Substitute the script's returned string into the system prompt in place of the placeholder.
- Enforce the strict-vs-best-effort error contract (`{{!py:}}` aborts session creation on failure; `{{!py?:}}` swallows and substitutes an error sentinel).
- Run under the session's AppArmor confinement when one is configured, so a script can't escape the persona's filesystem deny rules.

## Key concepts & structure

### The placeholder — `{{!py:script.py args}}`
Recognised by the regex `_PY_PLACEHOLDER` in `dynamic_instructions.py:68`: `\{\{!py(\?)?:([^\s}]+)(?:\s+([^}]*))?\}\}`. The path is everything up to the first whitespace; the rest are space-separated args. The optional `?` (server 0.6.48+) marks the placeholder best-effort.

### `render(context, args) -> str`
The required entry point. Scripts must define a top-level `def render(context, args)` (`dynamic_instructions.py:23`). The symbol is loaded by `load_script_symbol(path, symbol="render", module_prefix="_jaato_dynprompt")` (`dynamic_instructions.py:258-260`).

### `RenderContext`
Defined at `dynamic_instructions.py:107-180`. Fields the script reads: `session`, `runtime`, `registry`, `workspace_path`, `config_root`, `agent_params` (the dict forwarded by the supervisor), `env` (an `os.environ` snapshot), `logger`, `session_id`, and `tool_calls` (empty for input-side prefetch; populated only for completion processors).

### Resolution tier
`resolve_script_path` (`script_loader.py:241-287`) resolves a reference as: absolute path → workspace tier (`<config_root>/<path>`, else `<workspace>/.jaato/<path>`) → user tier (`~/.jaato/<path>`). `load_script_symbol` (`script_loader.py:290-368`) re-executes the script on every call so edits are picked up without a daemon restart, and tracks transitively-imported helpers under `.jaato/scripts/` for mtime-based reload.

## Lifecycle / flow

1. A caller spawns the persona: `spawn_subagent(profile=<name>, task=..., agent_params={...})`.
2. If the profile declares a `spawn_payload_schema`, the framework validates `agent_params` against it **before** creating the session (`spawn_schema_loader.py:1-9`) — missing required keys fail at the spawn boundary, not mid-cascade.
3. The session is created; `JaatoSession.configure()` assembles the system instruction from the persona template, with profile env (`JAATO_WORKSPACE_ROOT` / `JAATO_CONFIG_ROOT` / overlay) already pushed (`dynamic_instructions.py:33-38`).
4. If the assembled prompt contains `{{!py:` or `{{!py?:`, `configure()` builds a `RenderContext` and calls `expand_py_placeholders` (`jaato_session.py:2046-2071`). When a confine-context factory is set, the expansion runs inside the session's AppArmor confinement (`jaato_session.py:2063-2067`).
5. For each placeholder, `expand_py_placeholders` (`dynamic_instructions.py:183-306`) resolves the path, loads `render`, invokes `render(context, args)`, and substitutes the returned string.
6. The expansion is implicitly run-once — rendered a single time per session at configure time (`README.md:942`), before the agent's first turn.

## Configuration / authoring

Scripts live at `<workspace>/.jaato/scripts/<name>.py` (or `~/.jaato/scripts/`). The persona references them in `.jaato/agents/<name>.md`. The spawn schema that mirrors the script's required keys lives at `<config_root>/spawn_schemas/<name>.json` and is named in the profile via `spawn_payload_schema` (`README.md:871`).

**The mirroring rule** (`payload-schema-conventions.md:104-139`): if a persona body-wires a prefetch that reads keys from `context.agent_params`, the spawn schema's `required` array should **exactly mirror** the keys the prefetch needs. This closes the field-drop variance class (a 2026-05-01 load test saw 5/10 rejections because an upstream agent silently dropped forwarded fields). The schema's `description` should name the prefetch path so both are updated in the same diff (`payload-schema-conventions.md:157-163`). Spawn schemas default to `additionalProperties: true` for forward-compat with `agent_params`-mediated framework features like `continuity_scope` (`payload-schema-conventions.md:141-156`, §6).

**Error contract** (`dynamic_instructions.py:62-67`, `99-104`): `{{!py:}}` is strict by default (server 0.6.48+) — any failure (not found, load error, render raise, non-string return, or a return starting with a sentinel like `[prefetch error:`) raises `DynamicInstructionsError` and aborts session creation with a structured `ErrorEvent`. `{{!py?:}}` is best-effort: the same failures are swallowed and the error marker (`[script not found: ...]`, `[script load error: ...]`, `[script error: ...]`) is substituted into the prompt for the agent to reason about.

## Relationship to neighboring components

A pre-fetch script **belongs to a Persona** (the `.md` template references it) and **consumes the spawn payload** (`agent_params`) the caller forwarded. The **spawn schema** (`spawn_payload_schema`, resolved by `spawn_schema_loader.py`) guards the same boundary by validating that the caller supplied the keys the script needs — the two are intentionally kept in lockstep. On the far side of the agent, the **completion schema** (`completion_payload_schema`) and **completion artifacts** form the symmetric output boundary: prefetch is body-fetched input, completion artifacts are body-rendered output, and the model's structured `signal_completion` payload is the judgment in between (`README.md:933-944`).

## Example

`.jaato/agents/kyc_aml.md` (persona body, `README.md:619-633`):

```markdown
You are the KYC/AML agent.  The framework has already called both
external services on your behalf — interpret the responses below.

{{!py:scripts/prefetch_kyc_aml.py}}
```

`.jaato/scripts/prefetch_kyc_aml.py` (`README.md:635-659`):

```python
import json

def render(context, args):
    p = context.agent_params
    sc = context.registry.get_plugin("service_connector")
    kyc = sc._execute_call_service({
        "service": "kyc", "method": "POST", "path": "/v1/kyc/verify",
        "body": {"dni": p["tomador_dni"], "nombre": p["tomador_nombre"]},
    })
    aml = sc._execute_call_service({
        "service": "aml", "method": "POST", "path": "/v1/aml/screen",
        "body": {"dni": p["tomador_dni"]},
    })
    return (
        f"### KYC verify\n```json\n{json.dumps(kyc, indent=2)}\n```\n\n"
        f"### AML screen\n```json\n{json.dumps(aml, indent=2)}\n```"
    )
```

The supervisor passes the case fields via `agent_params` on the spawn (`README.md:666-677`), and the mirroring `spawn_schemas/kyc_aml.json` lists `tomador_dni` and `tomador_nombre` in `required`. At configure time the framework calls both services and embeds the responses in the prompt; the agent reads them as data already present and produces only the decision.

## Diagram brief (for illustration)

- **Layout:** Left-to-right horizontal flow with a highlighted middle stage. Three lanes top-to-bottom only for the "boundary" labels.
- **Boxes:**
  1. `Caller / Supervisor` (far left) — emits `spawn_subagent(profile, agent_params={...})`.
  2. `Spawn schema gate` (small diamond/box) — labeled `spawn_payload_schema · validates agent_params (spawn_schema_loader.py)`.
  3. `Persona (.jaato/agents/<name>.md)` — shows a code line `{{!py:scripts/prefetch_kyc_aml.py}}`.
  4. `Pre-fetch script (.jaato/scripts/prefetch_kyc_aml.py)` — labeled `render(context, args) -> str` — THE HIGHLIGHTED BOX.
  5. `RenderContext` (small box feeding the script) — labeled `agent_params · registry · runtime · workspace`.
  6. `External service / KB` (above the script) — labeled `service_connector → KYC / AML`.
  7. `Assembled System Prompt` — the prefetch output substituted in place of the placeholder.
  8. `Agent's first turn` (far right) — reads the prompt.
  9. Faint mirror box bottom-right: `Completion schema / artifacts (output boundary)` to show symmetry.
- **Arrows:**
  - `Caller` → `Spawn schema gate`, label `agent_params`.
  - `Spawn schema gate` → `Persona`, label `validated, session created`.
  - `Persona` → `Pre-fetch script`, label `{{!py:...}} placeholder expand (configure time)`.
  - `RenderContext` → `Pre-fetch script`, label `handles`.
  - `Pre-fetch script` ↔ `External service / KB`, label `call_service`.
  - `Pre-fetch script` → `Assembled System Prompt`, label `returns string → substituted`.
  - `Assembled System Prompt` → `Agent's first turn`, label `reads as input data`.
  - Dashed double-headed arrow between `Spawn schema gate` and `Pre-fetch script`, label `required keys MIRROR prefetch keys`.
  - Faint dashed arrow `Agent` → `Completion schema / artifacts`, label `symmetric output boundary`.
- **Emphasis:** Bold/colored border on box 4 (the pre-fetch script) and the dashed "MIRROR" arrow.
- **Caption:** "Pre-fetch scripts run at session bootstrap: the framework body-fetches context (service calls, forwarded case data) and injects it into the persona's prompt before the agent's first turn — its required keys mirror the spawn schema."

## Source references
- `jaato/jaato-server/shared/dynamic_instructions.py:1-39` — module purpose: input-side `{{!py:...}}` expansion, runs during `configure()` before first turn.
- `jaato/jaato-server/shared/dynamic_instructions.py:62-104,183-306` — placeholder regex, strict/best-effort `?` contract, failure sentinels, and the `expand_py_placeholders` substitution logic.
- `jaato/jaato-server/shared/dynamic_instructions.py:107-180` — `RenderContext` fields handed to `render` (`agent_params`, `registry`, `runtime`, `workspace_path`, etc.).
- `jaato/jaato-server/shared/script_loader.py:241-368` — `resolve_script_path` (`.jaato/` tier) and `load_script_symbol` (loads `render`, re-executes per call).
- `jaato/jaato-server/shared/jaato_session.py:2046-2071` — where `configure()` invokes expansion, optionally inside AppArmor confinement.
- `jaato/jaato-server/shared/spawn_schema_loader.py:1-9,38-107` — `spawn_payload_schema` validated before session creation; the input boundary that mirrors prefetch keys.
- `jaato/docs/design/payload-schema-conventions.md:104-163` — the mirroring rule: spawn schema `required` exactly mirrors the body-wired prefetch's keys.
- `jaato/jaato-server/shared/plugins/subagent/README.md:553-714,933-944` — body-wired pattern, the kyc_aml worked example, execution-context contract, and input/output symmetry table.
