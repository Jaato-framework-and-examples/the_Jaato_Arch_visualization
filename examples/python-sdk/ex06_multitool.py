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

FINDINGS (the doc's autonomous loop needs daemon-side config the docs omit —
they assume the ungated openai path with all tool backends present):
  1. jaato gates file/cli tools by default (permission defaultPolicy "deny"), so
     a loop with no on_permission raises PermissionUnhandled the moment the agent
     calls e.g. readFile. We set a permissive policy so it runs unattended
     (ex07 shows the interactive on_permission path).
  2. file_edit needs an operator-supplied backup dir (it writes backups under
     <backup_dir>/...); without config_root *or* plugin_configs.file_edit.backup_dir
     it won't initialise (framework PR-146 init-ordering). We set backup_dir.
  3. web_search needs a search backend that this bare test daemon doesn't have,
     so it's dropped from the live set; the loop is shown with cli/file_edit/todo
     (the deployable subset). The comparison-doc snippet keeps the full 4-plugin
     list as the illustration.

Standing requirement: explicit `plugins`. Standing deviations (see README):
`**CONN`, `**AUTH` (pass: cred knob), the model/provider literal, + the daemon
config above. Runs in WORKSPACE so file_edit writes here (trip.md is gitignored).
"""
import asyncio
import os
from jaato_sdk import IPCClient
from _config import CONN, WORKSPACE, AUTH

BACKUP_DIR = os.path.join(WORKSPACE, ".jaato", "backups")


async def main():
    async with IPCClient.session(**CONN, workspace_path=WORKSPACE, config_root=WORKSPACE,
                                 profile={
            "model": "openai/gpt-4o-mini", "provider": "openrouter",
            "plugins": ["cli", "file_edit", "todo"],   # web_search dropped — see FINDING 3
            "plugin_configs": {**AUTH["plugin_configs"],
                               "permission": {"policy": {"defaultPolicy": "allow"}},
                               "file_edit": {"backup_dir": BACKUP_DIR}}}) as s:
        print(await s.ask("Plan a trip to Paris and save it to trip.md"))


asyncio.run(main())
