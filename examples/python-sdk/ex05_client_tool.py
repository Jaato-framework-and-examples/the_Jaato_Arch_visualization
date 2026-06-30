"""ex05 — A single client-provided ("host") tool. ONE example, two transports:

    python ex05_client_tool.py ipc
    python ex05_client_tool.py in_process

`jaato.session(mode=...)` picks the transport (the daemon via IPC, or the
embedded in-process runtime); the SAME `profile={...}` and kwargs run both ways.
`socket_path` is ipc-only (ignored in-process); `env_file` applies to both. The
tool `handler` always runs in YOUR process.

Appears in: pydantic-ai.md §5 (canonical/majority form), agno.md §5,
claude-agent.md §5, openai-agents.md §5, strands.md §5, langchain.md §5*.
(* langchain.md uses a named `def get_weather(args)` instead of the inline
lambda — the five other Python docs share this lambda form, so it is canonical.)

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
        client_tools=[{
            "name": "get_weather", "description": "Return the weather for a city.",
            "parameters": {"type": "object",
                           "properties": {"city": {"type": "string"}}, "required": ["city"]},
            "handler": lambda args: {"weather": f"{args['city']}: sunny, 24C"},   # runs in YOUR process
            "auto_approve": True,
        }],
    ) as s:
        print(f"[{mode}]", await s.ask("Weather in Paris?"))


asyncio.run(main())
