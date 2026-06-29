# examples/python-sdk — runnable, deduplicated jaato-sdk (IPC) examples

One canonical, **buildable, end-to-end-tested** file per jaato example, mirroring
the jaato-sdk code blocks that repeat across the comparison docs in this repo.
Each file reproduces the doc's SDK call shape **1:1**; the differences are the few
documented, load-bearing substitutions listed below.

The Python SDK speaks **IPC** (a local Unix socket) to a long-lived daemon. These
examples run against a **dedicated** OpenRouter daemon (its own socket/port/pid/log)
so it won't collide with any other jaato daemon on the host.

## Build & run

```bash
./setup.sh            # venv + `pip install -e` the local jaato-sdk
./daemon.sh start     # dedicated daemon: /tmp/jaato-examples.sock + ws :8099
./.venv/bin/python ex01_basic_ask.py
./.venv/bin/python smoke.py     # run every example, assert green
./daemon.sh stop
```

Provider auth is **not** an env var or a tracked secret — the `openrouter`
credential is a `pass:` resolver knob of the provider plugin
(`plugin_configs.openrouter.api_key = "pass://jaato/openrouter/api-key"`), which
the daemon resolves from the password store at session creation. Inline-spec
examples spread it via `_config.AUTH`; declarative profiles carry it in their
JSON. `.env` only names the provider + model. (`jaato-scaffold explain provider
openrouter` / `explain profile` document the credential resolver.)

## Example → docs map

Each file maps to the doc sections it appears in. **Canonical source =
`pydantic-ai.md`** (the majority form, byte-identical in `agno.md`,
`claude-agent.md`, `openai-agents.md`, `strands.md`); `langchain.md` is the
*outlier* on ex05/ex07/ex10 (named functions instead of inline lambdas) — noted
per-file. `mastra.md` carries the TypeScript versions (→ `examples/ts-sdk`).

| File | Example | Appears in (SDK docs §) |
|---|---|---|
| `ex01_basic_ask.py` | Hello world — `IPCClient.session` + `s.ask`, and the module `ask()` | langchain §1, pydantic-ai §1, agno §1, claude-agent §1, openai-agents §1, strands §1 |
| `ex02_streaming.py` | Streaming — `s.stream` | …§2 (all six) |
| `ex03_persona_memory.py` | Persona + session-as-memory — `agent="pirate"`, two `s.ask` | …§3 (all six) |
| `ex04_typed_completion.py` | Typed completion gate — `profile="person-extractor"`, `s.complete` | …§4 (all six) |
| `ex05_client_tool.py` | Client/host tool — `client_tools=[…]` | …§5 (all six; langchain uses a named fn) |
| `ex06_multitool.py` | Multi-tool loop — server-side `plugins=[…]` | …§6 (all six) |
| `ex07_permissions.py` | HITL approval — `on_permission` | …§7 (all six; langchain uses a named fn + `input()`) |
| `ex08_subagent.py` | Subagent delegation — `agent="lead"`, `plugins=["subagent"]`, event API | …§8 (all six) |
| `ex09_cascade.py` (+ `.jaato/reactors/cascade.json`, `.jaato/scripts/spawn_summarize.py`) | Reactor-driven cascade — `cascade_driver_id` | …§9 (all six; jsonc+py halves byte-identical) |
| `ex10_recovery.py` | Recovery client — `IPCRecoveryClient` | …§10 (all six; langchain uses `on_status_change=print`) |

The platform docs (`ona.md`, `kiro.md`, `intent.md`) carry no ex01–ex10; their
raw-WS-frame / CLI / YAML snippets belong to `examples/ws` (and are not duplicated
here).

## Standing substitutions from the doc snippets

Applied uniformly so the examples actually round-trip; everything else is the doc
verbatim. Each file's header repeats the doc snippet for side-by-side comparison.

1. **`**CONN`** — harness connection kwargs (`socket_path`, `env_file`) from
   `_config.py`, pointing at the dedicated daemon. The docs assume the default
   daemon; this is the minimal retarget. Declarative examples (ex03/04/08/09) also
   pass `workspace_path=WORKSPACE` so the daemon resolves `./.jaato/` assets.
2. **`**AUTH`** — the provider's `pass:` credential knob
   (`plugin_configs.openrouter.api_key`), spread into inline specs from
   `_config.AUTH`. The docs assume an ambient `OPENAI_API_KEY`; OpenRouter auth is
   a profile knob (project convention: credentials via `pass:` knobs, never env
   vars). Declarative
   examples carry the same knob in their profile JSON instead.
3. **OpenRouter model/provider** — `{"model": "google/gemini-2.5-flash",
   "provider": "openrouter"}` in place of the docs' `{"model": "gpt-4o",
   "provider": "openai"}` (a cheap model with reliable tool-calling + completion
   gates, which the tool examples ex05–ex09 lean on). For declarative examples the
   model/provider live in the profile JSON instead.
4. **explicit `plugins`** — *not a deviation, the correct form.* The installed
   daemon **requires** a `plugins` key on an inline session spec (absent ≠ `[]` ≠
   `[set]` is deliberate); the doc snippets omit it. Tool-less examples use
   `"plugins": []`.

## Deviations from the docs

- **Inline spec requires `plugins`.** The docs' concise `profile={"model","provider"}`
  is rejected (`InvalidSessionSpec`); examples add `"plugins": []`.
- **ex08 — the subagent lead must be completion-gated.** The prose says the lead
  must be completion-gated, but the doc's inline profile omits the
  `completion_payload_schema` that exposes `signal_completion`. `ex08` adds the
  gate (a `blurb` schema).
- **ex09 — `read_cascade_driver_id` is pseudocode.** The doc's helper (and its
  "from workspace cascade_state" comment) is illustrative; the real cid is read
  from the managed session record via
  `ctx.session_manager.get_session(ctx.session_id)`. `spawn_summarize.py` uses the
  real mechanism.
- **ex09 — `reactors.json` requires `"version": 1`.** The doc's reactor snippet
  omits it; without it the rule file fails to load (`Unsupported reactors.json
  version: None`) and the cascade never fires.
- **ex09 — typed-payload handoff needs a schema on the producer.** The cascade is
  the full 3-stage chain extract → summarise → verify (the comparison §9 shows the
  2-stage illustration). `event.get(<field>)` is the typed-handoff pattern and
  needs both: (1) a `completion_payload_schema` with that top-level field on the
  **producer** profile (so `signal_completion(field=…)` attaches a validated typed
  payload) — `extract.json`→`facts`, `summarize.json`→`summary`,
  `verify.json`→`verdict`; and (2) the server hoists that typed payload onto the
  bus event the reactor receives. End-to-end: summarise gets the real facts,
  verify the real summary (verdict "pass").
- **ex06 — the autonomous loop needs daemon-side config + a tool-requiring task.**
  jaato gates file/cli tools by default (set `permission.policy.defaultPolicy:
  "allow"`), and `file_edit` is dropped (its backup dir can't resolve before
  init), so file work goes via `cli`. The doc's vague "plan a trip and save it" is
  a flaky loop trigger (a model may ask for clarification — which errors headless —
  or just print the answer instead of saving it), so the example uses a task that
  *requires* tool output (real date + dir listing → `report.txt`). See the file
  header.

## The dedicated daemon

`daemon.sh` runs an isolated daemon (`/tmp/jaato-examples.sock`, ws `:8099`, own
pid/log). Provider = `openrouter` (`google/gemini-2.5-flash`), creds via the profiles'
`pass:` knob. Note: a dedicated daemon still inherits **home-global** reactors
from `~/.jaato/reactors/` — a stray completion reactor there can interfere with
these examples' cascades, so keep that dir clean.
