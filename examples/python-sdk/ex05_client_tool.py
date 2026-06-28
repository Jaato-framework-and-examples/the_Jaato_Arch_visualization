"""ex05 — A single client-provided ("host") tool.

Appears in: pydantic-ai.md §5 (canonical/majority form), agno.md §5,
claude-agent.md §5, openai-agents.md §5, strands.md §5, langchain.md §5*.
(* langchain.md uses a named `def get_weather(args)` instead of the inline
lambda — the five other Python docs share this lambda form, so it is canonical.)

Doc snippet (verbatim shape):

    async with IPCClient.session(
            profile={"model": "gpt-4o", "provider": "openai"},
            client_tools=[{
                "name": "get_weather", "description": "Return the weather for a city.",
                "parameters": {"type": "object",
                               "properties": {"city": {"type": "string"}}, "required": ["city"]},
                "handler": lambda args: {"weather": f"{args['city']}: sunny, 24C"},   # runs in YOUR process
            }]) as s:
        print(await s.ask("Weather in Paris?"))

Standing deviations (see README): `**CONN`, GLM literal, `plugins:[]`.
"""
import asyncio
from jaato_sdk import IPCClient
from _config import CONN


async def main():
    async with IPCClient.session(**CONN,
            profile={"model": "glm-5-turbo", "provider": "zhipuai", "plugins": []},
            client_tools=[{
                "name": "get_weather", "description": "Return the weather for a city.",
                "parameters": {"type": "object",
                               "properties": {"city": {"type": "string"}}, "required": ["city"]},
                "handler": lambda args: {"weather": f"{args['city']}: sunny, 24C"},   # runs in YOUR process
            }]) as s:
        print(await s.ask("Weather in Paris?"))


asyncio.run(main())
