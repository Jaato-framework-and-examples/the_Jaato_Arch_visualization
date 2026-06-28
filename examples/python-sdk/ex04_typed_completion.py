"""ex04 — Structured / typed output (server-enforced completion gate).

Appears in: pydantic-ai.md §4, langchain.md §4, agno.md §4, claude-agent.md §4,
openai-agents.md §4, strands.md §4.

The "person-extractor" profile declares a completion_payload_schema; the daemon
forces the agent to call signal_completion(payload), validates it server-side,
and `s.complete()` returns only the validated dict (or None).

Doc snippet (verbatim shape):

    # the "person-extractor" profile declares completion_payload_schema (.jaato/completion_schemas/person.json)
    async with IPCClient.session(profile="person-extractor") as s:
        person = await s.complete("Alice is 30.")       # dict | None (server-validated payload)
        print(person["name"], person["age"])

Note: this installed daemon takes the completion schema as an inline dict on the
profile (server/runner_spawn.py:561 reads `profile.completion_payload_schema`),
so .jaato/profiles/person-extractor.json embeds the schema rather than pointing
at a separate completion_schemas/person.json file — the doc's path is
illustrative; the Python (profile= + s.complete) is unchanged. `profile=` is a
named declarative asset, so this example passes `workspace_path=WORKSPACE`.
Standing deviations (see README): `**CONN`. (Model/provider + plugins live in
the profile JSON, not inline here.)
"""
import asyncio
from jaato_sdk import IPCClient
from _config import CONN, WORKSPACE


async def main():
    async with IPCClient.session(**CONN, workspace_path=WORKSPACE,
                                 profile="person-extractor") as s:
        person = await s.complete("Alice is 30.")       # dict | None (server-validated payload)
        print(person["name"], person["age"])


asyncio.run(main())
