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

This example sets a permissive permission policy and a reduced plugin set:
  - permission defaultPolicy "allow": jaato gates file/cli tools by default, so a
    loop with no on_permission raises PermissionUnhandled the moment the agent
    calls a gated tool (ex07 shows the interactive on_permission path).
  - file_edit is omitted: it needs its backup dir resolved before init, which
    can't happen here, so the agent does file work via `cli` instead. web_search
    stays (it uses the `ddgs`/DuckDuckGo library, no API key). Live plugin set:
    cli + web_search + todo; the comparison-doc snippet keeps the full 4-plugin
    list as the illustration.
  - the task requires real tool output (the current date + a dir listing, which
    the model can't fabricate) so the cli loop runs deterministically and writes
    report.txt, instead of the doc's vague "plan a trip and save it".

Standing requirement: explicit `plugins`. Standing deviations (see README):
`**CONN`, `**AUTH` (pass: cred knob), the model/provider literal, the permissive
policy, the reduced plugin set, and the tool-requiring task above. Runs in
WORKSPACE so cli's cwd is here (report.txt is gitignored).
"""
import asyncio
from jaato_sdk import IPCClient
from _config import CONN, WORKSPACE, AUTH


async def main():
    async with IPCClient.session(**CONN, workspace_path=WORKSPACE, profile={
            "model": "google/gemini-2.5-flash", "provider": "openrouter",
            "plugins": ["cli", "web_search", "todo"],   # file_edit omitted: backup dir can't resolve before init
            "plugin_configs": {**AUTH["plugin_configs"],
                               "permission": {"policy": {"defaultPolicy": "allow"}}}}) as s:
        # the task requires real tool output (the model can't fabricate the real
        # date/file list) so the cli loop runs deterministically, rather than the
        # doc's vague "plan a trip and save it" which a model may answer
        # conversationally without calling the shell.
        print(await s.ask("Using the shell, get the current date with `date` and the "
                          "directory listing with `ls`, then write both into a file "
                          "called report.txt. Do not ask questions; just do it."))


asyncio.run(main())
