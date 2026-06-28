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
     dropped from the live set; the agent does file work via `cli` instead.
     (web_search is kept — it uses the `ddgs`/DuckDuckGo library, no API key, and
     works with network access.) Live plugin set: cli + web_search + todo; the
     comparison-doc snippet keeps the full 4-plugin list as the illustration.
  3. The doc's "plan a trip and save it" is a flaky way to *exercise* the loop —
     a model may ask for clarification (errors headless) or just print the plan
     instead of saving it. We use a self-contained task that REQUIRES tool output
     (the real date + dir listing, which the model can't fabricate) so the cli
     loop runs deterministically and writes report.txt.

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
            "plugins": ["cli", "web_search", "todo"],   # only file_edit dropped — see FINDING 2
            "plugin_configs": {**AUTH["plugin_configs"],
                               "permission": {"policy": {"defaultPolicy": "allow"}}}}) as s:
        # FINDING: the vague doc prompt ("plan a trip and save it") is a flaky
        # way to exercise the loop — a model may call the framework
        # `request_clarification` tool (which errors headless, no one to answer),
        # or just print the plan instead of calling the shell to save it. We use
        # a self-contained task that REQUIRES tool output (the model can't
        # fabricate the real date/file list), so the cli loop runs deterministically.
        print(await s.ask("Using the shell, get the current date with `date` and the "
                          "directory listing with `ls`, then write both into a file "
                          "called report.txt. Do not ask questions; just do it."))


asyncio.run(main())
