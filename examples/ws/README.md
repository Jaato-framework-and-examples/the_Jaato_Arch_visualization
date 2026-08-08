# examples/ws — runnable raw-WebSocket-frame examples

The jaato daemon speaks the same wire protocol over WebSocket as over IPC. These
are the **raw-frame** examples from `platform-comparisons/ona.md` — one tiny
node ws-client script per frame sequence, sending the exact JSON frames the doc
shows and reading the daemon's reply frames. No SDK, no build: just node's global
`WebSocket` (Node ≥ 22).

Connects to the **same dedicated daemon** as the SDK surfaces (WS `:8099`).

## Run

```bash
export JAATO_OPENROUTER_API_KEY=sk-or-...  # provider key; inherited by the daemon
(cd ../python-sdk && ./daemon.sh start)   # shared dedicated daemon (serves WS :8099)
./run.sh ex1_basic_session.mjs            # run one example
./run.sh smoke.mjs                        # run all, assert the working core
```

> ⚠️ **Provider key / `pass://` needs jaato-premium.** The inline `SPEC` in
> `_config.mjs` sets `plugin_configs.openrouter.api_key = "${JAATO_OPENROUTER_API_KEY}"`.
> Over WS there is no `env_file`, so the daemon expands that var from **its own
> process environment** — export `JAATO_OPENROUTER_API_KEY` before `daemon.sh
> start`. This replaced a `pass://` secret URI, whose resolver ships only in the
> private **jaato-premium** package (on a public checkout it fails silently — the
> literal URI is used as the key). See the
> [org-wide note](https://github.com/Jaato-framework-and-examples/.github/blob/main/profile/README.md#-providers-and-api-keys-in-these-examples--read-this-first).

`run.sh` sets `NODE_EXTRA_CA_CERTS=$HOME/.jaato/certs/ca.crt` so node trusts the
daemon's self-signed Jaato Dev CA for `wss://`. The bearer token is read from
`~/.jaato/ws.token`. No secret committed.

## Frame sequence → docs map

| File | Frame sequence | ona.md |
|---|---|---|
| `ex1_basic_session.mjs` | connect → `session.new` → `message.send` → `agent.output`/`turn.completed` | §1 |
| `ex2_attach_replay.mjs` | detach → reconnect (`session.list` → `workspace.select`) → `session.attach` (replay) | §2 |
| `ex3_attach_followup.mjs` | reconnect → `session.attach` → `message.send` (continue) | §3 |
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
  `api_key` knob `"${JAATO_OPENROUTER_API_KEY}"`) so it works against a fresh
  daemon with no pre-installed `backend` profile. (Provider = `openrouter`,
  model = `google/gemini-2.5-flash`.) A `pass://` secret URI here would need
  jaato-premium — see the note under **Run**.

## Notes

- **ex1 + ex4** exercise the basic round-trip and the lifecycle frames
  (`session.list` → a session list, `session.stop`, `session.end`).
- **Re-attaching across connections needs a `workspace.select` first** (ex2/ex3).
  Each WS connection auto-provisions its own workspace, so a second connection
  can't see a session created on the first one until it re-targets that session's
  workspace. The reconnect sequence is: `session.list` (each entry carries its
  `workspace_path`) → `workspace.select <that path>` → `session.attach <sid>`.
  The daemon then restores the session from disk, replays its history (ex2), and
  the session keeps its memory (ex3). The cold restore is asynchronous: a send
  issued while it settles can return a recoverable `"Session not found"`, so the
  reconnect helper resends until output arrives.
- **The opaque `"Session not found"` is deliberate, not a rough edge.** Workspace
  isolation is a security boundary — a connection only sees its selected
  workspace, and the daemon won't reveal that a session exists in another one
  (that would leak cross-workspace session existence). So `workspace.select` is
  how a client legitimately re-targets a workspace it owns; it isn't a workaround
  for a vague error.
