# SDK usage, side by side: **Pydantic AI** vs **jaato-sdk**

Ten worked examples, simplest first, each shown in **Pydantic AI** and **jaato-sdk** — both in **Python**. The point isn't "which is fewer lines" — it's to make the *shape* of each SDK visible, because they sit in different categories:

- **Pydantic AI** is a **type-first, in-process Python library**: you construct an `Agent` and call it; everything runs inside your Python process. Its signature move is **types everywhere** — Pydantic models validate the structured output, the dependencies, and the tool arguments, and the result is a typed object you can rely on. State, isolation, and durability are yours to assemble.
- **jaato-sdk** is an **async client to a long-lived daemon**: agents run **server-side as isolated, permission-gated, per-session subprocesses**; your code is a thin client that opens a **session** and `ask`s. The agent loop, tools, isolation, persistence, and permissions live in the daemon.

So the trade is: Pydantic AI gives you a tightly-typed agent that lives in your process and is trivial to test and embed; jaato gives you runtime/provider-agnostic, multi-tenant, recoverable agents behind a boundary, with typed *completion* gates enforced server-side. Read it as a trade, not a scoreboard.

> **Setup.** Pydantic AI: `pip install pydantic-ai`. jaato-sdk: `pip install jaato-sdk` + a reachable daemon. The facade front door: `from jaato_sdk import IPCClient, IPCRecoveryClient, ask, AgentError, PermissionUnhandled`. All jaato calls are `async` (Pydantic AI offers both `run` (async) and `run_sync`).

`IPCClient.session(...)` defaults the load-bearing knobs (`client_type=ClientType.API` so completion works headless, `env_file=".env"`, `auto_start=True`, `connect_timeout=120.0`). It forwards `profile` / `agent` / `cascade_driver_id` to the session, so both the declarative style (`profile="researcher"`, named assets in `.jaato/`) and the programmatic style (`profile={"model": …, "provider": …}`) work. `ask`/`complete`/`stream` wait on the first of `{TURN_COMPLETED, SESSION_TERMINATED}` and **raise** on failure (`AgentError`, `PermissionUnhandled`). `s.client` exposes the underlying low-level client for mixing high- and low-level calls on one session.

---

## 1. Hello world — one prompt, one reply

**Pydantic AI**
```python
from pydantic_ai import Agent

agent = Agent("openai:gpt-4o", instructions="Be concise.")
result = agent.run_sync("Who are you? One sentence.")
print(result.output)
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
…or the one-shot module helper:
```python
from jaato_sdk import ask
print(await ask("Who are you? One sentence.", profile={"model": "gpt-4o", "provider": "openai"}))
```

**Side by side.** Pydantic AI is one in-process call returning a typed `result` (`.output` is `str` here). jaato opens an isolated session on a (possibly auto-started) daemon and `ask`s. The agent runs *in your process* in one case, *behind a boundary* in the other.

## 2. Streaming the reply

**Pydantic AI**
```python
async with agent.run_stream("Tell me a short story.") as response:
    async for text in response.stream_text(delta=True):
        print(text, end="", flush=True)
```

**jaato-sdk**
```python
async with IPCClient.session(profile={"model": "gpt-4o", "provider": "openai"}) as s:
    async for chunk in s.stream("Tell me a short story."):
        print(chunk, end="", flush=True)
```

**Side by side.** Both are async iteration over text deltas. Pydantic AI's `run_stream` is an async context manager yielding a typed `StreamedRunResult` (it can also stream *structured* output as it's validated); jaato's `s.stream(...)` is an `AsyncIterable[str]` of model-output chunks that raises `AgentError`/`PermissionUnhandled` after it drains.

## 3. System prompt + multi-turn memory

**Pydantic AI** — you thread the message history yourself:
```python
agent = Agent("openai:gpt-4o", instructions="You are a terse pirate.")
r1 = agent.run_sync("Hello")
r2 = agent.run_sync("And your name?", message_history=r1.all_messages())   # carry the thread
print(r2.output)
```

**jaato-sdk** — the **session is the memory**; the system prompt is a persona file:
```python
# persona lives in .jaato/agents/pirate.md (the system instructions), referenced by name:
async with IPCClient.session(agent="pirate", profile={"model": "gpt-4o", "provider": "openai"}) as s:
    await s.ask("Hello")
    print(await s.ask("And your name?"))            # same session → it remembers
```

**Side by side.** Pydantic AI keeps the conversation in *your* hands — you pass `message_history=result.all_messages()` into the next run (typed `ModelMessage` objects you can persist however you like). jaato keeps history **in the daemon session**; a second `ask` continues it. A system prompt is a reusable **persona** (`agent="pirate"`), not constructor config.

## 4. Structured / typed output

**Pydantic AI** — typed output is the framework's whole identity:
```python
from pydantic import BaseModel
class Person(BaseModel):
    name: str; age: int

agent = Agent("openai:gpt-4o", output_type=Person)
person = agent.run_sync("Alice is 30.").output      # a validated Person, fully typed
print(person.name, person.age)
```

**jaato-sdk** — a typed **completion schema** the *server* enforces:
```python
# the "person-extractor" profile declares a completion_payload_schema (.jaato/completion_schemas/person.json)
async with IPCClient.session(profile="person-extractor") as s:
    person = await s.complete("Alice is 30.")       # dict | None (server-validated payload)
    print(person["name"], person["age"])
```

**Side by side.** This is where the two are closest in *spirit* and furthest in *locus*. Pydantic AI validates the model's output against a Pydantic model **in your process** (`output_type` → `result.output`, by default via the model's tool-calling). jaato makes typed output a **server-side completion gate**: the agent must call `signal_completion(payload)`, the daemon validates it (and runs completion processors), and a wrong-shape payload is bounced back to the model to retry — the agent can't "finish" malformed, regardless of which client is connected. Under the hood both lean on **JSON Schema** at the model layer — Pydantic AI *generates* it from your model, jaato authors it directly — and both can push it down as **strict / grammar-constrained decoding** when the provider supports it. The difference is what enforces and what you get back: Pydantic AI validates with **Pydantic** in your process and hands you a **typed object**; jaato validates **server-side with `jsonschema`** (not Pydantic) and hands you a **dict**.

## 5. A single tool / function call

**Pydantic AI** — a decorated Python function becomes a typed tool:
```python
from pydantic_ai import Agent
agent = Agent("openai:gpt-4o")

@agent.tool_plain
def get_weather(city: str) -> str:
    "Return the weather for a city."
    return f"{city}: sunny, 24C"

print(agent.run_sync("Weather in Paris?").output)
```

**jaato-sdk** — a client-provided ("host") tool the daemon calls back into:
```python
async with IPCClient.session(
        profile={"model": "gpt-4o", "provider": "openai"},
        client_tools=[{
            "name": "get_weather", "description": "Return the weather for a city.",
            "parameters": {"type": "object",
                           "properties": {"city": {"type": "string"}}, "required": ["city"]},
            "handler": lambda args: {"weather": f"{args['city']}: sunny, 24C"},   # runs in YOUR process
        }]) as s:
    print(await s.ask("Weather in Paris?"))
```

**Side by side.** Pydantic AI derives the tool schema from your function's **type hints** (`@agent.tool_plain` for context-free tools; `@agent.tool` to receive a `RunContext` with injected `deps`), and runs the call inline in your process. jaato's `client_tools` registers a schema **the daemon's agent loop invokes**, calling back into your client for the handler — the loop, retries, and result-threading happen server-side. (jaato can also use **server-side** plugins — `cli`, `web_search`, … — via the profile's `plugins`, with no client code; Example 6.)

## 6. Multi-tool agent loop

**Pydantic AI** — register several tools; the agent loops internally:
```python
@agent.tool_plain
def search(q: str) -> str: ...
@agent.tool_plain
def calculator(expr: str) -> float: ...

agent.run_sync("Plan a trip to Paris.")     # model → tool calls → results → model, in your process
```

**jaato-sdk** — the daemon **is** the loop; pick the plugin set and `ask`:
```python
async with IPCClient.session(profile={
        "model": "gpt-4o", "provider": "openai",
        "plugins": ["cli", "web_search", "file_edit", "todo"]}) as s:
    print(await s.ask("Plan a trip to Paris and save it to trip.md"))
```

**Side by side.** Pydantic AI runs the tool-calling loop **inside `run`/`run_sync`**, in your process, until the model returns a final (typed) output. In jaato the loop — model → tool calls (permission-checked, parallelizable) → results → model — runs **inside the confined runner**; you choose the tools and `ask`. The loop is your dependency's code in one case, infrastructure in the other.

## 7. Human-in-the-loop tool approval

**Pydantic AI** — **deferred tools**: a tool needing approval ends (or pauses) the run:
```python
from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults
from pydantic_ai.tools import ToolApproved, ToolDenied

agent = Agent("openai:gpt-4o", output_type=[str, DeferredToolRequests])   # run may yield approvals
result = agent.run_sync("Delete temp.log")
if isinstance(result.output, DeferredToolRequests):
    approvals = {c.tool_call_id: ToolApproved() if ok(c) else ToolDenied("nope")
                 for c in result.output.approvals}
    result = agent.run_sync(message_history=result.all_messages(),
                            deferred_tool_results=DeferredToolResults(approvals=approvals))
print(result.output)
```

**jaato-sdk** — permissions are built-in; pass an `on_permission` callback:
```python
async with IPCClient.session(
        profile={"model": "gpt-4o", "provider": "openai", "plugins": ["cli"]},
        on_permission=lambda ev: "y" if approve(ev.tool_name) else "n") as s:
    print(await s.ask("Delete temp.log"))
```

**Side by side.** Pydantic AI's deferred-tools model is genuinely close in spirit: a gated tool pauses the run and surfaces `DeferredToolRequests`; you gather approvals and resume with the original `message_history` + a `DeferredToolResults`. It runs **in your process** — you hold the message history and drive the resume (inline `HandleDeferredToolCalls`, or stop-the-world-and-resume for an out-of-process UI). jaato's is **daemon-side**: `on_permission` answers inline, and for *headless* sessions the escalation is a **bus event** a reactor can park on a `HandoffGate`, ask a human **out-of-band** (a webhook/Telegram bridge), then drive the same session's retry by id — pause→approve→resume with **no client attached** (see the resilience doc). Same shape; in-process-and-you-resume vs daemon-side-and-out-of-band.

## 8. Multi-agent / delegation

**Pydantic AI** — **agent delegation**: a tool on one agent invokes another agent:
```python
from pydantic_ai import Agent, RunContext
researcher = Agent("openai:gpt-4o", instructions="Research topics, return bullet notes.")
lead = Agent("openai:gpt-4o", instructions="Delegate research, then write a blurb from the notes.")

@lead.tool
async def research(ctx: RunContext, topic: str) -> str:
    r = await researcher.run(f"Research {topic}", usage=ctx.usage)   # delegate; usage rolls up
    return r.output

print((await lead.run("Write a blurb about tide pools.")).output)
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

**Side by side.** Pydantic AI's delegation is **synchronous and in-process**: a `@lead.tool` calls `await researcher.run(...)` and blocks until it returns, rolling usage up via `ctx.usage`. jaato's is **async and daemon-driven**: the lead calls `spawn_subagent(profile=…, task=…)` and **ends its turn**; each specialist runs **server-side** in its own context (a per-subagent isolated runner + cgroup is designed but not yet shipped), and its result returns as a `[SUBAGENT … COMPLETED]` event the daemon uses to auto-continue the lead until it composes and `signal_completion`s. Because that spans many turns, the facade one-shots don't fit — you wait on `s.client` for the final `SESSION_TERMINATED`. (How the lead knows the targets: its **persona** gives the *role*, the **first prompt** carries the *task*, and the `subagent` plugin's `list_subagent_profiles` discovers the available **profiles** from `.jaato/profiles/`.)

## 9. Multi-stage pipeline (graph vs cascade)

**Pydantic AI** — `pydantic-graph`, a typed finite-state machine of node classes:
```python
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

class Extract(BaseNode[State]):
    async def run(self, ctx: GraphRunContext[State]) -> "Summarize":
        ctx.state.facts = await extract_agent.run(ctx.state.doc)
        return Summarize()
class Summarize(BaseNode[State]):
    async def run(self, ctx: GraphRunContext[State]) -> End[str]:
        return End((await summarize_agent.run(ctx.state.facts)).output)

await Graph(nodes=[Extract, Summarize]).run(Extract(), state=State(doc=text))
```

**jaato-sdk** — a real cascade is **event + reactor driven**, not a client loop. The client only starts **stage 1**; a **reactor** spawns every later stage server-side when the prior one completes:
```python
import uuid
cid = uuid.uuid4().hex
async with IPCClient.session(profile="extract", cascade_driver_id=cid) as s:
    await s.complete("Extract the facts from this doc: …")   # a headless stage; its completion drives the next
```
The hop lives in a **deployment reactor** (`.jaato/reactors/` + `.jaato/scripts/`), running inside the daemon:
```jsonc
// .jaato/reactors/cascade.json — fire when the 'extract' stage signals done
{ "rules": [{ "id": "cascade.after_extract",
              "match": { "event_type": "agent.completed", "where": "agent_id == 'extract'" },
              "action": { "script": "scripts/spawn_summarize.py" } }] }
```
```python
# .jaato/scripts/spawn_summarize.py — runs INSIDE the daemon on that event
def execute(params, event, ctx):
    facts = event.get("payload")                       # the prior stage's typed signal_completion output
    ctx.create_session(agent="summarize",              # spawn the next headless stage, server-side
                       initial_prompt=f"Summarise: {facts}",
                       cascade_driver_id=event.get("cascade_driver_id"))   # reuse the warm slot
```

**Side by side.** `pydantic-graph` is a **typed, in-process state machine you drive** — node classes return the next node, state passed around, the whole flow one Python program. A jaato **cascade** is **event- and reactor-driven, server-side**: each stage is an **isolated headless session** that just `signal_completion`s 'done' — *ignorant of what comes next* — and a **reactor** reacts to that completion event and spawns the successor (threading the prior stage's typed payload into a freed warm slot). The client only triggers stage 1; the pipeline then runs **decoupled in the daemon** — surviving the client disconnecting, each stage independently isolated/observable, and you branch or fan out by adding **rules, not code**. *(A client `for`-loop over `s.complete` can sequence stages too — but that's **you** orchestrating in-process, which any framework does; the cascade proper is the **daemon** orchestrating on events. Production splits the hop into a two-event `agent.completed`→`slot.settled` handoff for warm-slot reuse — see the cascade docs.)*

## 10. Production: persistence, recovery, observability

**Pydantic AI** — instrument with **Logfire** (built on OpenTelemetry):
```python
import logfire
logfire.configure()
logfire.instrument_pydantic_ai()        # or Agent(..., instrument=True)
agent.run_sync("…")                     # agent runs, tool calls, tokens → Logfire / any OTel backend
# durability (message history, retries) is yours to persist; runs live in your process.
```

**jaato-sdk** — durability/recovery/tracing are daemon properties:
```python
from jaato_sdk import IPCRecoveryClient
async with IPCRecoveryClient.session(
        profile={"model": "gpt-4o", "provider": "openai"},
        on_status_change=lambda st: print(st.state)) as s:      # auto-reconnect across daemon restarts
    print(await s.ask("Long task…"))                            # survives a daemon bounce
# sessions also persist server-side: detach (fire-and-forget) and re-attach by id with the low-level client.
```

**Side by side.** Pydantic AI gives you **first-class observability** (Logfire's LLM-aware traces, token/cost panels — and since it's OTel, any backend) but leaves **durability to you**: the run lives in your process, and you persist `all_messages()` to resume. jaato inherits durability from the **daemon**: `IPCRecoveryClient` auto-reconnects and recovers an in-flight turn across a restart; sessions persist server-side and re-attach by id; OpenTelemetry tracing is a daemon flag. Plus what Pydantic AI has no analog for: each session runs in its **own AppArmor-confinable, workspace-scoped subprocess**.

---

## When each shines

| You want… | Reach for |
|---|---|
| A tightly-typed agent in your Python process — Pydantic-validated output, deps, and tools; trivial to unit-test and embed | **Pydantic AI** |
| A low-setup, **first-party** LLM-observability *platform* (Logfire — built-in instrumentation, conversation/token/cost UI, by the same team) | **Pydantic AI** (both speak OpenTelemetry; jaato emits the same signals daemon-side to a backend *you* choose, with no bundled UI) |
| Multi-tenant, isolated, recoverable agents behind a boundary; built-in permissions / cascades / crash-recovery; provider- and runtime-agnostic (local GPUs); server-enforced typed completion gates; a thin client with per-agent memory isolated in server-side runners | **jaato-sdk** |

**Honest caveats.**
- Both sides are Python, so this is a genuine same-language comparison.
- **Pydantic AI moves quickly.** The snippets use the current API (`result.output`, `instructions=`, `output_type=`, deferred tools); verify exact signatures (especially the deferred-tools and `pydantic-graph` APIs) against the version you install.
- **jaato-sdk needs a running daemon** (auto-started here). For a single throwaway script that's a real dependency the in-process library doesn't have; for a fleet of isolated, recoverable, multi-tenant agents it's the point. The facade keeps the common path to one `async with`.
- Different runtime models: Pydantic AI runs **your** agent code (and tools) in your Python process — easy to test, embed, and reason about with types; jaato runs agents as **isolated subprocesses** behind the daemon, so a tool/agent crash or memory blowup is contained server-side, not in your app.
