"""ex10 — Production: persistence, recovery, observability (IPCRecoveryClient).

Appears in: pydantic-ai.md §10 (canonical/majority form), agno.md §10,
claude-agent.md §10, openai-agents.md §10, strands.md §10, langchain.md §10*.
(* langchain.md passes `on_status_change=print`; the five other Python docs
share `on_status_change=lambda st: print(st.state)`, so it is canonical.)

Doc snippet (verbatim shape):

    from jaato_sdk import IPCRecoveryClient
    async with IPCRecoveryClient.session(
            profile={"model": "gpt-4o", "provider": "openai"},
            on_status_change=lambda st: print(st.state)) as s:   # auto-reconnect across daemon restarts
        print(await s.ask("Long task…"))

FINDING (the doc snippet hangs as written — caught by running it e2e):
The convenience facade's `ask`/`complete`/`stream` register handlers and then
`await done.wait()`, trusting the client to dispatch events to those handlers
in the background. `IPCClient` does (it runs a background drain task for the
connection's lifetime). `IPCRecoveryClient` does NOT — it only dispatches to
its handler registry while `client.events()` is being iterated (recovery.py
:870), and it has no `drain_events()` (that exists only on IPCClient,
ipc.py:2191). So `IPCRecoveryClient.session(...)` + bare `await s.ask(...)`
completes the turn server-side but the terminal event never reaches the
facade's `done.set()` → it hangs forever.

The doc's three load-bearing lines are reproduced verbatim below; the only
addition is the background `events()` pump that the recovery client needs for
the facade to work at all. Standing requirement: explicit `plugins` (`[]` here).
Standing deviations (see README): `**CONN`, `**AUTH` (pass: cred knob), the model/provider literal.
"""
import asyncio
from jaato_sdk import IPCRecoveryClient
from _config import CONN, AUTH


async def _pump(client):
    # Drive the recovery client's dispatch so the facade's terminal handler
    # fires. (IPCClient runs this in the background itself; the recovery client
    # doesn't — see the FINDING above.)
    try:
        async for _ in client.events():
            pass
    except asyncio.CancelledError:
        pass


async def main():
    async with IPCRecoveryClient.session(**CONN,
            profile={"model": "google/gemini-2.5-flash", "provider": "openrouter", "plugins": [], **AUTH},
            on_status_change=lambda st: print(st.state)) as s:   # auto-reconnect across daemon restarts
        pump = asyncio.create_task(_pump(s.client))
        try:
            print(await s.ask("Long task…"))
        finally:
            pump.cancel()


asyncio.run(main())
