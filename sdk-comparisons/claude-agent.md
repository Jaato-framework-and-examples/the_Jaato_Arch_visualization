# SDK usage, side by side: **Claude Agent SDK** vs **jaato-sdk**

Ten worked examples, simplest first, each shown in the **Claude Agent SDK** and **jaato-sdk** — both in **Python**. The point isn't "which is fewer lines" — it's to make the *shape* of each SDK visible. Of all the frameworks compared in this series, this is the **closest peer**: both are full agent **runtimes** (built-in tools, permission callbacks, subagents, hooks, sessions), not just libraries you assemble an agent from. The split is where the agent runs and how open it is:

- **Claude Agent SDK** is Anthropic's agent harness — the same loop that powers Claude Code: a built-in toolset (`Read`/`Write`/`Edit`/`Bash`/`WebFetch`/…), MCP, subagents, **permission modes** + a `can_use_tool` callback, and hooks. You drive it with `query()` (one-shot) or `ClaudeSDKClient` (interactive); the SDK talks to the Claude agent process over stream-json. It is **Claude-model-centric**, one agent process per client.
- **jaato-sdk** is an **async client to a long-lived, provider-agnostic daemon**: agents run **server-side as isolated, permission-gated, per-session subprocesses** with your own personas/profiles/plugins. The agent loop, tools, isolation, persistence, and permissions live in the daemon — multi-tenant, with reactor-driven cascades and server-enforced completion gates.

So both give you a batteries-included agent runtime; the Claude Agent SDK is Claude + the Claude Code toolset in one process, while jaato is any-model/any-runtime, multi-tenant, AppArmor-isolated, with the cascade/reactor/completion-gate machinery on top. Read it as a trade, not a scoreboard.

> **Setup.** Claude Agent SDK: `pip install claude-agent-sdk` (+ the `claude` CLI it drives). jaato-sdk: `pip install jaato-sdk` + a reachable daemon. Front door: `from jaato_sdk import IPCClient, IPCRecoveryClient, ask, AgentError, PermissionUnhandled`. Both are `async`.

`IPCClient.session(...)` defaults the load-bearing knobs (`client_type=ClientType.API` so completion works headless, `env_file=".env"`, `auto_start=True`, `connect_timeout=120.0`). It forwards `profile` / `agent` / `cascade_driver_id` to the session, so both the declarative style (`profile="researcher"`, named assets in `.jaato/`) and the programmatic style (`profile={"model": …, "provider": …, "plugins": []}` — an inline spec needs an explicit `plugins` key; `[]` = the minimal framework set) work. `ask`/`complete`/`stream` wait on the first of `{TURN_COMPLETED, SESSION_TERMINATED}` and **raise** on failure (`AgentError`, `PermissionUnhandled`). `s.client` exposes the underlying low-level client for mixing high- and low-level calls on one session.

---

## 1. Hello world — one prompt, one reply

**Claude Agent SDK**
```python
from claude_agent_sdk import query, AssistantMessage, TextBlock

async for message in query(prompt="Who are you? One sentence."):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                print(block.text, end="")
```

**jaato-sdk**
```python
import asyncio
from jaato_sdk import IPCClient

async def main():
    async with IPCClient.session(profile={"model": "gpt-4o", "provider": "openai", "plugins": []}) as s:
        print(await s.ask("Who are you? One sentence."))

asyncio.run(main())
```
…or the one-shot module helper:
```python
from jaato_sdk import ask
print(await ask("Who are you? One sentence.", profile={"model": "gpt-4o", "provider": "openai", "plugins": []}))
```

**Side by side.** `query(...)` is an async iterator of **typed messages** (assistant/tool/result) — even "hello world" hands you the agent's message stream, because it's a full agent loop. jaato opens an isolated session on a (possibly auto-started) daemon and `ask`s, collapsing that stream to the answer. Claude runs **in the agent process** the SDK drives; jaato's agent runs **behind a daemon boundary**.

## 2. Streaming the reply

**Claude Agent SDK**
```python
async for message in query(prompt="Tell me a short story."):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                print(block.text, end="", flush=True)
# set ClaudeAgentOptions(include_partial_messages=True) for raw token-level deltas
```

**jaato-sdk**
```python
async with IPCClient.session(profile={"model": "gpt-4o", "provider": "openai", "plugins": []}) as s:
    async for chunk in s.stream("Tell me a short story."):
        print(chunk, end="", flush=True)
```

**Side by side.** The Claude Agent SDK streams **messages** by default (assistant text, tool calls, results); `include_partial_messages=True` exposes raw token deltas. jaato's `s.stream(...)` is an `AsyncIterable[str]` of model-output chunks that raises `AgentError`/`PermissionUnhandled` after it drains (the full event stream is there too, via `s.client`).

## 3. System prompt + multi-turn memory

**Claude Agent SDK** — `ClaudeSDKClient` keeps a live multi-turn session:
```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

options = ClaudeAgentOptions(system_prompt="You are a terse pirate.")
async with ClaudeSDKClient(options=options) as client:
    await client.query("Hello")
    async for _ in client.receive_response(): ...
    await client.query("And your name?")          # same client → it remembers
    async for _ in client.receive_response(): ...
# (or resume later with the session_id from ResultMessage)
```

**jaato-sdk** — the **session is the memory**; the system prompt is a persona file:
```python
# persona lives in .jaato/agents/pirate.md (the system instructions), referenced by name:
async with IPCClient.session(agent="pirate", profile={"model": "gpt-4o", "provider": "openai", "plugins": []}) as s:
    await s.ask("Hello")
    print(await s.ask("And your name?"))          # same session → it remembers
```

**Side by side.** The Claude Agent SDK holds the conversation in a live `ClaudeSDKClient` (and can **resume** later from `ResultMessage.session_id` — restoring files read, analysis done, actions taken). jaato keeps state **in the daemon session**; a second `ask` continues it. A system prompt is an option in one case, a reusable **persona** (`agent="pirate"`) in the other.

## 4. Structured / typed output

**Claude Agent SDK** — no first-class typed output; you constrain by prompt and validate:
```python
from pydantic import BaseModel
class Person(BaseModel):
    name: str; age: int

# the SDK is an agentic harness, not an extraction library — ask for JSON, then validate:
text = ""
async for m in query(prompt='Extract name+age as JSON: "Alice is 30."'):
    if isinstance(m, AssistantMessage):
        text += "".join(b.text for b in m.content if isinstance(b, TextBlock))
person = Person.model_validate_json(text)
```

**jaato-sdk** — a typed **completion schema** the *server* enforces:
```python
# the "person-extractor" profile declares a completion_payload_schema (.jaato/completion_schemas/person.json)
async with IPCClient.session(profile="person-extractor") as s:
    person = await s.complete("Alice is 30.")   # dict | None (server-validated payload)
    print(person["name"], person["age"])
```

**Side by side.** This is where the two diverge most. The Claude Agent SDK has **no `output_type`** — it's built to *do agentic work* (edit files, run commands), not to extract typed objects, so you prompt for a shape and validate it yourself (or capture it through a custom tool). jaato makes typed output a **server-side completion gate**: the agent must call `signal_completion(payload)`, the daemon validates it against the JSON schema and bounces a wrong shape back to the model to retry — the agent can't "finish" malformed, regardless of which client is connected.

## 5. A single tool / function call

**Claude Agent SDK** — an in-process custom tool via an SDK MCP server:
```python
from claude_agent_sdk import tool, create_sdk_mcp_server, ClaudeAgentOptions, ClaudeSDKClient

@tool("get_weather", "Return the weather for a city.", {"city": str})
async def get_weather(args):
    return {"content": [{"type": "text", "text": f"{args['city']}: sunny, 24C"}]}

server = create_sdk_mcp_server(name="weather", tools=[get_weather])
options = ClaudeAgentOptions(mcp_servers={"weather": server},
                             allowed_tools=["mcp__weather__get_weather"])
async with ClaudeSDKClient(options=options) as client:
    await client.query("Weather in Paris?")
    async for _ in client.receive_response(): ...
```

**jaato-sdk** — a client-provided ("host") tool the daemon calls back into:
```python
async with IPCClient.session(
        profile={"model": "gpt-4o", "provider": "openai", "plugins": []},
        client_tools=[{
            "name": "get_weather", "description": "Return the weather for a city.",
            "parameters": {"type": "object",
                           "properties": {"city": {"type": "string"}}, "required": ["city"]},
            "handler": lambda args: {"weather": f"{args['city']}: sunny, 24C"},   # runs in YOUR process
        }]) as s:
    print(await s.ask("Weather in Paris?"))
```

**Side by side.** The Claude Agent SDK wraps custom tools as an **in-process MCP server** (`@tool` + `create_sdk_mcp_server`, exposed as `mcp__<server>__<name>`) — and ships a large built-in toolset besides. jaato's `client_tools` registers a schema **the daemon's agent loop invokes**, calling back into your client for the handler — the loop, retries, and result-threading happen server-side. (jaato can also use **server-side** plugins — `cli`, `web_search`, … — via the profile's `plugins`, with no client code; Example 6.)

## 6. Multi-tool agent loop

**Claude Agent SDK** — enable a set of (built-in + custom) tools; the agent loops:
```python
options = ClaudeAgentOptions(allowed_tools=["Read", "Write", "Bash", "WebFetch"])
async for _ in query(prompt="Plan a trip to Paris and save it to trip.md", options=options):
    pass                                         # the Claude agent loop runs Read/Write/Bash/… as needed
```

**jaato-sdk** — the daemon **is** the loop; pick the plugin set and `ask`:
```python
async with IPCClient.session(profile={
        "model": "gpt-4o", "provider": "openai",
        "plugins": ["cli", "web_search", "file_edit", "todo"]}) as s:
    print(await s.ask("Plan a trip to Paris and save it to trip.md"))
```

**Side by side.** Both are *batteries-included* loops. The Claude Agent SDK runs the **Claude Code agent loop** — a rich built-in toolset (files, shell, web, todo, …) gated by your `allowed_tools` — in the agent process. In jaato the loop runs **inside the confined runner**; you pick the plugin set and `ask`. The difference is mostly *whose process and which model*: Claude + the Claude Code toolset vs your model + your jaato plugins.

## 7. Human-in-the-loop tool approval

**Claude Agent SDK** — a `can_use_tool` callback (and `permission_mode`):
```python
from claude_agent_sdk import (ClaudeAgentOptions, ClaudeSDKClient,
                              PermissionResultAllow, PermissionResultDeny)

async def can_use_tool(tool_name, input_data, context):
    return PermissionResultAllow() if human_ok(tool_name, input_data) else PermissionResultDeny(message="denied")

options = ClaudeAgentOptions(allowed_tools=["Bash"], can_use_tool=can_use_tool,
                             permission_mode="default")
async with ClaudeSDKClient(options=options) as client:
    await client.query("Delete temp.log")
    async for _ in client.receive_response(): ...
```

**jaato-sdk** — permissions are built-in; pass an `on_permission` callback:
```python
async with IPCClient.session(
        profile={"model": "gpt-4o", "provider": "openai", "plugins": ["cli"]},
        on_permission=lambda ev: "y" if approve(ev.tool_name) else "n") as s:
    print(await s.ask("Delete temp.log"))
```

**Side by side.** These are almost the *same idea*: the Claude Agent SDK's `can_use_tool(tool_name, input, context)` returns `PermissionResultAllow`/`Deny` (with `permission_mode` presets like `acceptEdits`/`plan`/`bypassPermissions`), exactly like jaato's `on_permission(ev) → "y"/"n"`. Both run the decision **in your client**. jaato adds a daemon-side path the SDK has no analog for: for *headless* sessions the escalation is a **bus event** a reactor can park on a `HandoffGate`, ask a human **out-of-band** (a webhook bridge), then drive the same session's retry by id — pause→approve→resume with **no client attached** (see the resilience doc).

## 8. Multi-agent / delegation

**Claude Agent SDK** — **subagents**: define specialists; the lead delegates via the `Task` tool:
```python
from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition

options = ClaudeAgentOptions(agents={
    "researcher": AgentDefinition(description="Researches topics, returns notes.",
                                  prompt="You research topics.", tools=["WebFetch"]),
    "writer":     AgentDefinition(description="Writes blurbs from notes.",
                                  prompt="You write blurbs.", tools=[]),
})
async for _ in query(prompt="Research tide pools, then write a blurb.", options=options):
    pass                                         # the lead delegates to subagents via the Task tool
```

**jaato-sdk** — a **supervisor persona** delegates via the `subagent` plugin; delegation is **async + daemon-driven**, so the client drops to the event API. The persona gives the lead its delegating *role*:
```markdown
<!-- .jaato/agents/lead.md — role & behaviour, NOT a task -->
You are a coordinator. You get work done by delegating to specialist subagents
rather than doing it yourself: break the request into pieces, hand each to the
right specialist, and synthesise their results into the final answer.
```
The client sends the **task** as the first prompt; the lead delegates server-side:
```python
import asyncio
from jaato_sdk import IPCClient, EventType

async with IPCClient.session(agent="lead",
        profile={"model": "gpt-4o", "provider": "openai", "plugins": ["subagent"]}) as s:
    done, out = asyncio.Event(), []
    s.client.subscribe(EventType.AGENT_OUTPUT, lambda e: out.append(getattr(e, "text", "")))
    s.client.subscribe_once(EventType.SESSION_TERMINATED, lambda e: done.set())   # NOT turn.completed
    await s.client.send_message("Research tide pools, then write a blurb from the findings.")
    await done.wait()   # the daemon auto-continues 'lead' as each subagent COMPLETES
    print("".join(out))
```

**Side by side.** Conceptually close: the Claude Agent SDK's **subagents** (declared via `AgentDefinition`, each with its own prompt + tools) are invoked by the lead through the **`Task` tool**, running within the agent process. jaato's are **async and daemon-driven**: the lead persona calls `spawn_subagent(profile=…, task=…)` and **ends its turn**; each specialist runs **server-side** in its own context (a per-subagent isolated runner + cgroup is designed but not yet shipped), and its result returns as a `[SUBAGENT … COMPLETED]` event the daemon uses to auto-continue the lead until it composes and `signal_completion`s. Because that spans many turns, the facade one-shots don't fit — you wait on `s.client` for the final `SESSION_TERMINATED`. (How the lead knows the targets: its **persona** gives the *role*, the **first prompt** carries the *task*, and the `subagent` plugin's `list_subagent_profiles` discovers the available **profiles** from `.jaato/profiles/`.)

## 9. Multi-stage pipeline (chained agents vs cascade)

**Claude Agent SDK** — no pipeline primitive; you **chain runs in code** (or let subagents drive it):
```python
notes = ""
async for m in query(prompt="Research tide pools."):
    if isinstance(m, AssistantMessage):
        notes += "".join(b.text for b in m.content if isinstance(b, TextBlock))
async for m in query(prompt=f"Write a blurb from these notes:\n{notes}"):
    ...
```

**jaato-sdk** — a real cascade is **event + reactor driven**, not a client loop. Each stage runs a **persona** (`agent=`, its soul) under a **profile**, and needs a **first message** (its task): the client supplies **stage 1**'s, and a **reactor** *injects* every later stage's from the prior stage's output (no human types it):
```python
import uuid
cid = uuid.uuid4().hex
async with IPCClient.session(agent="extract", profile="extract",   # persona (soul) + profile (substrate)
                             cascade_driver_id=cid) as s:
    await s.complete("Extract the facts from this doc: …")          # stage 1's first message (its task)
```
For the typed handoff to work, the **producer's profile must declare a `completion_payload_schema`** — without it `signal_completion` is a legacy summary and `event.get("facts")` below is `None`:
```yaml
# .jaato/profiles/extract.yaml (excerpt)
completion_payload_schema: { type: object, properties: { facts: { type: string } }, required: [facts] }
# → the extract agent then calls signal_completion(facts="…")  — a schema's top-level props are FLAT args, not wrapped
```
A **deployment reactor** (`.jaato/reactors/` + `.jaato/scripts/`) spawns each next stage inside the daemon when the prior one completes:
```jsonc
// .jaato/reactors/cascade.json — fire when the 'extract' stage signals done
{ "rules": [{ "id": "cascade.after_extract",
              "match": { "event_type": "agent.completed", "where": "source_agent == 'extract'" },
              "action": { "script": "scripts/spawn_summarize.py" } }] }
```
```python
# .jaato/scripts/spawn_summarize.py — runs INSIDE the daemon on that event
def execute(params, event, ctx):
    facts = event.get("facts")                         # the prior stage's signal_completion fields are hoisted to the event's top level
    ctx.create_session(
        agent="summarize", profile="summarize",        # the next stage's persona (soul) + profile (runtime)
        initial_prompt=f"Summarise these findings: {facts}",   # its FIRST MESSAGE (task) — injected here; no human types it
        cascade_driver_id=read_cascade_driver_id(ctx.workspace_path))   # cid from the workspace cascade_state, not the event
```

**Side by side.** The Claude Agent SDK has **no pipeline object** — sequential work is *you* chaining `query` calls in code, or the agent driving subagents via the `Task` tool; both run **in the agent process**. A jaato **cascade** is **event- and reactor-driven, server-side**: each stage is an **isolated headless session** that just `signal_completion`s 'done' — *ignorant of what comes next* — and a **reactor** reacts to that completion and spawns the successor (threading the prior stage's typed payload into a freed warm slot). The client only triggers stage 1; the pipeline then runs **decoupled in the daemon** — surviving the client disconnecting, each stage independently isolated/observable, and you branch or fan out by adding **rules, not code**. *(A client `for`-loop over `s.complete` can sequence stages too — but that's **you** orchestrating in-process, which any framework does; the cascade proper is the **daemon** orchestrating on events. Production splits the hop into a two-event `agent.completed`→`slot.settled` handoff for warm-slot reuse — see the cascade docs.)*

## 10. Production: persistence, recovery, observability

**Claude Agent SDK** — hooks + session resume; OpenTelemetry via hooks/CLI:
```python
# Hooks (PreToolUse/PostToolUse/Stop) give you tracing + control points; session resume restores
# full context from ResultMessage.session_id. Observability typically rides the Claude Code CLI's
# OTel + the hook stream.
options = ClaudeAgentOptions(hooks={"PreToolUse": [my_trace_hook]}, resume=prior_session_id)
async for _ in query(prompt="Long task…", options=options):
    pass
```

**jaato-sdk** — durability/recovery/tracing are daemon properties:
```python
from jaato_sdk import IPCRecoveryClient
async with IPCRecoveryClient.session(
        profile={"model": "gpt-4o", "provider": "openai", "plugins": []},
        on_status_change=lambda st: print(st.state)) as s:      # auto-reconnect across daemon restarts
    print(await s.ask("Long task…"))                            # survives a daemon bounce
# sessions also persist server-side: detach (fire-and-forget) and re-attach by id with the low-level client.
```

**Side by side.** The Claude Agent SDK gives you **hooks** (PreToolUse/PostToolUse/Stop — for tracing and control) and **session resume** (restore full context by id), with observability typically via the CLI's OpenTelemetry. jaato inherits durability from the **daemon**: `IPCRecoveryClient` auto-reconnects and recovers an in-flight turn across a *daemon* restart; sessions persist server-side and re-attach by id; OTel tracing is a daemon flag. The isolation differs: the Claude Agent SDK runs one agent process; jaato runs each session in its **own AppArmor-confinable, workspace-scoped subprocess**, multi-tenant.

---

## Coming from the Claude Agent SDK

This is the closest peer in the series — both are full agent **runtimes** (built-in tools, permission callbacks, subagents, hooks, sessions), not libraries you assemble a loop from. So this isn't a scorecard: if you already think in the Claude Agent SDK, here's what actually changes when you move to jaato, and what it buys you:

- **Claude-on-the-`claude`-process becomes provider/runtime-agnostic.** The SDK is Claude-model-centric and drives the one `claude` CLI agent process; jaato's loop runs server-side against any model/provider (OpenAI, local GPUs, …) chosen per session via the profile. Same batteries-included agent loop — you just stop being pinned to one model and one process.
- **The single in-process agent becomes confined, multi-tenant per-session subprocesses.** The SDK runs one Claude agent process per client; jaato runs each session in its **own AppArmor-confinable, workspace-scoped subprocess** behind a daemon boundary — isolated, persistent, and re-attachable by id. Your `ClaudeSDKClient` collapses to a thin async client; the loop, tools, isolation, and memory all live in the daemon.
- **`@tool`/MCP + `can_use_tool`/`permission_mode` map almost one-to-one — plus a daemon-side gate the SDK has no analog for.** Your in-process MCP tools become jaato `client_tools` the daemon's loop calls back into; `can_use_tool(...) → Allow/Deny` becomes `on_permission(ev) → "y"/"n"`, still decided **in your client**. What's new: for *headless* sessions an escalation is a **bus event** a reactor can park on a `HandoffGate`, ask a human **out-of-band**, then drive the same session's retry by id — pause→approve→resume with no client attached.
- **No `output_type` → a server-enforced `completion_payload_schema`.** The SDK has no first-class typed output; you prompt for a shape and validate it in your process. jaato makes typed output a **server-side completion gate**: the agent must `signal_completion(payload)`, the daemon validates against the JSON schema and bounces a wrong shape back to the model — it can't "finish" malformed regardless of which client is attached (you get a validated dict). And **subagents** (`AgentDefinition` + the `Task` tool) become **daemon-driven** delegation — the lead spawns specialists that run server-side and auto-continue it on completion — composing into reactor-driven **cascades** you branch by adding rules, not code.

**What to keep in mind (honest trade-offs).**
- Both sides are Python (the Claude Agent SDK also ships TypeScript), so this is a genuine same-language comparison.
- The Claude Agent SDK is **evolving** — renamed from the Claude Code SDK, with options still shifting. The snippets use the current API (`query`/`ClaudeSDKClient`, `ClaudeAgentOptions`, `@tool`/`create_sdk_mcp_server`, `can_use_tool`/`permission_mode`, `AgentDefinition`, hooks); verify exact signatures against the version you install. It stays **Claude-model-centric**, drives the `claude` CLI agent process, and offers no first-class typed-output (`output_type`) primitive.
- jaato-sdk **needs a running daemon** (auto-started here). For a single throwaway script that's a real dependency; for a fleet of isolated, recoverable, multi-tenant agents it's the whole point. The facade keeps the common path to one `async with`.
- Closest peer, clearest split: both are full agent runtimes, but the Claude Agent SDK is **Claude + the Claude Code toolset in one process**, while jaato is **provider/runtime-agnostic and multi-tenant**, each agent in an isolated server-side subprocess with the reactor/cascade/completion-gate machinery on top.
