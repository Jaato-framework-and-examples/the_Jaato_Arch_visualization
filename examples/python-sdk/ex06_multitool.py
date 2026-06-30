"""ex06 — Multi-tool agent loop (the runtime IS the loop). ONE example, two
transports:

    python ex06_multitool.py ipc
    python ex06_multitool.py in_process

`jaato.session(mode=...)` picks the transport (the daemon via IPC, or the
embedded in-process runtime); the SAME `profile={...}` and kwargs run both ways.
`socket_path` is ipc-only (ignored in-process); `env_file` applies to both.

Appears in: pydantic-ai.md §6, langchain.md §6, agno.md §6, claude-agent.md §6,
openai-agents.md §6, strands.md §6.

You pick the server-side plugin set and send one message; the model → tool calls
→ results → model loop runs inside the confined runner.

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

Standing requirement: explicit `plugins`. Standing deviations (see README): the
dedicated-daemon connection, the model/provider literal, the permissive policy,
the reduced plugin set, and the tool-requiring task above. Runs in WORKSPACE so
cli's cwd is here (report.txt is gitignored).
"""
import asyncio
import sys

import jaato
from _config import CONN, WORKSPACE, AUTH

mode = sys.argv[1] if len(sys.argv) > 1 else "ipc"


async def main():
    async with jaato.session(
        mode=mode,
        profile={
            "model": "google/gemini-2.5-flash", "provider": "openrouter",
            "suppress_base_instructions": True,
            # cli(preload) forces the cli tool eager onto the initial wire instead of
            # behind lazy tool-discovery — so the model reaches it deterministically in
            # a multi-plugin session. web_search/todo stay lazy (the default).
            "plugins": ["cli(preload)", "web_search", "todo"],
            "plugin_configs": {**AUTH["plugin_configs"],
                               "permission": {"policy": {"defaultPolicy": "allow"}}}},
        env_file=CONN["env_file"],
        socket_path=CONN["socket_path"],   # ipc-only; ignored in-process
        workspace_path=WORKSPACE,
    ) as s:
        # One concrete shell command forces a real cli tool call whose output the
        # model can't fabricate, and keeps the task single-step so the model picks
        # the shell tool directly instead of improvising a file-writing tool. The
        # doc's vague "plan a trip and save it" lets a model answer conversationally
        # without calling a tool at all.
        print(f"[{mode}]", await s.ask("Run this exact shell command and report only its raw "
                          "output: echo jaato-multitool-ok. Do not ask questions; just run it."))


asyncio.run(main())
