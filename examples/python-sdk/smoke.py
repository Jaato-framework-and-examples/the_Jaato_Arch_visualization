#!/usr/bin/env python3
"""Smoke runner — run every example end-to-end and assert real behaviour.

Not mocked: each example actually round-trips against the dedicated daemon
(`./daemon.sh start` first). Each entry has a validator that checks the real
output (a model reply, a fired permission gate, a spawned cascade stage), not
just exit code. Exits non-zero if any example fails.

    ./daemon.sh start
    ./.venv/bin/python smoke.py
"""
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable
DAEMON_LOG = "/tmp/jaato-examples.log"   # matches daemon.sh


def run(script: str, timeout: int):
    t0 = time.time()
    p = subprocess.run([PY, str(HERE / script)], capture_output=True, text=True,
                       cwd=HERE, timeout=timeout)
    return p.returncode, p.stdout, p.stderr, time.time() - t0


def nonempty(out):
    return bool(out.strip())


def two_lines(out):
    return len([l for l in out.splitlines() if l.strip()]) >= 2


def has(*subs):
    return lambda out: any(s.lower() in out.lower() for s in subs)


def report_written(out):
    # ex06: the multi-tool loop must actually use the shell to create report.txt.
    return (HERE / "report.txt").exists()


def cascade_threaded(out):
    # ex09 triggers stage 1; the reactor chain runs extract -> summarize ->
    # verify decoupled in the daemon. Assert REAL typed-payload threading (not
    # just that stages spawn): the newest summarize stage must have received the
    # extract's facts (its injected prompt is NOT "...: None"), and the verify
    # stage must have run. Poll the per-session records the stages write.
    sdir = HERE / ".jaato" / "sessions"
    deadline = time.time() + 110
    while time.time() < deadline:
        recs = sorted(sdir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if sdir.exists() else []
        newest_summarize, verify_ran = None, False
        for p in recs[:15]:
            try:
                t = p.read_text(errors="ignore")
            except OSError:
                continue
            if newest_summarize is None and "Summarise these findings:" in t:
                newest_summarize = t
            if "Verify this summary is accurate" in t:
                verify_ran = True
        if newest_summarize and "Summarise these findings: None" not in newest_summarize and verify_ran:
            return True
        time.sleep(4)
    return False


# No examples are blocked: the multi-turn deadlock that held ex03 was fixed
# upstream (jaato PR #413, drain-on-finally). Keep this set empty unless a new
# example gets blocked on an upstream fix.
PENDING = set()

# (script, timeout_s, validator)
EXAMPLES = [
    ("ex01_basic_ask.py",       120, two_lines),
    ("ex02_streaming.py",       120, nonempty),
    ("ex03_persona_memory.py",  150, nonempty),
    ("ex04_typed_completion.py",120, has("alice", "30")),
    ("ex05_client_tool.py",     120, has("sunny", "24", "weather")),
    ("ex06_multitool.py",       200, report_written),
    ("ex07_permissions.py",     150, has("[permission]")),
    ("ex08_subagent.py",        240, nonempty),
    ("ex09_cascade.py",         200, cascade_threaded),
    ("ex10_recovery.py",        150, has("connected")),
]


def main():
    results = []
    for script, timeout, validator in EXAMPLES:
        pending = script in PENDING
        try:
            rc, out, err, dt = run(script, timeout)
            ok = rc == 0 and validator(out)
        except subprocess.TimeoutExpired:
            rc, out, err, dt, ok = None, "", "", timeout, False
        if pending:
            results.append((script, "PENDING", dt))
            print(f"~ {script:28} PENDING (blocked on upstream fix; {'ok' if ok else 'still failing'})")
            continue
        results.append((script, "PASS" if ok else "FAIL", dt))
        print(f"{'✓' if ok else '✗'} {script:28} {'PASS' if ok else 'FAIL'}  ({dt:.0f}s, rc={rc})")
        if not ok:
            if err.strip():
                print(f"    stderr: {err.strip().splitlines()[-1][:200]}")
            if out.strip():
                print(f"    stdout: {out.strip().splitlines()[-1][:200]}")
    gated = [r for r in results if r[1] != "PENDING"]
    n_pass = sum(1 for _, s, _ in gated if s == "PASS")
    n_pending = len(results) - len(gated)
    print(f"\n{n_pass}/{len(gated)} gated examples passed ({n_pending} pending upstream fix)")
    return 0 if n_pass == len(gated) else 1


if __name__ == "__main__":
    raise SystemExit(main())
