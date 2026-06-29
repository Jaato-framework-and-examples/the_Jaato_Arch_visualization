// Smoke runner — run every raw-WS example and assert real wire behaviour over
// the wss connection (not mocked): the basic round-trip (ex1), reconnect + replay
// (ex2), reconnect + memory (ex3), and the lifecycle frames (ex4).
//
//   (examples/python-sdk/daemon.sh start  — shared daemon, serves WS :8099)
//   ./run.sh smoke.mjs

import { execFile } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

function run(script, timeoutMs) {
  return new Promise((resolve) => {
    execFile("node", [join(HERE, script)], { cwd: HERE, timeout: timeoutMs, maxBuffer: 1 << 22 }, (err, stdout) => {
      resolve({ code: err && typeof err.code === "number" ? err.code : err ? 1 : 0, out: stdout });
    });
  });
}

const cases = [
  { script: "ex1_basic_session.mjs", timeoutMs: 90000, check: (o) => /reply:/.test(o) && o.split("reply:")[1].trim().length > 0 },
  { script: "ex2_attach_replay.mjs", timeoutMs: 90000, check: (o) => /replayed history:/.test(o) && !/\(none\)/.test(o) },
  { script: "ex3_attach_followup.mjs", timeoutMs: 130000, check: (o) => /follow-up reply:.*teal/is.test(o) },
  { script: "ex4_lifecycle.mjs", timeoutMs: 70000, check: (o) => /session\.list ->/.test(o) && /session\.stop \+ session\.end/.test(o) },
];

let pass = 0;
for (const c of cases) {
  const r = await run(c.script, c.timeoutMs);
  const ok = r.code === 0 && c.check(r.out);
  if (ok) pass++;
  console.log(`${ok ? "✓" : "✗"} ${c.script.padEnd(26)} ${ok ? "PASS" : "FAIL"} (rc=${r.code})`);
}
console.log(`\n${pass}/${cases.length} examples passed`);
process.exit(pass === cases.length ? 0 : 1);
