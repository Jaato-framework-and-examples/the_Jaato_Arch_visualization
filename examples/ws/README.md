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
- **`session.attach` works for a WARM reattach; ex2/ex3 do a COLD reattach, which
  currently races** (triaged with the framework owner). `session.attach` *does*
  replay history and accept follow-up sends when the session is still loaded
  (warm). ex2/ex3 close the socket first — which **unloads** the session — then
  attach by id (disk-restored = **cold**). On the cold path the runner re-spawns
  asynchronously, so two things race the restore: the replay history may not be
  populated when state is emitted → **no replay frames** (ex2), and the restored
  session may not be turn-ready when the follow-up lands → **the send starts no
  turn** (ex3). Both share one root — the cold-reattach readiness race — flagged
  upstream as a real gap on the unloaded→restored path (non-blocking). The session
  *does* persist (it appears in `session.list`). ex2/ex3 send the correct doc
  frames and report the observed behaviour (bounded so they never hang); the smoke
  runs them as informational.
