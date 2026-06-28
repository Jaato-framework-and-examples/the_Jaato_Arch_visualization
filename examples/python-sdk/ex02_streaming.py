"""ex02 — Streaming the reply.

Appears in: langchain.md §2, pydantic-ai.md §2, mastra.md §2, agno.md §2,
strands.md §2, openai-agents.md §2, claude-agent.md §2.

Doc snippet (verbatim shape):

    async with IPCClient.session(profile={"model": "gpt-4o", "provider": "openai"}) as s:
        async for chunk in s.stream("Tell me a short story."):
            print(chunk, end="", flush=True)

Standing deviations (see README): `**CONN`, GLM literal, `plugins:[]`.
"""
import asyncio
from jaato_sdk import IPCClient
from _config import CONN


async def main():
    async with IPCClient.session(**CONN,
            profile={"model": "glm-5-turbo", "provider": "zhipuai", "plugins": []}) as s:
        async for chunk in s.stream("Tell me a short story."):
            print(chunk, end="", flush=True)
    print()


asyncio.run(main())
