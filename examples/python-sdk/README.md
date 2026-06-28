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

## Findings (surfaced by running the docs e2e — flagged, not papered over)

- **Inline spec requires `plugins`.** The docs' concise `profile={"model","provider"}`
  is rejected (`InvalidSessionSpec`); examples add `"plugins": []`.
- **ex10 — facade × `IPCRecoveryClient` hang.** The doc's bare `await s.ask()` on a
  recovery client hangs (the recovery client ran no background event pump). Fixed
  upstream in jaato **PR #412** (recovery background pump + `workspace_path` `Path`
  coerce). `ex10` keeps a commented `events()` pump until the fix is in the
  installed build, then runs the doc-verbatim three lines.
- **ex08 — subagent example can't terminate as written.** The prose says the lead
  must be completion-gated, but the doc's inline profile omits the
  `completion_payload_schema` that exposes `signal_completion`. `ex08` adds the
  gate (a `blurb` schema).
- **ex09 — `read_cascade_driver_id` is wrong.** The doc's helper (and its "from
  workspace cascade_state" comment) is pseudocode; the real cid is read from the
  managed session record via `ctx.session_manager.get_session(ctx.session_id)`.
  `spawn_summarize.py` uses the real mechanism.
- **ex09 — `reactors.json` requires `"version": 1`.** The doc's reactor snippet
  omits it; without it the rule file fails to load (`Unsupported reactors.json
  version: None`) and the cascade never fires.
- **ex09 — typed-payload handoff drops the payload (under investigation).** The
  cascade *structure* works (the reactor fires and spawns the gated next stage,
  decoupled), but the validated `signal_completion` payload isn't surfaced to the
  reactor script: `event.get("facts")` returns `None` even though the extract
  stage emitted a correct `{"facts": …}` payload. The access pattern is correct
  (verified against `build_merged_view`); the delivered `agent.completed` event
  carries the envelope fields but not `payload`. Flagged upstream.
- **ex03 — client-driven multi-turn deadlocks (pending upstream fix).** Any two
  sequential `s.ask` on one session hang on turn 2: the daemon emits
  `TURN_COMPLETED` before clearing `_model_running`, so turn 2's send hits the
  "still running" gate, is forwarded as an inject onto an idle session with no
  drainer, and queues forever. Root-caused with a diagnostic trace (not ws/agent/
  reactor — a core runner-tier race). Held PENDING in `smoke.py` (not an example
  defect); ex03 is the only example doing two client-driven asks.
- **ex06 — the autonomous loop needs daemon-side config the docs omit.** jaato
  gates file/cli tools by default (set `permission.policy.defaultPolicy:"allow"`),
  and `file_edit` fails to initialise on this build — it can't resolve its backup
  dir before init, and `config_root` / `plugin_configs.file_edit.backup_dir` are
  applied too late (framework PR-146 init-ordering). So file_edit is dropped and
  the agent saves via `cli`. (`web_search` is kept — it uses `ddgs`/DuckDuckGo,
  no API key, and works with network access.) See the file header.

## The dedicated daemon

`daemon.sh` runs an isolated daemon (`/tmp/jaato-examples.sock`, ws `:8099`, own
pid/log). Provider = `openrouter` (`google/gemini-2.5-flash`), creds via the profiles'
`pass:` knob. Note: a dedicated daemon still inherits **home-global** reactors
from `~/.jaato/reactors/` — a completion reactor there can deadlock client-driven
multi-turn (see the repo findings); keep that dir clean for these examples.
