// Minimal WebSocket harness for the raw-frame examples — NOT part of any SDK.
// Opens the wss connection with the bearer token, waits for the daemon's
// "connected" greeting, and exposes send(frame) + an awaitable frame queue. The
// raw JSON frames each example sends are the load-bearing part (they mirror the
// ona.md wire snippets); this just does the socket plumbing.
//
// TLS: the daemon's wss uses a self-signed Jaato Dev CA — run via ./run.sh,
// which sets NODE_EXTRA_CA_CERTS so Node trusts it (no disabling verification).

import { URL, TOKEN } from "./_config.mjs";

export async function connect() {
  const ws = new WebSocket(`${URL}/?token=${TOKEN}`);
  const buf = [];
  const waiters = [];
  let failed = null;

  ws.addEventListener("message", (e) => {
    const f = JSON.parse(e.data);
    if (waiters.length) waiters.shift().resolve(f);
    else buf.push(f);
  });
  ws.addEventListener("error", () => {
    failed = new Error("WebSocket error");
    while (waiters.length) waiters.shift().reject(failed);
  });
  ws.addEventListener("close", (e) => {
    failed = new Error(`WebSocket closed (code ${e.code})`);
    while (waiters.length) waiters.shift().reject(failed);
  });

  const next = () =>
    buf.length
      ? Promise.resolve(buf.shift())
      : failed
        ? Promise.reject(failed)
        : new Promise((resolve, reject) => waiters.push({ resolve, reject }));

  const send = (frame) => ws.send(JSON.stringify(frame));
  const until = async (pred) => {
    for (;;) {
      const f = await next();
      if (pred(f)) return f;
    }
  };

  await until((f) => f.type === "connected"); // wait for the greeting before sending commands
  return { ws, send, next, until, close: () => ws.close() };
}

// Collect agent.output text until turn.completed (or session.terminated), then
// return the model's reply. Mirrors the doc's "← agent.output … ← turn.completed".
// Bounded by maxMs so a turn that never completes can't hang the example.
export async function collectReply(c, maxMs = 90000) {
  let out = "";
  const deadline = Date.now() + maxMs;
  for (;;) {
    const timeout = new Promise((r) => setTimeout(() => r({ type: "__timeout" }), Math.max(0, deadline - Date.now())));
    const f = await Promise.race([c.next(), timeout]);
    if (f.type === "__timeout") return out;
    if (f.type === "agent.output" && (f.source === undefined || f.source === "model")) out += f.text ?? "";
    if (f.type === "turn.completed" || f.type === "session.terminated") return out;
  }
}
