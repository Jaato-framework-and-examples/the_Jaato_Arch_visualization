"""ex10 — Production: persistence, recovery, observability. ONE example, two
daemon transports:

    python ex10_recovery.py ipc
    python ex10_recovery.py ws

`jaato.session(mode=..., recovery=True)` swaps in the auto-reconnect client for
either daemon transport — IPCRecoveryClient (ipc, local Unix socket) or
WSRecoveryClient (ws, remote ws://). It recovers an in-flight turn across a
daemon restart and reports connection state via on_status_change (reconnecting /
connected / closed).

Recovery is daemon-only — there is no daemon to reconnect to in-process
(`mode="in_process", recovery=True` raises) — so this example's two modes are the
two DAEMON transports (ipc + ws), not the ipc + in_process of ex01-08. ipc
connects over the local Unix socket; ws over the remote ws:// endpoint + a token,
trusting the daemon's self-signed dev CA via `ca=` (scoped to that connection).

Appears in: pydantic-ai.md §10 (canonical form), agno.md §10, claude-agent.md §10,
openai-agents.md §10, strands.md §10, langchain.md §10 (langchain passes
`on_status_change=print`; the others use the lambda shown here).

Scaffold a comparable skeleton — this file then customizes it:
    jaato-scaffold new client --workspace . --provider openrouter --model google/gemini-2.5-flash --transport ipc --recoverable
    jaato-scaffold new client --workspace . --provider openrouter --model google/gemini-2.5-flash --transport ws --recoverable --url wss://localhost:8099 --ca ~/.jaato/certs/ca.crt
"""
import asyncio
import sys
from pathlib import Path

import jaato
from _config import CONN, WORKSPACE, WS_URL, WS_CA, ws_token

mode = sys.argv[1] if len(sys.argv) > 1 else "ipc"
# ipc connects over the local Unix socket (+ env_file); ws over the remote ws://
# endpoint + the daemon's WS auth token + the daemon's self-signed CA (ca=, scoped
# to this connection — not a global SSL_CERT_FILE that would replace the system
# roots process-wide).
conn = dict(CONN) if mode == "ipc" else {"url": WS_URL, "token": ws_token(), "ca": WS_CA}


async def main():
    async with jaato.session(
        mode=mode, recovery=True,
        workspace_path=Path(WORKSPACE),   # a Path: the recovery client does workspace_path / ".jaato"
        profile="recovery-demo",   # NAMED profile (.jaato/profiles/recovery-demo.json): recovery
                                   # re-resolves the profile's pass:// on the fresh daemon by NAME;
                                   # an INLINE profile isn't persisted to the recovery record.
        on_status_change=lambda st: print(st.state),   # auto-reconnect across daemon restarts
        **conn,
    ) as s:
        print(f"[{mode}]", await s.ask("Long task…"))


asyncio.run(main())
