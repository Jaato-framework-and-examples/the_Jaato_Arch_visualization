"""ex10 — Production: persistence, recovery, observability (IPCRecoveryClient).

Appears in: pydantic-ai.md §10 (canonical form), agno.md §10, claude-agent.md §10,
openai-agents.md §10, strands.md §10, langchain.md §10 (langchain passes
`on_status_change=print`; the others use the lambda shown here).

Doc snippet (verbatim shape):

    from jaato_sdk import IPCRecoveryClient
    async with IPCRecoveryClient.session(
            profile={"model": "gpt-4o", "provider": "openai"},
            on_status_change=lambda st: print(st.state)) as s:   # auto-reconnect across daemon restarts
        print(await s.ask("Long task…"))

`IPCRecoveryClient.session(...)` is the same facade on the auto-reconnect client:
it recovers an in-flight turn across a daemon restart and reports state via
`on_status_change` (reconnecting / connected / closed). Substitutions (see
README): `**CONN`, `**AUTH` (the pass: credential knob), the model/provider, and
the explicit `plugins`.
"""
import asyncio
from jaato_sdk import IPCRecoveryClient
from _config import CONN, AUTH


async def main():
    async with IPCRecoveryClient.session(**CONN,
            profile={"model": "google/gemini-2.5-flash", "provider": "openrouter", "plugins": [], **AUTH},
            on_status_change=lambda st: print(st.state)) as s:   # auto-reconnect across daemon restarts
        print(await s.ask("Long task…"))


asyncio.run(main())
