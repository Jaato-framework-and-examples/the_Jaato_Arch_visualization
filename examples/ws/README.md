# examples/ws — runnable raw-WebSocket-frame examples

The jaato daemon speaks the same wire protocol over WebSocket as over IPC. These
are the **raw-frame** examples from `platform-comparisons/ona.md` — one tiny
node ws-client script per frame sequence, sending the exact JSON frames the doc
shows and reading the daemon's reply frames. No SDK, no build: just node's global
`WebSocket` (Node ≥ 22).

Connects to the **same dedicated daemon** as the SDK surfaces (WS `:8099`).

## Run

```bash
(cd ../python-sdk && ./daemon.sh start)   # shared dedicated daemon (serves WS :8099)
./run.sh ex1_basic_session.mjs            # run one example
./run.sh smoke.mjs                        # run all, assert the working core
```

`run.sh` sets `NODE_EXTRA_CA_CERTS=$HOME/.jaato/certs/ca.crt` so node trusts the
daemon's self-signed Jaato Dev CA for `wss://`. The bearer token is read from
`~/.jaato/ws.token`. No secret committed.

## Frame sequence → docs map

| File | Frame sequence | ona.md |
|---|---|---|
| `ex1_basic_session.mjs` | connect → `session.new` → `message.send` → `agent.output`/`turn.completed` | §1 |
| `ex2_attach_replay.mjs` | detach → `session.attach` (replay) | §2 |
| `ex3_attach_followup.mjs` | `session.attach` → `message.send` (continue) | §3 |
| `ex4_lifecycle.mjs` | `session.list` / `session.stop` / `session.end` | §4 |

The wire frames (`connect` greeting, `command.execute`/`session.new`,
`message.send`, `agent.output`, `turn.completed`, `session.attach`,
`session.stop {agent_id:null}`, `session.end`/`session.list`) are reproduced
verbatim from the doc; each file's header shows the doc snippet alongside.

## Standing substitutions

- **`wss://localhost:8099/?token=…`** — the dedicated daemon (the doc shows
  `:8080`/`:8089`); token from `~/.jaato/ws.token`.
- **Inline session spec in `payload.spec`** — the doc shows `session.new
  --profile backend`; the runnable uses an inline spec (model/provider + the
  `pass:` credential knob) so it works against a fresh daemon with no
  pre-installed `backend` profile. (Provider = `openrouter`,
  model = `google/gemini-2.5-flash`.)

## Findings

- **ex1 + ex4 are e2e-green** — the basic round-trip and the lifecycle frames
  (`session.list` → a session list, `session.stop`, `session.end`) work.
- **Raw `session.attach` (ex2/ex3) doesn't behave as ona.md §2/§3 shows on this
  build** (triaged with the framework owner):
  - **ex2 — no replay (by design on this path).** The daemon deliberately skips
    re-emitting state on this attach path, so "raw attach replays prior turns" is
    aspirational for the raw-frame path — not a bug to wait on.
  - **ex3 — send-after-reattach isn't processed (a real readiness gap, flagged,
    non-blocking).** The connection's session *is* set and the send reaches the
    reloaded session, but the restored session doesn't start a turn on it (a
    re-attach-readiness gap, #413-flavour). The session persists (it appears in
    `session.list`); the gap is the send→turn start on a restored session.

  ex2/ex3 send the correct doc frames and report the observed behaviour (bounded
  so they never hang); the smoke runs them as informational.
