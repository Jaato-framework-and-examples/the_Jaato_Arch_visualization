// ex2 — Raw WS: detach, then re-attach by id (attach replays history).
//
// Appears in: platform-comparisons/ona.md §2.
//
// Doc frames (verbatim shape):
//
//   → {"type":"command.execute","command":"session.attach","args":["<sid>"]}
//   ← {"type":"agent.output","text":"…"}    # FIRST replayed history, THEN live output
//   ← {"type":"turn.completed", ...}         # a plain turn ends here…
//
// The session persists server-side after the client disconnects, so a second
// connection re-attaches by id and the daemon replays the prior turns. Because a
// WS connection auto-provisions its own workspace, the reconnect first selects
// the session's original workspace (session.list → workspace.select) before
// session.attach — see reattach() in _ws.mjs. Substitutions: see README.

import { SPEC } from "./_config.mjs";
import { connect, collectReply, reattach } from "./_ws.mjs";

// 1) Start a session, run one turn, then DETACH (close the socket).
const a = await connect();
a.send({ type: "command.execute", command: "session.new", args: [], payload: { spec: SPEC } });
const sid = (await a.until((f) => f.type === "agent.created" && f.session_id)).session_id;
a.send({ type: "message.send", text: "Name one ocean. One word." });
const first = (await collectReply(a)).trim();
a.close();
console.log("first turn:", first, "| detached from", sid);

// 2) Re-attach (select workspace → attach) — the daemon replays prior history.
const b = await connect();
await reattach(b, sid);
const replay = (await collectReply(b, 30000)).trim();
console.log("replayed history:", replay || "(none)");
b.close();
process.exit(0);
