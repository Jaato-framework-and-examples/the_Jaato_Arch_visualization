# examples/ts-sdk — runnable TypeScript `@jaato/sdk` (WebSocket) examples

One canonical, **buildable, end-to-end-tested** file per jaato example, mirroring
the TypeScript jaato snippets in `sdk-comparisons/mastra.md`. The TS SDK speaks
**WebSocket** to the daemon; each example reproduces the doc's `JaatoClient.session`
call shape **1:1**, with the few documented substitutions below.

These connect to the **same dedicated daemon** as `examples/python-sdk` (it serves
both the IPC socket and the WS port `:8099`).

## Build & run

```bash
(cd ../python-sdk && ./daemon.sh start)   # shared dedicated daemon (IPC + WS :8099)
./setup.sh                                # vendor the local @jaato/sdk, npm install, tsc
./run.sh src/ex01_basic_ask.ts            # run one example
./run.sh src/smoke.ts                     # run every example, assert green
```

`run.sh` sets `NODE_EXTRA_CA_CERTS=$HOME/.jaato/certs/ca.crt` so Node trusts the
daemon's self-signed **Jaato Dev CA** for the `wss://` connection (the clean way —
no disabling TLS verification). The bearer token is read from the daemon's
`~/.jaato/ws.token`. No secret is committed.

## Example → docs map

Each file maps to `mastra.md` (the TypeScript jaato side); the Python `§N` maps to
`examples/python-sdk/exNN_*.py`.

| File | Example | mastra.md |
|---|---|---|
| `ex01_basic_ask.ts` | Hello world — `JaatoClient.session` + `s.ask`, and module `ask()` | §1 |
| `ex02_streaming.ts` | Streaming — `s.stream` | §2 |
| `ex03_persona_memory.ts` | Persona + session memory — `agent:"pirate"`, two `s.ask` | §3 |
| `ex04_typed_completion.ts` | Typed completion gate — `profile:"person-extractor"`, `s.complete` | §4 |
| `ex05_client_tool.ts` | Client/host tool — `clientTools:[…]` | §5 |
| `ex06_multitool.ts` | Multi-tool loop — server-side `plugins:[…]` | §6 |
| `ex07_permissions.ts` | HITL approval — `onPermission` | §7 |
| `ex08_subagent.ts` | Subagent delegation — `agent:"lead"`, `plugins:["subagent"]`, event API | §8 |
| `ex09_cascade.ts` (+ shared `.jaato/`) | Reactor-driven cascade — `cascadeDriverId` | §9 |
| `ex10_recovery.ts` | Recovery — `recovery:{}` + `onStatusChange` | §10 |

## Standing substitutions from the doc snippets

1. **`...CONN`** — connection (`url`, `token`) from `_config.ts`, pointing at the
   dedicated daemon's WS endpoint. The doc shows `url` only.
2. **`...AUTH`** — the provider's `pass:` credential knob
   (`plugin_configs.openrouter.api_key`), spread into inline profiles; declarative
   profiles carry it in their JSON. (Project convention: creds via `pass:` knobs,
   never env vars.)
3. **OpenRouter model/provider** — `{model:"google/gemini-2.5-flash",
   provider:"openrouter"}` in place of the docs' `{model:"gpt-4o",
   provider:"openai"}`.
4. **explicit `plugins`** — the daemon requires a `plugins` key on an inline spec.
5. **`configRoot` on declarative examples** (ex03/04/08/09) — see the first finding.

## Findings (surfaced by running the docs e2e against the WS transport)

- **WS facade race (fixed upstream, PR #417).** `JaatoClient.session()` threw "no
  session id" — `openSession` checked `sessionId` immediately after the
  fire-and-forget `createSession`, before the async `SessionInfoEvent` set it
  (~2s for a cold session). Fixed by waiting for `SessionInfoEvent` (the TS analog
  of Python's `create_session` wait). Requires `@jaato/sdk` ≥ that fix.
- **WS declarative resolution needs `configRoot`.** Unlike the IPC client, a WS
  client gets an auto-provisioned per-session workspace, and the daemon resolves
  declarative assets (profiles/agents) from *that* workspace's `.jaato` — not from
  `workspacePath`. So the declarative examples pass `configRoot` at this project's
  `.jaato` so `agent:"pirate"` / `profile:"person-extractor"` resolve.
- **WS file ops are sandboxed.** ex06's `cli` writes `report.txt` into the WS
  session's auto-provisioned workspace (correct isolation), not this project dir —
  so the example asserts on the model's output, not a local file.
- **ex06 / ex07 / ex08 model behaviour** (same daemon + model as python-sdk):
  file_edit's PR-146 init bug → file work via `cli`; "delete temp.log" / "plan a
  trip" are flaky loop triggers → tool-requiring tasks + a permission policy; and
  **`gemini-2.5-flash` tends not to call `spawn_subagent`** (ex08), so the
  delegation is fully wired but whether the lead actually delegates is
  model-dependent (a stronger agentic model delegates reliably).
- **ex09 cascade** — the `.jaato/` reactor + scripts are identical to python-sdk
  (daemon-side); real cross-stage data flow needs the typed-payload hoist
  (jaato PR #414, on main).
