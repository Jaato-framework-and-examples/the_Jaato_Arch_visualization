# SDK usage, side by side: **LangChain** vs **jaato-sdk**

Ten worked examples, simplest first, each shown in **LangChain** (Python) and **jaato-sdk** (Python). The point isn't "which is fewer lines" — it's to make the *shape* of each SDK visible, because they sit in different categories:

- **LangChain** is an **in-process library**: you construct an `llm`/agent object and call it; everything runs inside your Python process. State, tools, isolation, and durability are yours to assemble.
- **jaato-sdk** is an **async client to a long-lived daemon**: you open a **session** against a jaato server (auto-started if needed) and `ask` it. The agent loop, tool execution, isolation, persistence, and permissions run **server-side** in a confined per-session runner.

The daemon is a real architectural difference — but with the **convenience facade** (`IPCClient.session(...)` → `s.ask` / `s.complete` / `s.stream`) it costs about **one line** (`async with`), not the page of event-plumbing it used to. So the basic examples are now close to LangChain in size, and the advanced ones (multi-agent, human approval, cascades, crash-recovery) come built-in rather than assembled. Read it as a trade, not a scoreboard.

> **Setup.** LangChain: `pip install langchain langchain-openai` (`langgraph` for the agent/HITL/durability examples). jaato-sdk: `pip install jaato-sdk` + a reachable daemon socket. The facade front door: `from jaato_sdk import IPCClient, IPCRecoveryClient, ask, AgentError, PermissionUnhandled`. All jaato calls are `async`. The LangChain snippets use current LCEL / `langchain_openai` / LangGraph idioms (the API churns across majors — see the caveat at the end).

`IPCClient.session(...)` defaults the load-bearing knobs (`client_type=ClientType.API` so completion works headless, `env_file=".env"`, `auto_start=True`, `connect_timeout=120.0` for a cold autostart). It forwards `profile` / `agent` / `agent_params` / `cascade_driver_id` straight to `create_session`, so **both** the declarative style (`profile="researcher"`, named assets in `.jaato/`) and the programmatic style (`profile={"model": …, "provider": …}`) work. `ask`/`complete`/`stream` wait on the first of `{TURN_COMPLETED, SESSION_TERMINATED}` (so a plain turn never hangs) and **raise** on failure — `AgentError` on an error terminal, `PermissionUnhandled` if a gated tool goes unanswered — so there's no manual `if reason == "error"` bookkeeping. And the facade is **not all-or-nothing**: `s.client` exposes the underlying low-level client, so you can mix high-level `ask`/`complete`/`stream` with raw event-API calls — `s.client.subscribe(EventType.…)`, `s.client.cascade_events(...)`, `s.client.respond_to_permission(req_id, "e", edited_arguments={...})` (edit a tool's args before it runs) — on the **same session and connection** (listeners you add persist across turns). `ask`/`complete`/`stream` also take `attachments=[...]` for multimodal image/file inputs.

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
from jaato_sdk import IPCClient

async def main():
    async with IPCClient.session(profile={"model": "gpt-4o", "provider": "openai"}) as s:
        print(await s.ask("Who are you? One sentence."))

asyncio.run(main())
```
…or the one-shot module helper, for a throwaway call:
```python
from jaato_sdk import ask
print(await ask("Who are you? One sentence.", profile={"model": "gpt-4o", "provider": "openai"}))
```

**Side by side.** LangChain is one in-process call. jaato-sdk opens an isolated session on a (possibly auto-started) daemon and `ask`s — one `async with` of overhead, not a page of `connect`/`subscribe`/`done.wait`. The daemon is still there; it just costs a line now.

## 2. Streaming the reply

**LangChain**
```python
for chunk in llm.stream("Tell me a short story."):
    print(chunk.content, end="", flush=True)
```

**jaato-sdk**
```python
async with IPCClient.session(profile={"model": "gpt-4o", "provider": "openai"}) as s:
    async for chunk in s.stream("Tell me a short story."):
        print(chunk, end="", flush=True)
```

**Side by side.** Near-identical: both are async iterators of text chunks. `s.stream(...)` yields `AGENT_OUTPUT` chunks (filtered to model output by default; `sources=None` for everything incl. tool narration) and stops at turn end, raising the same `AgentError`/`PermissionUnhandled` after draining.

## 3. System prompt + multi-turn memory

**LangChain** — you own the message list (or bolt on a history runnable):
```python
from langchain_core.messages import SystemMessage, HumanMessage
history = [SystemMessage("You are a terse pirate."), HumanMessage("Hello")]
history.append(llm.invoke(history))                 # thread the reply back in
history.append(HumanMessage("And your name?"))
print(llm.invoke(history).content)                  # you carry the state
```

**jaato-sdk** — the **session is the memory**; the system prompt is a persona file:
```python
# persona lives in .jaato/agents/pirate.md (the system instructions), referenced by name:
async with IPCClient.session(agent="pirate",
                             profile={"model": "gpt-4o", "provider": "openai"}) as s:
    await s.ask("Hello")
    print(await s.ask("And your name?"))            # same session → it remembers
```

**Side by side.** LangChain threads the conversation through your own list (or `RunnableWithMessageHistory`). jaato-sdk keeps history **in the daemon session** — two `s.ask()` calls in one `async with` just continue it. A system prompt is a reusable **persona** (`agent="pirate"`), not an inline message.

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
# the "person-extractor" profile declares completion_payload_schema -> .jaato/completion_schemas/person.json
async with IPCClient.session(profile="person-extractor") as s:
    person = await s.complete("Alice is 30.")        # -> dict | None (server-validated payload)
    print(person["name"], person["age"])
```

**Side by side.** LangChain validates the model's output *after the fact, in your process* (`with_structured_output`). jaato makes typed output a **server-side completion gate**: the agent must call `signal_completion(payload)`, the daemon validates it against the JSON schema (and runs **completion processors**), and `s.complete()` returns only that validated `payload` (or `None`). A wrong-shape payload is bounced back to the model to retry — the agent can't "finish" malformed. (Author + check with `jaato-scaffold validate`.)

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

**jaato-sdk** — a client-provided ("host") tool the daemon calls back into, passed as `client_tools=` (the facade registers it after connect, before the session is created — the order the runner-tier model needs):
```python
def get_weather(args):                                # runs in YOUR process on invocation
    return {"weather": f"{args['city']}: sunny, 24C"}

async with IPCClient.session(
        profile={"model": "gpt-4o", "provider": "openai"},
        client_tools=[{
            "name": "get_weather", "description": "Return the weather for a city.",
            "parameters": {"type": "object",
                           "properties": {"city": {"type": "string"}}, "required": ["city"]},
            "handler": get_weather,
        }]) as s:
    print(await s.ask("Weather in Paris?"))
```

**Side by side.** LangChain's `bind_tools` hands *you* the tool-call to execute. jaato-sdk's `register_client_tools` registers a schema **the daemon's agent loop invokes**, calling back into your process for the handler — the loop, retries, and result-threading happen server-side. (jaato can also use **server-side** tool plugins — `cli`, `web_search`, `file_edit` — by listing them in the profile's `plugins`, with no client code at all — see Example 6.)

## 6. Multi-tool agent loop (ReAct)

**LangChain** — you construct the agent that runs the loop:
```python
from langgraph.prebuilt import create_react_agent
agent = create_react_agent("openai:gpt-4o", tools=[get_weather, search, calculator])
agent.invoke({"messages": [("user", "Plan a trip to Paris.")]})   # loop runs in-process
```

**jaato-sdk** — the daemon **is** the loop; you pick the tools and send one message:
```python
async with IPCClient.session(profile={                # server-side tools, no client glue
        "model": "gpt-4o", "provider": "openai",
        "plugins": ["cli", "web_search", "file_edit", "todo"]}) as s:
    print(await s.ask("Plan a trip to Paris and save it to trip.md"))
```

**Side by side.** In LangChain *you* assemble and own the agent loop. In jaato-sdk the loop — model → tool calls (permission-checked, parallelized) → results → model, until done — runs **inside the confined runner**; you choose the plugin set and `ask`. The loop is infrastructure, not your code.

## 7. Human-in-the-loop tool approval

**LangChain (LangGraph)** — you build the interrupt/resume with a checkpointer:
```python
from langgraph.checkpoint.memory import MemorySaver
agent = create_react_agent("openai:gpt-4o", tools=[delete_file],
                           checkpointer=MemorySaver(), interrupt_before=["tools"])
cfg = {"configurable": {"thread_id": "1"}}
agent.invoke({"messages": [("user", "Delete temp.log")]}, cfg)   # pauses before the tool
agent.invoke(None, cfg)                               # resume == approve
```

**jaato-sdk** — permissions are built-in; pass an `on_permission` callback:
```python
def approve(ev):                                      # called per gated tool; return the response
    return "y" if input(f"allow {ev.tool_name}? [y/n] ") == "y" else "n"

async with IPCClient.session(
        profile={"model": "gpt-4o", "provider": "openai", "plugins": ["cli"]},
        on_permission=approve) as s:
    print(await s.ask("Delete temp.log"))
```

**Side by side.** In LangGraph HITL is *assembled* from a checkpointer + `interrupt_before` + manual resume. In jaato-sdk it's **first-class**: the daemon asks before a gated tool and your `on_permission(ev)` returns `"y"`/`"n"`/`"a"`/… (sync or async; may set `edited_arguments` via the low-level `respond_to_permission`). Omit the callback and a gated tool makes `s.ask()` raise `PermissionUnhandled` (the facade auto-denies to keep the daemon unstuck). For *headless* sessions the same escalation can route to an out-of-band approval **gate** (the reliability reactor) instead of prompting — see the resilience doc.

**The deeper link — pausing a *cascade* for out-of-band approval.** `on_permission` assumes a client is connected to answer. But in jaato, tool-failure escalations are **bus events**, so a **reactor** can handle them with *nothing connected*. The reliability pattern (resilience doc): a **headless cascade stage** (Example 9) keeps failing a tool → the reliability reactor escalates → a reactor **parks the call on a `HandoffGate`** and requests approval **out-of-band** — e.g. a Telegram bot (via a webhook you wire) carrying the tool, its args, and which cascade stage asked → on **approve**, a second reactor flips deny→allow and **drives that same session's retry by id** — even if the runner was **unloaded** while waiting (it's reloaded by id, same session, no fork). So a long-running **cascade can pause mid-flight for a human and resume on approval**, hibernating in between — no client attached, no polling. And the pending approval (the **gate**) is durable: it survives a daemon restart, bounded by its TTL (an expired gate denies rather than hangs). LangGraph's `interrupt` does the same *shape*, but resumption runs in **your** process — you must be alive to call `.invoke(None, cfg)`; jaato's pause → approve → resume is **daemon-side, out-of-band, and durable**. (A deployment pattern — opt-in premium reactors + a gate + an approval webhook you wire, not client code; mechanism in the resilience doc.)

## 8. Multi-agent / subagent delegation

**LangChain (LangGraph)** — you wire the topology (supervisor / handoffs):
```python
from langgraph.graph import StateGraph, START
g = StateGraph(State)
g.add_node("researcher", researcher_agent); g.add_node("writer", writer_agent)
g.add_edge(START, "researcher"); g.add_edge("researcher", "writer")
g.compile().invoke({"topic": "tide pools"})
```

**jaato-sdk** — a **supervisor** persona delegates via the `subagent` plugin; delegation is **async + daemon-driven**, so this one drops to the event API:
```python
import asyncio
from jaato_sdk import IPCClient, EventType

# The "lead" persona delegates via spawn_subagent, ENDS its turn after spawning, and
# calls signal_completion once the subagents have returned and it has composed the answer.
async with IPCClient.session(agent="lead",
        profile={"model": "gpt-4o", "provider": "openai", "plugins": ["subagent"]}) as s:
    done, out = asyncio.Event(), []
    s.client.subscribe(EventType.AGENT_OUTPUT, lambda e: out.append(getattr(e, "text", "")))
    s.client.subscribe_once(EventType.SESSION_TERMINATED, lambda e: done.set())   # NOT turn.completed
    await s.client.send_message("Research tide pools, then write a blurb from the findings.")
    await done.wait()   # the daemon auto-continues 'lead' as each subagent COMPLETES;
                        # resolves only when 'lead' signal_completion's (the true end)
    print("".join(out))
```

**Side by side.** Both are true **delegation** — one lead agent decides when to hand off. But the execution models differ sharply. LangGraph runs the supervisor graph **in your process**, blocking until it composes. jaato's is **async and daemon-driven**: the lead calls `spawn_subagent(agent=…, task=…)` and **ends its turn**; each specialist runs **server-side** (sharing the parent's runner — a per-subagent *isolated* runner + cgroup is designed but **not yet shipped**), and its result returns as a `[SUBAGENT … COMPLETED]` event that **the daemon uses to auto-continue the lead** on a later turn, until the lead composes and `signal_completion`s. Because that spans many turns, this is the one example that uses the **event API**: the facade's `ask`/`complete`/`stream` all return on the first `TURN_COMPLETED` (the spawn turn), so you wait on `s.client` for the final `SESSION_TERMINATED`. (The `lead`/`researcher`/`writer` personas live in `.jaato/agents/`, and the lead must be **completion-gated**. You can also orchestrate from the *client* instead — separate `ask()` calls passing output — when you'd rather own the control flow.) **How the lead knows to delegate, and to whom:** its persona `.md` carries the *strategy* (when to hand off), while the `subagent` plugin surfaces the available *targets* — the lead calls `list_subagent_profiles` to read each profile's name + description, then `spawn_subagent(profile=…/agent=…, task=…)`. (LangGraph instead declares the agents and routing in the graph you wire, and the supervisor node's prompt decides.)

## 9. Multi-stage pipeline (chain vs cascade)

**LangChain** — an in-process LCEL pipeline:
```python
chain = extract_prompt | llm | parser | summarize_prompt | llm
chain.invoke({"doc": text})                           # synchronous data flow, your process
```

**jaato-sdk** — a **cascade**: sequential sessions sharing one **warm runner slot**:
```python
import uuid
cid = uuid.uuid4().hex                                 # one id per cascade
for prompt in ["Stage 1: extract.", "Stage 2: summarize."]:
    async with IPCClient.session(profile={"model": "gpt-4o", "provider": "openai"},
                                 cascade_driver_id=cid) as s:   # reuse the warm slot (~7s vs ~30s)
        await s.complete(prompt)   # complete() waits SESSION_TERMINATED → slot settled before the next stage
```

**Side by side.** A LangChain chain is synchronous data flow inside one process. A jaato cascade is a chain of **headless sessions** linked by completion events, reusing a pre-warmed runner slot (`cascade_driver_id`) so each stage skips cold-start — and in a real deployment the stage-to-stage handoff is **reactor-driven** (a reactor spawns the next stage on `slot.settled`), so stages are decoupled and observable. To *watch* a running cascade read-only, use the low-level event iterator — `async for ev in client.cascade_events(cid, event_types=[...], role="observer"): ...` — which is the *same* surface the facade exposes as `s.client`, so you interleave it with `s.ask`/`s.complete` rather than choosing one or the other.

## 10. Production: persistence, recovery, observability

**LangChain (LangGraph)** — configure durable state + tracing:
```python
from langgraph.checkpoint.postgres import PostgresSaver
agent = create_react_agent("openai:gpt-4o", tools=tools, checkpointer=PostgresSaver(...))
# durable threads via thread_id; tracing via LangSmith (LANGCHAIN_TRACING_V2=true)
```

**jaato-sdk** — durability/recovery/tracing are daemon properties; the recovery client is the *same* facade:
```python
from jaato_sdk import IPCRecoveryClient
async with IPCRecoveryClient.session(
        profile={"model": "gpt-4o", "provider": "openai"},
        on_status_change=print) as s:                  # auto-reconnect across daemon restarts
    print(await s.ask("Long task…"))                   # survives a daemon bounce
# sessions also persist server-side: detach (fire-and-forget) and reattach by id with the low-level client.
```

**Side by side.** In LangGraph you *opt into* durability (a checkpointer backend) and tracing (LangSmith). jaato-sdk inherits them from the **daemon**: `IPCRecoveryClient.session(...)` is the same facade on the auto-reconnect client (`on_status_change` reports `reconnecting`/`connected`/`closed`) and recovers an in-flight turn across a restart; sessions persist server-side and can be detached and **re-attached by id**; OpenTelemetry/OpenInference tracing (to Arize Phoenix) is a daemon env-flag, not client code. Plus what has no LangChain analog: each session runs in an **AppArmor-confined, workspace-scoped subprocess**.

---

## When each shines

| You want… | Reach for |
|---|---|
| A pure in-process library — nothing to run but Python (no daemon/server) | **LangChain** (or any in-process library) |
| A huge integration/tool/RAG ecosystem | **LangChain** |
| An explicit, inspectable, rewindable state graph | **LangGraph** |
| Multi-tenant, isolated, self-hosted agents; built-in permissions / cascades / crash-recovery; local GPUs; typed completion gates; a thin client, with per-agent memory isolated in server-side runners (optionally cgroup-capped) | **jaato-sdk** (you're driving a platform, not importing a library) |

**Honest caveats.**
- **LangChain's API churns** across majors (LCEL, `langchain` 0.x→1.x, the LangGraph split). The snippets above use the current idioms as of early 2026; verify against the version you install.
- **jaato-sdk needs a running daemon** (auto-started here). For one throwaway call that's a real dependency the in-process libraries don't have; for a fleet of isolated, recoverable agents it's the point. The facade keeps the common path to one `async with`, and `s.client` drops to the full low-level API on the same session when you need it (custom event routing, the cascade observer) — a front door, not a wall. Scaffold a known-good client with `jaato-scaffold new client` (see doc 23).
- **Client memory — thin client vs. in-process.** A LangChain process accumulates the model client, conversation history, tool outputs, and any RAG/vector data in *your* process, so its RSS grows with the workload. The jaato-sdk client holds only the connection, its event subscriptions, and the text you collect — history, the agent loop, and tool execution run in the **daemon + the per-session runner subprocess**, so the client stays small and roughly flat (you can even detach the session and exit, then reattach by id). It's memory *relocation + isolation*, not less total RAM: the daemon, the per-session runners, and the **pre-warm pool of idle warm runners** all carry it server-side, so on one box total RAM can be *higher*. Each agent runs in its own subprocess (so a runaway agent can't bloat *your* client), and a runner **can** additionally be memory-capped — a cgroup `memory.max` from a per-session `memory_max_mb` — but that's **opt-in**: only when the daemon runs as a WS server with cgroups enabled (`JAATO_CGROUPS_ROOT`) and a limit is configured. IPC sessions (like every example here) get no cgroup, and `memory_max_mb` defaults unset. Biggest win when the client is constrained/edge, or you fan out many agents.
- Apples-to-apples: both SDKs also ship **TypeScript** (`jaato-sdk-ts`, LangChain JS); these examples are Python for parity.
