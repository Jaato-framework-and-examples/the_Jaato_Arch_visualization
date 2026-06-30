"""ex07 — Human-in-the-loop tool approval (on_permission). ONE example, two
transports:

    python ex07_permissions.py ipc
    python ex07_permissions.py in_process

`jaato.session(mode=...)` picks the transport (the daemon via IPC, or the
embedded in-process runtime); the SAME `profile={...}` and kwargs run both ways.
`socket_path` is ipc-only (ignored in-process); `env_file` applies to both.

Appears in: pydantic-ai.md §7 (canonical/majority form), agno.md §7,
claude-agent.md §7, openai-agents.md §7, strands.md §7, langchain.md §7*.
(* langchain.md uses a named `def approve(ev)` that prompts via `input()`; the
five other Python docs share this inline-lambda form, so it is canonical.)

The doc leaves `approve(tool_name)` as an illustrative predicate. Here it is a
real one — auto-approving so the example is headless (the langchain variant
prompts via input()).

The on_permission mechanism is identical for any gated tool. The prompt asks for
something only the shell can provide (the system `date`), and `defaultPolicy:"ask"`
gates every cli call → on_permission is always asked → approves. This makes the
gate fire deterministically rather than the doc's "Delete temp.log", which a model
may decline or answer conversationally without calling the tool.

Standing deviations (see README): the dedicated-daemon connection, the
model/provider literal + `**AUTH` (pass: cred knob), the ask-policy + benign
command above.
"""
import asyncio
import sys

import jaato
from _config import CONN, WORKSPACE, AUTH

mode = sys.argv[1] if len(sys.argv) > 1 else "ipc"


def approve(tool_name: str) -> bool:
    # In a TUI this would prompt; headless, we auto-approve and log the gate.
    print(f"[permission] {tool_name} -> approve")
    return True


async def main():
    async with jaato.session(
        mode=mode,
        profile={"model": "google/gemini-2.5-flash", "provider": "openrouter", "plugins": ["cli(preload)"],
                 "suppress_base_instructions": True,
                 "plugin_configs": {**AUTH["plugin_configs"],
                                    "permission": {"policy": {"defaultPolicy": "ask"}}}},
        env_file=CONN["env_file"],
        socket_path=CONN["socket_path"],   # ipc-only; ignored in-process
        workspace_path=WORKSPACE,
        on_permission=lambda ev: "y" if approve(ev.tool_name) else "n",
    ) as s:
        print(f"[{mode}]", await s.ask("What is the current date and time on this machine? Find out by running the `date` command in the shell."))


asyncio.run(main())
