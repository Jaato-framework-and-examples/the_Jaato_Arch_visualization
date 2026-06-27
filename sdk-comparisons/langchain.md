# SDK usage, side by side: **LangChain** vs **jaato-sdk**

Ten worked examples, simplest first, each shown in **LangChain** (Python) and **jaato-sdk** (Python). The point isn't "which is fewer lines" — it's to make the *shape* of each SDK visible, because they sit in different categories:

- **LangChain** is an **in-process library**: you construct an `llm`/agent object and call it; everything runs inside your Python process. State, tools, isolation, and durability are yours to assemble.
- **jaato-sdk** is an **async client to a long-lived daemon**: you `connect()` to a jaato server (auto-started if needed), open a **session**, `send_message`, and consume a **typed event stream** (`AGENT_OUTPUT`, `SESSION_TERMINATED`, `PERMISSION_REQUESTED`, …). The agent loop, tool execution, isolation, persistence, and permissions run **server-side** in a confined per-session runner.

That difference makes the basic examples *heavier* in jaato-sdk (you pay for the daemon/session/event machinery up front) and the advanced ones *lighter* (multi-agent, human approval, cascades, crash-recovery are built in, not assembled). Read it as a trade, not a scoreboard.

> **Setup.** LangChain: `pip install langchain langchain-openai` (and `langgraph` for the agent/HITL/durability examples). jaato-sdk: `pip install jaato-sdk` + a reachable daemon socket; `from jaato_sdk import IPCClient, IPCRecoveryClient, ClientType, EventType`. All jaato calls are `async`. The LangChain snippets use the current LCEL / `langchain_openai` / LangGraph idioms (the API churns across majors — see the caveat at the end).

The verified jaato-sdk knobs every example relies on (baked into `jaato-scaffold new client`): `client_type=ClientType.API` (keeps `signal_completion` for headless completion), `connect(timeout=120.0)` (a cold daemon autostart is ~30–60s), a **real** `env_file` (None crashes the handshake), and completion via `subscribe_once(EventType.SESSION_TERMINATED)`.

---

## 1. Hello world — one prompt, one reply

**LangChain**
```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o")
print(llm.invoke("Who are you? One sentence.").content)
```

**jaato-sdk**
```python
import asyncio
from jaato_sdk import IPCClient, ClientType, EventType

async def main():
    client = IPCClient("/tmp/jaato.sock", client_type=ClientType.API,
                       auto_start=True, env_file=".env", workspace_path=".")
    await client.connect(timeout=120.0)            # cold daemon autostart ~30–60s

    done, out = asyncio.Event(), []
    client.subscribe(EventType.AGENT_OUTPUT, lambda e: out.append(getattr(e, "text", "")))
    client.subscribe_once(EventType.SESSION_TERMINATED, lambda e: done.set())

    await client.create_session(profile={"model": "gpt-4o", "provider": "openai"})
    await client.send_message("Who are you? One sentence.")
    await done.wait()
    print("".join(out))
    await client.disconnect()

asyncio.run(main())
```

**Side by side.** LangChain is a single in-process call. jaato-sdk connects to a daemon, opens an isolated session, and consumes an event stream. The extra machinery *is* the product — it's what makes the later examples free.

> The rest of the examples factor that boilerplate into two helpers so each snippet shows only what's new:
> ```python
> async def connect():
>     c = IPCClient("/tmp/jaato.sock", client_type=ClientType.API,
>                   auto_start=True, env_file=".env", workspace_path=".")
>     await c.connect(timeout=120.0)
>     return c
>
> async def ask(client, prompt, **session):          # one-shot: send + collect + wait
>     done, out = asyncio.Event(), []
>     client.subscribe(EventType.AGENT_OUTPUT, lambda e: out.append(getattr(e, "text", "")))
>     client.subscribe_once(EventType.SESSION_TERMINATED, lambda e: done.set())
>     await client.create_session(**session)
>     await client.send_message(prompt)
>     await done.wait()
>     return "".join(out)
> ```

## 2. Streaming the reply

**LangChain**
```python
for chunk in llm.stream("Tell me a short story."):
    print(chunk.content, end="", flush=True)
```

**jaato-sdk**
```python
client = await connect()
client.subscribe(EventType.AGENT_OUTPUT,
                 lambda e: print(getattr(e, "text", ""), end="", flush=True))
client.subscribe_once(EventType.SESSION_TERMINATED, lambda e: ...)
await client.create_session(profile={"model": "gpt-4o", "provider": "openai"})
await client.send_message("Tell me a short story.")
```

**Side by side.** LangChain *opts in* to streaming (`.stream` vs `.invoke`). In jaato-sdk every turn already streams as `AGENT_OUTPUT` events — "non-streaming" (Example 1) is just buffering them. Streaming is the default, not a mode.

## 3. System prompt + multi-turn memory

**LangChain** — you own the message list (or bolt on a history runnable):
```python
from langchain_core.messages import SystemMessage, HumanMessage
history = [SystemMessage("You are a terse pirate.")]
history.append(HumanMessage("Hello"))
history.append(llm.invoke(history))                 # thread the reply back in
history.append(HumanMessage("And your name?"))
print(llm.invoke(history).content)                  # you carry the state
```

**jaato-sdk** — the **session is the memory**; the system prompt is a persona file:
```python
client = await connect()
# persona lives in .jaato/agents/pirate.md (system instructions), referenced by name:
await client.create_session(agent="pirate", profile={"model": "gpt-4o", "provider": "openai"})

async def turn(prompt):                              # wait for the turn to finish
    done = asyncio.Event()
    unsub = client.subscribe(EventType.TURN_COMPLETED, lambda e: done.set())
    await client.send_message(prompt); await done.wait(); unsub()

await turn("Hello")
await turn("And your name?")                         # same session → it remembers
```

**Side by side.** LangChain threads the conversation through your own list (or `RunnableWithMessageHistory`). jaato-sdk keeps history **in the daemon session** — `send_message` again continues it. A system prompt is a reusable **persona** (`agent="pirate"`), not an inline message.

## 4. Structured / typed output

**LangChain** — client-side Pydantic validation:
```python
from pydantic import BaseModel
class Person(BaseModel):
    name: str; age: int
result = llm.with_structured_output(Person).invoke("Alice is 30.")
print(result.name, result.age)                       # validated in your process
```

**jaato-sdk** — a typed **completion schema** the *server* enforces:
```python
# profile/persona declares completion_payload_schema -> .jaato/completion_schemas/person.json
client = await connect()
payload = {}
client.subscribe_once(EventType.AGENT_COMPLETED, lambda e: payload.update(e.payload or {}))
done = asyncio.Event(); client.subscribe_once(EventType.SESSION_TERMINATED, lambda e: done.set())
await client.create_session(profile="person-extractor")   # a set with the schema
await client.send_message("Alice is 30.")
await done.wait()
print(payload["name"], payload["age"])               # the agent called signal_completion(...)
```

**Side by side.** LangChain validates the model's output *after the fact, in your process* (`with_structured_output`). jaato makes typed output a **server-side completion gate**: the agent must call `signal_completion(payload)`, the daemon validates it against the JSON schema (and runs **completion processors**), and only then emits `AGENT_COMPLETED` with the typed `payload`. A rejected payload is bounced back to the model to retry — the agent can't "finish" with the wrong shape. (Authored + checked with `jaato-scaffold validate`.)

## 5. A single tool / function call

**LangChain** — a local Python tool bound to the model:
```python
from langchain_core.tools import tool
@tool
def get_weather(city: str) -> str:
    "Return the weather for a city."
    return f"{city}: sunny, 24C"
llm.bind_tools([get_weather]).invoke("Weather in Paris?")   # you run the call it returns
```

**jaato-sdk** — a client-provided ("host") tool the daemon calls back into:
```python
client = await connect()
def get_weather(args):                               # runs in YOUR process on invocation
    return {"weather": f"{args['city']}: sunny, 24C"}

await client.register_client_tools([{                # register BEFORE the session
    "name": "get_weather",
    "description": "Return the weather for a city.",
    "parameters": {"type": "object",
                   "properties": {"city": {"type": "string"}}, "required": ["city"]},
    "handler": get_weather,
}])
print(await ask(client, "Weather in Paris?",
                profile={"model": "gpt-4o", "provider": "openai"}))
```

**Side by side.** LangChain's `bind_tools` hands *you* the tool-call to execute (or you wrap it in an agent that loops). jaato-sdk's `register_client_tools` registers a schema **the daemon's agent loop invokes**, calling back into your process for the handler — the loop, retries, and result-threading happen server-side. (jaato can also use **server-side** tool plugins — `cli`, `web_search`, `file_edit` — by listing them in the profile's `plugins`, with no client code at all.)

## 6. Multi-tool agent loop (ReAct)

**LangChain** — you construct the agent that runs the loop:
```python
from langgraph.prebuilt import create_react_agent
agent = create_react_agent("openai:gpt-4o", tools=[get_weather, search, calculator])
agent.invoke({"messages": [("user", "Plan a trip to Paris.")]})   # loop runs in-process
```

**jaato-sdk** — the daemon **is** the loop; you just pick the tools and send one message:
```python
client = await connect()
await client.create_session(profile={                # server-side tools, no client glue
    "model": "gpt-4o", "provider": "openai",
    "plugins": ["cli", "web_search", "file_edit", "todo"],
})
print(await ask(client, "Plan a trip to Paris and save it to trip.md"))
```

**Side by side.** In LangChain *you* assemble and own the agent loop (prebuilt or hand-rolled). In jaato-sdk the agent loop — model → tool calls (permission-checked, parallelized) → results → model, until done — runs **inside the confined runner**; you choose the plugin set and observe `AGENT_OUTPUT` / tool events. The loop is infrastructure, not your code.

## 7. Human-in-the-loop tool approval

**LangChain (LangGraph)** — you build the interrupt/resume with a checkpointer:
```python
from langgraph.checkpoint.memory import MemorySaver
agent = create_react_agent("openai:gpt-4o", tools=[delete_file],
                           checkpointer=MemorySaver(), interrupt_before=["tools"])
cfg = {"configurable": {"thread_id": "1"}}
agent.invoke({"messages": [("user", "Delete temp.log")]}, cfg)   # pauses before the tool
# ... a human inspects state ...
agent.invoke(None, cfg)                               # resume == approve
```

**jaato-sdk** — permissions are built-in; subscribe and respond:
```python
client = await connect()
async def on_perm(e):                                 # the daemon asks before a gated tool
    ok = input(f"allow {e.tool_name}? [y/n] ") == "y"
    await client.respond_to_permission(e.request_id, "y" if ok else "n")
client.subscribe(EventType.PERMISSION_REQUESTED, lambda e: asyncio.ensure_future(on_perm(e)))

await client.set_default_policy("ask")                # or add_whitelist_tools([...])
print(await ask(client, "Delete temp.log",
                profile={"model": "gpt-4o", "provider": "openai", "plugins": ["cli"]}))
```

**Side by side.** In LangGraph HITL is *assembled* from a checkpointer + `interrupt_before` + manual resume. In jaato-sdk it's **first-class infrastructure**: the daemon emits `PERMISSION_REQUESTED` for gated tools, you `respond_to_permission(request_id, "y"|"n"|"a"|…)` (optionally with `edited_arguments`), and policy is set per-tool/session. For *headless* sessions the same escalation can route to an out-of-band approval gate (the reliability reactor) instead of blocking — see the resilience doc.

## 8. Multi-agent / subagent delegation

**LangChain (LangGraph)** — you wire the topology (supervisor / handoffs):
```python
from langgraph.graph import StateGraph, START
g = StateGraph(State)
g.add_node("researcher", researcher_agent)
g.add_node("writer", writer_agent)
g.add_edge(START, "researcher"); g.add_edge("researcher", "writer")
app = g.compile(); app.invoke({"topic": "tide pools"})
```

**jaato-sdk** — each agent is its own session; drive them, or let the agent spawn subagents:
```python
client = await connect()
notes  = await ask(client, "Research tide pools; return bullet notes.",
                   agent="researcher", profile={"model": "gpt-4o", "provider": "openai"})
draft  = await ask(client, f"Write a blurb from these notes:\n{notes}",
                   agent="writer", profile={"model": "gpt-4o", "provider": "openai"})
```

**Side by side.** LangGraph makes the multi-agent graph explicit and inspectable (you author nodes + edges). jaato-sdk gives each agent an **isolated session** (own runner, own plugins/persona); you compose them by passing output between `create_session` calls — or a single agent spawns **subagents** server-side via the `subagent` plugin. Different paradigm: explicit graph vs. independent sessions composed by the driver (or by reactors, for fully async cascades).

## 9. Multi-stage pipeline (chain vs cascade)

**LangChain** — an in-process LCEL pipeline:
```python
chain = extract_prompt | llm | parser | summarize_prompt | llm
chain.invoke({"doc": text})                           # synchronous data flow, your process
```

**jaato-sdk** — a **cascade**: sequential sessions sharing one **warm runner slot**:
```python
import uuid
client = await connect()
cid = uuid.uuid4().hex                                 # one id per cascade
for prompt in ["Stage 1: extract.", "Stage 2: summarize."]:
    await ask(client, prompt,
              cascade_driver_id=cid,                   # reuse the warm slot (~7s vs ~30s)
              profile={"model": "gpt-4o", "provider": "openai"})
```

**Side by side.** A LangChain chain is synchronous data flow inside one process. A jaato cascade is a chain of **headless sessions** linked by completion events, reusing a pre-warmed runner slot (`cascade_driver_id`) so each stage skips cold-start — and in a real deployment the stage-to-stage handoff is **reactor-driven** (a reactor spawns the next stage on `slot.settled`), so stages are decoupled and observable, not a single call stack. (An `observer` client can live-trace it via `client.cascade_events(cid, ...)`.)

## 10. Production: persistence, recovery, observability

**LangChain (LangGraph)** — configure durable state + tracing:
```python
from langgraph.checkpoint.postgres import PostgresSaver
agent = create_react_agent("openai:gpt-4o", tools=tools, checkpointer=PostgresSaver(...))
# durable threads via thread_id; tracing via LangSmith env vars (LANGCHAIN_TRACING_V2=true)
```

**jaato-sdk** — durability/recovery/tracing are daemon properties:
```python
def on_status(s): print("connection:", s)             # reconnecting / connected / closed
client = IPCRecoveryClient("/tmp/jaato.sock", client_type=ClientType.API,
                           auto_start=True, env_file=".env", workspace_path=".",
                           on_status_change=on_status)  # auto-reconnect across restarts
await client.connect(timeout=120.0)
sid = await client.create_session(profile={"model": "gpt-4o", "provider": "openai"})
await client.send_message("Long task…")               # survives a daemon bounce;
# later, from a fresh client:  await other.attach_session(sid)   # reattach by id
```

**Side by side.** In LangGraph you *opt into* durability (a checkpointer backend) and tracing (LangSmith). jaato-sdk inherits them from the **daemon**: `IPCRecoveryClient` auto-reconnects and recovers an in-flight turn across a daemon restart; sessions persist server-side and can be **detached and re-attached by id** (fire-and-forget then reattach); and OpenTelemetry/OpenInference tracing (to Arize Phoenix) is a daemon env-flag, not client code. Plus what has no LangChain analog at all: each session runs in an **AppArmor-confined, workspace-scoped subprocess**.

---

## When each shines

| You want… | Reach for |
|---|---|
| One agent, minimal ceremony, in your process | **LangChain** (or any in-process library) |
| A huge integration/tool/RAG ecosystem | **LangChain** |
| An explicit, inspectable, rewindable state graph | **LangGraph** |
| Multi-tenant, isolated, self-hosted agents; built-in permissions / cascades / crash-recovery; local GPUs; typed completion gates | **jaato-sdk** (you're driving a platform, not importing a library) |

**Honest caveats.**
- **LangChain's API churns** across majors (LCEL, `langchain` 0.x→1.x, the LangGraph split). The snippets above use the current idioms as of early 2026; verify against the version you install.
- **jaato-sdk needs a running daemon** (auto-started here). For a single throwaway script that's overhead; for a fleet of isolated, recoverable agents it's the point. Scaffold a known-good client with `jaato-scaffold new client` (see doc 23) rather than hand-writing the event boilerplate.
- Apples-to-apples: both SDKs also ship **TypeScript** (`jaato-sdk-ts`, LangChain JS); these examples are Python for parity.
