"""ex01 — Hello world: one prompt, one reply. ONE example, two transports:

    python ex01_basic_ask.py ipc
    python ex01_basic_ask.py in_process

`jaato.session(mode=...)` picks the transport (the daemon via IPC, or the
embedded in-process runtime); the SAME `profile={...}` and kwargs run both ways.
`socket_path` is ipc-only (ignored in-process); `env_file` applies to both.

Appears in: langchain.md §1, pydantic-ai.md §1, mastra.md §1, agno.md §1,
strands.md §1, openai-agents.md §1, claude-agent.md §1.

Standing deviations (see README): the dedicated-daemon connection, the
model/provider literal + `**AUTH` (pass: cred knob), and the `plugins` key the
inline spec requires.

Scaffold a comparable skeleton — this file then customizes it:
    jaato-scaffold new client --workspace . --provider openrouter --model google/gemini-2.5-flash --transport ipc
    jaato-scaffold new client --workspace . --provider openrouter --model google/gemini-2.5-flash --transport in_process
"""
import asyncio
import sys

import jaato
from _config import CONN, AUTH

mode = sys.argv[1] if len(sys.argv) > 1 else "ipc"


async def main():
    async with jaato.session(
        mode=mode,
        profile={"model": "google/gemini-2.5-flash", "provider": "openrouter", "plugins": [],
                 "suppress_base_instructions": True, **AUTH},
        env_file=CONN["env_file"],
        socket_path=CONN["socket_path"],   # ipc-only; ignored in-process
    ) as s:
        print(f"[{mode}]", await s.ask("Who are you? One sentence."))


asyncio.run(main())
