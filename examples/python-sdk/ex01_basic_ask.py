"""ex01 — Hello world: one prompt, one reply.

Appears in: langchain.md §1, pydantic-ai.md §1, mastra.md §1, agno.md §1,
strands.md §1, openai-agents.md §1, claude-agent.md §1.

The doc shows two §1 snippets — the session form and the one-shot module
helper. Both are here, run back to back (verbatim shape):

    async with IPCClient.session(profile={"model": "gpt-4o", "provider": "openai"}) as s:
        print(await s.ask("Who are you? One sentence."))
    # …or the one-shot module helper, for a throwaway call:
    print(await ask("Who are you? One sentence.", profile={"model": "gpt-4o", "provider": "openai"}))

Three standing deviations apply (see README): `**CONN` for the dedicated
daemon, the GLM model/provider literal, and the `plugins` key the installed
daemon now requires on an inline spec.
"""
import asyncio
from jaato_sdk import IPCClient, ask
from _config import CONN


async def main():
    # The session form — the shape all seven SDK docs use in §1.
    async with IPCClient.session(**CONN,
            profile={"model": "glm-5-turbo", "provider": "zhipuai", "plugins": []}) as s:
        print(await s.ask("Who are you? One sentence."))

    # …or the one-shot module helper, for a throwaway call.
    print(await ask("Who are you? One sentence.", **CONN,
                    profile={"model": "glm-5-turbo", "provider": "zhipuai", "plugins": []}))


asyncio.run(main())
