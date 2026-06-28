"""ex02 — Streaming the reply.

Appears in: langchain.md §2, pydantic-ai.md §2, mastra.md §2, agno.md §2,
strands.md §2, openai-agents.md §2, claude-agent.md §2.

Doc snippet (verbatim shape):

    async with IPCClient.session(profile={"model": "gpt-4o", "provider": "openai"}) as s:
        async for chunk in s.stream("Tell me a short story."):
            print(chunk, end="", flush=True)

Standing deviations (see README): `**CONN`, `**AUTH` (pass: cred knob), the model/provider literal. (`plugins` is the required form, not a deviation.)
"""
import asyncio
from jaato_sdk import IPCClient
from _config import CONN, AUTH


async def main():
    async with IPCClient.session(**CONN,
            profile={"model": "google/gemini-2.5-flash", "provider": "openrouter", "plugins": [], **AUTH}) as s:
        async for chunk in s.stream("Tell me a short story."):
            print(chunk, end="", flush=True)
    print()


asyncio.run(main())
