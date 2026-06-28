"""ex08 — Multi-agent / subagent delegation (async, daemon-driven).

Appears in: pydantic-ai.md §8, langchain.md §8, agno.md §8, claude-agent.md §8,
openai-agents.md §8, strands.md §8.

The lead's persona (agent="lead") gives it a delegating role; the first prompt
carries the task; the `subagent` plugin supplies the means (list_subagent_profiles
→ spawn_subagent). Delegation spans many turns, so this is the one example that
drops to the event API and waits for SESSION_TERMINATED (not turn.completed).

Doc snippet (verbatim shape):

    async with IPCClient.session(agent="lead",
            profile={"model": "gpt-4o", "provider": "openai", "plugins": ["subagent"]}) as s:
        done, out = asyncio.Event(), []
        s.client.subscribe(EventType.AGENT_OUTPUT, lambda e: out.append(getattr(e, "text", "")))
        s.client.subscribe_once(EventType.SESSION_TERMINATED, lambda e: done.set())   # NOT turn.completed
        await s.client.send_message("Research tide pools, then write a blurb from the findings.")
        await done.wait()   # the daemon auto-continues 'lead' as each subagent COMPLETES
        print("".join(out))

FINDING (the doc snippet can't terminate as written): the prose says "the lead
must be completion-gated" and the wait resolves "only when 'lead'
signal_completion's" — but signal_completion is only EXPOSED when the profile
declares a completion_payload_schema, and the doc's inline profile omits it. So
the lead can never signal_completion → SESSION_TERMINATED never fires →
done.wait() hangs. This file adds the completion gate the prose requires (a
`blurb` schema) to the inline profile; everything else is the doc verbatim.

Subagent targets (researcher, writer) are discovered from .jaato/profiles/, and
the lead persona from .jaato/agents/, so this passes `workspace_path=WORKSPACE`.
Standing requirement: explicit `plugins`. Standing deviations (see README):
`**CONN`, `**AUTH` (pass: cred knob), the model/provider literal, + the completion gate above.
"""
import asyncio
from jaato_sdk import IPCClient, EventType
from _config import CONN, WORKSPACE, AUTH


async def main():
    async with IPCClient.session(**CONN, workspace_path=WORKSPACE, agent="lead",
            profile={"model": "google/gemini-2.5-flash", "provider": "openrouter", "plugins": ["subagent"], **AUTH,
                     "completion_payload_schema": {
                         "type": "object", "additionalProperties": False,
                         "required": ["blurb"],
                         "properties": {"blurb": {"type": "string",
                                                  "description": "The final composed blurb."}}}}) as s:
        done, out = asyncio.Event(), []
        s.client.subscribe(EventType.AGENT_OUTPUT, lambda e: out.append(getattr(e, "text", "")))
        s.client.subscribe_once(EventType.SESSION_TERMINATED, lambda e: done.set())   # NOT turn.completed
        await s.client.send_message("Research tide pools, then write a blurb from the findings.")
        await done.wait()   # the daemon auto-continues 'lead' as each subagent COMPLETES
        print("".join(out))


asyncio.run(main())
