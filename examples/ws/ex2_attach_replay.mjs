// ex2 — Raw WS: detach, then re-attach by id (raw attach replays history).
//
// Appears in: platform-comparisons/ona.md §2.
//
// Doc frames (verbatim shape):
//
//   → {"type":"command.execute","command":"session.attach","args":["<sid>"]}
//   ← {"type":"agent.output","text":"…"}    # FIRST replayed history, THEN live output
//   ← {"type":"turn.completed", ...}         # a plain turn ends here…
//
// The session persists server-side after the client disconnects ("close the
// socket → the run keeps going"), so a second connection re-attaches by id and
// the daemon replays the prior turns. Substitutions: see README.
//
// FINDING (triaged with the framework owner): on this build raw `session.attach`
// does NOT stream a replay — the daemon deliberately skips re-emitting state on
// this attach path, so "raw attach replays prior turns" (ona.md §2) is
// aspirational for the raw-frame path, not a bug to wait on. This example sends
// the correct doc frame and reports the observed behaviour; ex1 + ex4 are the
// fully-working raw-frame core.

import { SPEC } from "./_config.mjs";
import { connect, collectReply } from "./_ws.mjs";

// 1) Start a session, run one turn, then DETACH (close the socket).
const a = await connect();
a.send({ type: "command.execute", command: "session.new", args: [], payload: { spec: SPEC } });
const sid = (await a.until((f) => f.type === "agent.created" && f.session_id)).session_id;
a.send({ type: "message.send", text: "Name one ocean. One word." });
const first = (await collectReply(a)).trim();
a.close(); // detach — the session persists server-side
console.log("first turn:", first, "| detached from", sid);

// 2) Re-attach by id on a fresh connection — the doc says the daemon replays
//    prior history. Bounded so a non-replaying attach can't hang.
const b = await connect();
b.send({ type: "command.execute", command: "session.attach", args: [sid] });
const replay = (await collectReply(b, 8000)).trim();
console.log("replayed history:", replay || "(none — raw session.attach did not replay on this build; see FINDING)");
b.close();
process.exit(0);
