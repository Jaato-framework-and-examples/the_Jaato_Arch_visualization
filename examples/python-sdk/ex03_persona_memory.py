"""ex03 — System prompt + multi-turn memory (persona + session-as-memory).
ONE example, two transports:

    python ex03_persona_memory.py ipc
    python ex03_persona_memory.py in_process

`jaato.session(mode=...)` picks the transport (the daemon via IPC, or the
embedded in-process runtime); the SAME `profile={...}` and kwargs run both ways.
`socket_path` is ipc-only (ignored in-process); `env_file` applies to both.

Appears in: pydantic-ai.md §3, langchain.md §3, agno.md §3, claude-agent.md §3,
openai-agents.md §3, strands.md §3.

The system prompt is a reusable persona file (.jaato/agents/pirate.md), and the
session IS the memory — two `s.ask` calls in one `async with` continue the same
conversation.

`agent="pirate"` resolves from <workspace>/.jaato/agents/pirate.md, so this
example passes `workspace_path=WORKSPACE` (+ `config_root` so the in-process
runtime resolves the persona; ipc ignores config_root). Standing requirement:
explicit `plugins` (`[]`). Standing deviations (see README): the dedicated-daemon
connection, the model/provider literal + `**AUTH` (pass: cred knob).

Scaffold a comparable skeleton — this file then customizes it:
    jaato-scaffold new client --workspace . --provider openrouter --model google/gemini-2.5-flash --transport ipc
    jaato-scaffold new client --workspace . --provider openrouter --model google/gemini-2.5-flash --transport in_process
"""
import asyncio
import sys

import jaato
from _config import CONN, WORKSPACE, AUTH

mode = sys.argv[1] if len(sys.argv) > 1 else "ipc"


async def main():
    async with jaato.session(
        mode=mode,
        profile={"model": "google/gemini-2.5-flash", "provider": "openrouter", "plugins": [],
                 "suppress_base_instructions": True, **AUTH},
        env_file=CONN["env_file"],
        socket_path=CONN["socket_path"],   # ipc-only; ignored in-process
        agent="pirate",
        workspace_path=WORKSPACE,
        config_root=WORKSPACE + "/.jaato",
    ) as s:
        await s.ask("Hello")
        print(f"[{mode}]", await s.ask("And your name?"))            # same session → it remembers


asyncio.run(main())
