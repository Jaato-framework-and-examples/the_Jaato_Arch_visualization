"""ex04 — Structured / typed output (server-enforced completion gate).
ONE example, two transports:

    python ex04_typed_completion.py ipc
    python ex04_typed_completion.py in_process

`jaato.session(mode=...)` picks the transport (the daemon via IPC, or the
embedded in-process runtime); the SAME named `profile` and kwargs run both ways.
`socket_path` is ipc-only (ignored in-process); `env_file` applies to both.

Appears in: pydantic-ai.md §4, langchain.md §4, agno.md §4, claude-agent.md §4,
openai-agents.md §4, strands.md §4.

The "person-extractor" profile declares a completion_payload_schema; the daemon
forces the agent to call signal_completion(payload), validates it server-side,
and `s.complete()` returns only the validated dict (or None).

Note: this installed daemon takes the completion schema as an inline dict on the
profile (server/runner_spawn.py:561 reads `profile.completion_payload_schema`),
so .jaato/profiles/person-extractor.json embeds the schema rather than pointing
at a separate completion_schemas/person.json file — the doc's path is
illustrative; the Python (profile= + s.complete) is unchanged. `profile=` is a
named declarative asset, so this example passes `workspace_path=WORKSPACE` (+
`config_root` so the in-process runtime resolves the named profile; ipc ignores
config_root). Model/provider + plugins live in the profile JSON, not inline here.
Standing deviations (see README): the dedicated-daemon connection.

Scaffold a comparable skeleton — this file then customizes it:
    jaato-scaffold new client --workspace . --provider openrouter --model google/gemini-2.5-flash --transport ipc
    jaato-scaffold new client --workspace . --provider openrouter --model google/gemini-2.5-flash --transport in_process
"""
import asyncio
import sys

import jaato
from _config import CONN, WORKSPACE

mode = sys.argv[1] if len(sys.argv) > 1 else "ipc"


async def main():
    async with jaato.session(
        mode=mode,
        profile="person-extractor",
        env_file=CONN["env_file"],
        socket_path=CONN["socket_path"],   # ipc-only; ignored in-process
        workspace_path=WORKSPACE,
        config_root=WORKSPACE + "/.jaato",
    ) as s:
        person = await s.complete("Alice is 30.")       # dict | None (server-validated payload)
        print(f"[{mode}]", person["name"], person["age"])


asyncio.run(main())
