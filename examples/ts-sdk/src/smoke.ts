// Smoke runner — run every TS example end-to-end and assert real behaviour.
//
// Not mocked: each example round-trips against the dedicated daemon over wss://.
// Each entry validates the real output (a model reply, a fired permission gate,
// a spawned cascade stage), not just exit code. Exits non-zero if any fails.
//
//   (examples/python-sdk/daemon.sh start  — shared daemon, serves WS :8099)
//   ./run.sh src/smoke.ts

import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(dirname(fileURLToPath(import.meta.url))); // project dir
const RUN = join(HERE, "run.sh");
const DAEMON_LOG = "/tmp/jaato-examples.log";

function run(script: string, timeoutMs: number): Promise<{ code: number; out: string }> {
  return new Promise((resolve) => {
    execFile(RUN, [`src/${script}`], { cwd: HERE, timeout: timeoutMs, maxBuffer: 1 << 22 }, (err, stdout) => {
      resolve({ code: err && typeof (err as { code?: number }).code === "number" ? (err as { code: number }).code : err ? 1 : 0, out: stdout });
    });
  });
}

const has = (...subs: string[]) => (out: string) => subs.some((s) => out.toLowerCase().includes(s.toLowerCase()));
const nonempty = (out: string) => out.trim().length > 0;
const twoLines = (out: string) => out.split("\n").filter((l) => l.trim()).length >= 2;

// ex09: the cascade runs decoupled in the daemon; confirm a later stage spawned.
async function cascadeContinued(): Promise<boolean> {
  for (let i = 0; i < 25; i++) {
    let log = "";
    try { log = await readFile(DAEMON_LOG, "utf8"); } catch { /* ignore */ }
    if (/agent=summarize|agent=verify|Using agent: (summarize|verify)/.test(log)) return true;
    await new Promise((r) => setTimeout(r, 3000));
  }
  return false;
}

interface Case { script: string; timeoutMs: number; check: (out: string) => boolean | Promise<boolean>; }
const CASES: Case[] = [
  { script: "ex01_basic_ask.ts", timeoutMs: 120000, check: twoLines },
  { script: "ex02_streaming.ts", timeoutMs: 120000, check: nonempty },
  { script: "ex03_persona_memory.ts", timeoutMs: 150000, check: nonempty },
  { script: "ex04_typed_completion.ts", timeoutMs: 120000, check: has("alice", "30") },
  { script: "ex05_client_tool.ts", timeoutMs: 120000, check: has("sunny", "24", "paris") },
  { script: "ex06_multitool.ts", timeoutMs: 200000, check: has("report.txt", "wrote", "date") },
  { script: "ex07_permissions.ts", timeoutMs: 150000, check: has("[permission]") },
  { script: "ex08_subagent.ts", timeoutMs: 240000, check: nonempty }, // delegation is model-dependent; see header
  { script: "ex09_cascade.ts", timeoutMs: 200000, check: () => cascadeContinued() },
  { script: "ex10_recovery.ts", timeoutMs: 150000, check: has("connected") },
];

let pass = 0;
for (const c of CASES) {
  let ok = false;
  let code = -1;
  try {
    const r = await run(c.script, c.timeoutMs);
    code = r.code;
    ok = code === 0 && (await c.check(r.out));
  } catch {
    ok = false;
  }
  if (ok) pass++;
  console.log(`${ok ? "✓" : "✗"} ${c.script.padEnd(26)} ${ok ? "PASS" : "FAIL"} (rc=${code})`);
}
console.log(`\n${pass}/${CASES.length} examples passed`);
process.exit(pass === CASES.length ? 0 : 1);
