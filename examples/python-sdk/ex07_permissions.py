"""ex07 — Human-in-the-loop tool approval (on_permission).

Appears in: pydantic-ai.md §7 (canonical/majority form), agno.md §7,
claude-agent.md §7, openai-agents.md §7, strands.md §7, langchain.md §7*.
(* langchain.md uses a named `def approve(ev)` that prompts via `input()`; the
five other Python docs share this inline-lambda form, so it is canonical.)

Doc snippet (verbatim shape):

    async with IPCClient.session(
            profile={"model": "gpt-4o", "provider": "openai", "plugins": ["cli"], **AUTH},
            on_permission=lambda ev: "y" if approve(ev.tool_name) else "n") as s:
        print(await s.ask("Delete temp.log"))

The doc leaves `approve(tool_name)` as an illustrative predicate. Here it is a
real one — auto-approving so the example is headless (the langchain variant
prompts via input()).

FINDING: the doc's `s.ask("Delete temp.log")` is a flaky way to trigger the gate
— a model may decline a destructive shell delete on safety grounds, or answer
conversationally instead of calling the tool, so the gate never fires (model-
dependent). The on_permission mechanism (the example's actual subject) is
identical for ANY gated tool, so we make the gate fire deterministically: ask for
something only the shell can provide (the system `date`, which the model can't
answer without the tool), with `defaultPolicy:"ask"` so every cli call is gated →
on_permission is asked → approves.

Standing deviations (see README): `**CONN`, `**AUTH` (pass: cred knob), the
model/provider literal, the ask-policy + benign command above.
"""
import asyncio
from jaato_sdk import IPCClient
from _config import CONN, WORKSPACE, AUTH


def approve(tool_name: str) -> bool:
    # In a TUI this would prompt; headless, we auto-approve and log the gate.
    print(f"[permission] {tool_name} -> approve")
    return True


async def main():
    async with IPCClient.session(**CONN, workspace_path=WORKSPACE,
            profile={"model": "google/gemini-2.5-flash", "provider": "openrouter", "plugins": ["cli"],
                     "plugin_configs": {**AUTH["plugin_configs"],
                                        "permission": {"policy": {"defaultPolicy": "ask"}}}},
            on_permission=lambda ev: "y" if approve(ev.tool_name) else "n") as s:
        print(await s.ask("What is the current date and time on this machine? Find out by running the `date` command in the shell."))


asyncio.run(main())
