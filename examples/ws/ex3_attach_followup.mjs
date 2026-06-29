// ex3 — Raw WS: re-attach and continue the same running session.
//
// Appears in: platform-comparisons/ona.md §3.
//
// Doc frames (verbatim shape):
//
//   → {"type":"command.execute","command":"session.attach","args":["<sid>"]}
//   → {"type":"message.send","text":"Also add tests."}     # continue the same running session
//
// The re-attached session keeps its memory, so the follow-up can reference the
// earlier turn. Substitutions: see README.
//
// FINDING (flagged upstream): on the installed build, a `message.send` to a
// RE-ATTACHED (previously-unloaded) session is not processed — no turn starts
// (the session was unloaded on detach; attach reloads it but the subsequent send
// goes nowhere). This example sends the correct doc frames and reports the
// observed behaviour; ex1 + ex4 are the fully-working raw-frame core.

import { SPEC } from "./_config.mjs";
import { connect, collectReply } from "./_ws.mjs";

// 1) Start a session, establish a fact, then detach.
const a = await connect();
a.send({ type: "command.execute", command: "session.new", args: [], payload: { spec: SPEC } });
const sid = (await a.until((f) => f.type === "agent.created" && f.session_id)).session_id;
a.send({ type: "message.send", text: "My favourite colour is teal. Acknowledge in one word." });
await collectReply(a);
a.close();
console.log("detached from", sid);

// 2) Re-attach and continue — the doc says the session remembers and accepts a
//    follow-up. Bounded so a non-processing re-attach can't hang.
const b = await connect();
b.send({ type: "command.execute", command: "session.attach", args: [sid] });
await new Promise((r) => setTimeout(r, 2000)); // brief settle (attach emits no frame to wait on)
b.send({ type: "message.send", text: "What is my favourite colour?" });
const reply = (await collectReply(b, 25000)).trim();
console.log("follow-up reply:", reply || "(no reply — a re-attached session did not process the follow-up on this build; see FINDING)");
b.close();
process.exit(0);
