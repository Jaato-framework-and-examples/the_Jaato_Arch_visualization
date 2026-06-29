// ex1 — Raw WS: connect, start a session, send a message, read the reply.
//
// Appears in: platform-comparisons/ona.md §1 (the wire-level jaato example).
//
// Doc frames (verbatim shape — `→` client→server, `←` server→client):
//
//   websocat "wss://localhost:8080/?token=$JAATO_WS_TOKEN"
//   ← {"type":"connected","server_info":{...}}                      # wait for the greeting
//   → {"type":"command.execute","command":"session.new","args":["--profile","backend"],"payload":{}}
//   → {"type":"message.send","text":"Refactor the auth module and open a PR."}
//   ← {"type":"agent.output","text":"…"} … ← {"type":"turn.completed", ...}
//
// Substitutions (see README): wss://localhost:8099 + ?token= (the dedicated
// daemon); an INLINE session spec in `payload.spec` (model/provider + pass: cred
// knob) instead of `--profile backend`, so it runs against a fresh daemon with
// no pre-installed profile.

import { SPEC } from "./_config.mjs";
import { connect, collectReply } from "./_ws.mjs";

const c = await connect(); // opens wss + waits for the "connected" greeting

// → session.new (inline spec). The created session arrives as an "agent.created"
//   frame carrying the session_id.
c.send({ type: "command.execute", command: "session.new", args: [], payload: { spec: SPEC } });
const created = await c.until((f) => f.type === "agent.created" && f.session_id);
console.log("session:", created.session_id);

// → message.send, then read agent.output until turn.completed.
c.send({ type: "message.send", text: "Who are you? One sentence." });
console.log("reply:", (await collectReply(c)).trim());

c.close();
process.exit(0);
