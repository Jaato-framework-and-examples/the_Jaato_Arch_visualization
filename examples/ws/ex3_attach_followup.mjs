// ex3 — Raw WS: re-attach and continue the same running session.
//
// Appears in: platform-comparisons/ona.md §3.
//
// Doc frames (verbatim shape):
//
//   → {"type":"command.execute","command":"session.attach","args":["<sid>"]}
//   → {"type":"message.send","text":"Also add tests."}     # continue the same running session
//
// The re-attached session keeps its memory, so the reply reflects the colour
// established in the first turn. Because a WS connection auto-provisions its own
// workspace, the reconnect first selects the session's original workspace
// (session.list → workspace.select) before session.attach — see reattach() in
// _ws.mjs. While the session is restoring from disk a send can come back as a
// recoverable "Session not found"; re-attach and resend until output arrives.
// Substitutions: see README.

import { SPEC } from "./_config.mjs";
import { connect, reattach } from "./_ws.mjs";

// 1) Start a session, establish a fact, then detach (close the socket).
const a = await connect();
a.send({ type: "command.execute", command: "session.new", args: [], payload: { spec: SPEC } });
const sid = (await a.until((f) => f.type === "agent.created" && f.session_id)).session_id;
a.send({ type: "message.send", text: "My favourite colour is teal. Acknowledge in one word." });
for (;;) { const f = await a.next(); if (f.type === "turn.completed") break; }
a.close();
console.log("detached from", sid);

// 2) Re-attach (select workspace → attach) and continue. Resend on the recoverable
//    "Session not found" the restore raises until the follow-up turn completes.
const b = await connect();
await reattach(b, sid);
let reply = "";
for (let attempt = 1; attempt <= 6; attempt++) {
  b.send({ type: "message.send", text: "What is my favourite colour? Answer with just the colour." });
  let out = "";
  let retry = false;
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    const f = await Promise.race([b.next(), new Promise((r) => setTimeout(() => r({ type: "__t" }), deadline - Date.now()))]);
    if (f.type === "__t") break;
    if (f.type === "error") { retry = true; break; } // recoverable: restore still settling
    if (f.type === "agent.output") out += f.text ?? "";
    if (f.type === "turn.completed") break;
  }
  if (out.trim()) { reply = out.trim(); break; }
  if (retry) await reattach(b, sid);
}
console.log("follow-up reply:", reply);
b.close();
process.exit(0);
