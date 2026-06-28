"""ex06 — Multi-tool agent loop (the daemon IS the loop).

Appears in: pydantic-ai.md §6, langchain.md §6, agno.md §6, claude-agent.md §6,
openai-agents.md §6, strands.md §6.

You pick the server-side plugin set and send one message; the model → tool calls
→ results → model loop runs inside the confined runner.

Doc snippet (verbatim shape):

    async with IPCClient.session(profile={
            "model": "gpt-4o", "provider": "openai",
            "plugins": ["cli", "web_search", "file_edit", "todo"]}) as s:
        print(await s.ask("Plan a trip to Paris and save it to trip.md"))

FINDINGS (the doc's autonomous loop needs daemon-side config the docs omit — they
assume the ungated openai path with all tool backends present):
  1. jaato gates file/cli tools by default (permission defaultPolicy "deny"), so a
     loop with no on_permission raises PermissionUnhandled the moment the agent
     calls a gated tool. We set a permissive policy so it runs unattended (ex07
     shows the interactive on_permission path).
  2. file_edit won't initialise on this build: it needs its backup dir resolved
     before init, but config_root / plugin_configs.file_edit.backup_dir are
     applied too late (framework PR-146 init-ordering). So it's the one plugin
     dropped from the live set; the agent saves trip.md via `cli` instead.
(web_search is kept — it uses the `ddgs`/DuckDuckGo library, no API key/backend,
and works as long as the daemon has network access.)
So the live plugin set is cli + web_search + todo. The comparison-doc snippet
keeps the full 4-plugin list as the illustration.

Standing requirement: explicit `plugins`. Standing deviations (see README):
`**CONN`, `**AUTH` (pass: cred knob), the model/provider literal, the permissive
policy, and the reduced plugin set above. Runs in WORKSPACE so cli's cwd is here
(trip.md is gitignored).
"""
import asyncio
from jaato_sdk import IPCClient
from _config import CONN, WORKSPACE, AUTH


async def main():
    async with IPCClient.session(**CONN, workspace_path=WORKSPACE, profile={
            "model": "google/gemini-2.5-flash", "provider": "openrouter",
            "plugins": ["cli", "web_search", "todo"],   # only file_edit dropped — see FINDING 2
            "plugin_configs": {**AUTH["plugin_configs"],
                               "permission": {"policy": {"defaultPolicy": "allow"}}}}) as s:
        print(await s.ask("Plan a trip to Paris and save it to trip.md"))


asyncio.run(main())
