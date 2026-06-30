"""ex08 — Multi-agent / subagent delegation. ONE example, two transports:

    python ex08_subagent.py ipc
    python ex08_subagent.py in_process

`jaato.session(mode=...)` picks the transport; the lead (agent="lead") delegates
to subagents (researcher, writer) discovered from .jaato/profiles/. Delegation
spans many turns, so this is the one example that drops to the event API and
waits for SESSION_TERMINATED (not a single turn's completion).

Multi-agent delegation is a harder task than a single ask/stream, so the lead
and its subagents use a model strong enough to orchestrate it reliably
(claude-sonnet-4.5); ex01-07 use the lighter google/gemini-2.5-flash for
single-shot tasks.

The lead must be completion-gated for the wait to resolve: SESSION_TERMINATED
fires only when 'lead' calls signal_completion, which is exposed only when the
profile declares a completion_payload_schema (the `blurb` schema below).
`subagent(preload)` puts the delegation tools on the initial wire, and the
permission policy whitelists them so the spawn is host-independent (not reliant
on a host's ~/.jaato permissions). `socket_path` is ipc-only (ignored
in-process); `env_file` applies to both.

Appears in: pydantic-ai.md §8, langchain.md §8, agno.md §8, claude-agent.md §8,
openai-agents.md §8, strands.md §8.
"""
import asyncio
import sys

import jaato
from jaato_sdk import EventType
from _config import CONN, WORKSPACE, AUTH

mode = sys.argv[1] if len(sys.argv) > 1 else "ipc"


async def main():
    async with jaato.session(
        mode=mode,
        agent="lead",
        workspace_path=WORKSPACE,
        config_root=WORKSPACE + "/.jaato",
        env_file=CONN["env_file"],
        socket_path=CONN["socket_path"],   # ipc-only; ignored in-process
        profile={
            "model": "anthropic/claude-sonnet-4.5", "provider": "openrouter",
            "plugins": ["subagent(preload)", "permission"],
            "plugin_configs": {**AUTH["plugin_configs"],
                               "permission": {"policy": {
                                   "whitelist": {"tools": ["spawn_subagent", "send_to_subagent",
                                                           "close_subagent", "cancel_subagent"]},
                                   "defaultPolicy": "allow"}}},
            "completion_payload_schema": {
                "type": "object", "additionalProperties": False,
                "required": ["blurb"],
                "properties": {"blurb": {"type": "string",
                                         "description": "The final composed blurb."}}},
        },
    ) as s:
        done, out = asyncio.Event(), []
        s.client.subscribe(EventType.AGENT_OUTPUT, lambda e: out.append(getattr(e, "text", "")))
        s.client.subscribe_once(EventType.SESSION_TERMINATED, lambda e: done.set())   # NOT turn.completed
        await s.client.send_message("Research tide pools, then write a blurb from the findings.")
        await done.wait()   # the runtime auto-continues 'lead' as each subagent COMPLETES
        print(f"[{mode}]", "".join(out))


asyncio.run(main())
