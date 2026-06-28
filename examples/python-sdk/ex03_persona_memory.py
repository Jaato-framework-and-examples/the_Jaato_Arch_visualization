"""ex03 — System prompt + multi-turn memory (persona + session-as-memory).

Appears in: pydantic-ai.md §3, langchain.md §3, agno.md §3, claude-agent.md §3,
openai-agents.md §3, strands.md §3.

The system prompt is a reusable persona file (.jaato/agents/pirate.md), and the
daemon session IS the memory — two `s.ask` calls in one `async with` continue
the same conversation.

Doc snippet (verbatim shape):

    # persona lives in .jaato/agents/pirate.md (the system instructions):
    async with IPCClient.session(agent="pirate", profile={"model": "gpt-4o", "provider": "openai"}) as s:
        await s.ask("Hello")
        print(await s.ask("And your name?"))            # same session → it remembers

`agent="pirate"` resolves from <workspace>/.jaato/agents/pirate.md, so this
example passes `workspace_path=WORKSPACE` (the docs assume the daemon's default
workspace). Standing requirement: explicit `plugins` (`[]`). Standing
deviations (see README): `**CONN`, `**AUTH` (pass: cred knob), the model/provider literal.
"""
import asyncio
from jaato_sdk import IPCClient
from _config import CONN, WORKSPACE, AUTH


async def main():
    async with IPCClient.session(**CONN, workspace_path=WORKSPACE, agent="pirate",
                                 profile={"model": "openai/gpt-4o-mini", "provider": "openrouter", "plugins": [], **AUTH}) as s:
        await s.ask("Hello")
        print(await s.ask("And your name?"))            # same session → it remembers


asyncio.run(main())
