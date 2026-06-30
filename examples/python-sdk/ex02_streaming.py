"""ex02 — Streaming the reply. ONE example, two transports:

    python ex02_streaming.py ipc
    python ex02_streaming.py in_process

`jaato.session(mode=...)` picks the transport (the daemon via IPC, or the
embedded in-process runtime); the SAME `profile={...}` and kwargs run both ways.
`socket_path` is ipc-only (ignored in-process); `env_file` applies to both.

Appears in: langchain.md §2, pydantic-ai.md §2, mastra.md §2, agno.md §2,
strands.md §2, openai-agents.md §2, claude-agent.md §2.

Standing deviations (see README): the dedicated-daemon connection, the
model/provider literal + `**AUTH` (pass: cred knob), and the `plugins` key the
inline spec requires.
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
        print(f"[{mode}]", end=" ", flush=True)
        async for chunk in s.stream("Tell me a short story."):
            print(chunk, end="", flush=True)
    print()


asyncio.run(main())
