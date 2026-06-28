"""ex07 — Human-in-the-loop tool approval (on_permission).

Appears in: pydantic-ai.md §7 (canonical/majority form), agno.md §7,
claude-agent.md §7, openai-agents.md §7, strands.md §7, langchain.md §7*.
(* langchain.md uses a named `def approve(ev)` that prompts via `input()`; the
five other Python docs share this inline-lambda form, so it is canonical.)

Doc snippet (verbatim shape):

    async with IPCClient.session(
            profile={"model": "gpt-4o", "provider": "openai", "plugins": ["cli"]},
            on_permission=lambda ev: "y" if approve(ev.tool_name) else "n") as s:
        print(await s.ask("Delete temp.log"))

The doc leaves `approve(tool_name)` as an illustrative predicate. Here it is a
real one — auto-approving so the example is headless (the langchain variant
prompts via input()). Standing deviations (see README): `**CONN`, GLM literal.
(`plugins` is already present in this example's doc spec.)
"""
import asyncio
from jaato_sdk import IPCClient
from _config import CONN


def approve(tool_name: str) -> bool:
    # In a TUI this would prompt; headless, we auto-approve and log the gate.
    print(f"[permission] {tool_name} -> approve")
    return True


async def main():
    async with IPCClient.session(**CONN,
            profile={"model": "glm-5-turbo", "provider": "zhipuai", "plugins": ["cli"]},
            on_permission=lambda ev: "y" if approve(ev.tool_name) else "n") as s:
        print(await s.ask("Delete temp.log"))


asyncio.run(main())
