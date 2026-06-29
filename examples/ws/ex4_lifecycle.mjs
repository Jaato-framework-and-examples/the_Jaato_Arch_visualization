// ex4 — Raw WS: session lifecycle (stop / end / delete / list).
//
// Appears in: platform-comparisons/ona.md §4.
//
// Doc frames (verbatim shape):
//
//   → {"type":"session.stop","agent_id":null}                        # cancel the in-flight turn (null = current/all)
//   → {"type":"command.execute","command":"session.end","args":[]}   # end current; or session.delete ["<sid>"]
//   → {"type":"command.execute","command":"session.list","args":[]}  # ← replies with a SessionList event
//
// Substitutions: see README.

import { SPEC } from "./_config.mjs";
import { connect } from "./_ws.mjs";

const c = await connect();
c.send({ type: "command.execute", command: "session.new", args: [], payload: { spec: SPEC } });
const sid = (await c.until((f) => f.type === "agent.created" && f.session_id)).session_id;
console.log("session:", sid);

// → session.list — the daemon replies with a list of sessions.
c.send({ type: "command.execute", command: "session.list", args: [] });
const list = await c.until((f) => /session.*list|list.*session|sessions/i.test(f.type));
const sessions = list.sessions ?? list.session_list ?? list.payload?.sessions ?? list;
console.log("session.list ->", Array.isArray(sessions) ? `${sessions.length} session(s)` : list.type);

// → session.stop (cancel any in-flight turn; null = current/all).
c.send({ type: "session.stop", agent_id: null });

// → session.end (end the current session; or session.delete ["<sid>"] by id).
c.send({ type: "command.execute", command: "session.end", args: [] });
console.log("sent session.stop + session.end for", sid);

setTimeout(() => {
  c.close();
  process.exit(0);
}, 1500);
