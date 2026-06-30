# SDK usage, side by side: **Pydantic AI** vs **jaato-sdk**

Ten worked examples, simplest first, each shown in **Pydantic AI** and **jaato-sdk** — both in **Python**. The point isn't "which is fewer lines" — it's to make the *shape* of each SDK visible, because they sit in different categories:

- **Pydantic AI** is a **type-first, in-process Python library**: you construct an `Agent` and call it; everything runs inside your Python process. Its signature move is **types everywhere** — Pydantic models validate the structured output, the dependencies, and the tool arguments, and the result is a typed object you can rely on. State, isolation, and durability are yours to assemble.
- **jaato-sdk** is an **async client to a long-lived daemon**: agents run **server-side as isolated, permission-gated, per-session subprocesses**; your code is a thin client that opens a **session** and `ask`s. The agent loop, tools, isolation, persistence, and permissions live in the daemon.

So the trade is: Pydantic AI gives you a tightly-typed agent that lives in your process and is trivial to test and embed; jaato gives you runtime/provider-agnostic, multi-tenant, recoverable agents behind a boundary, with typed *completion* gates enforced server-side. Read it as a trade, not a scoreboard.

> **Setup.** Pydantic AI: `pip install pydantic-ai`. jaato: `import jaato` → `jaato.session(mode=…)` (errors via `from jaato_sdk import AgentError, PermissionUnhandled`). All jaato calls are `async` (Pydantic AI offers both `run` (async) and `run_sync`).

> **Two ways to run the *same* agent (three transports).** `jaato.session(mode=…)` runs the runtime **embedded in your process** (`mode="in_process"`, no daemon — the direct analog to how Pydantic AI runs) **or** against a **daemon**: locally (`mode="ipc"`, what `IPCClient.session` does under the hood) or remotely over WebSocket (`mode="ws", url="wss://…", token=…`). The session spec and the `s.ask`/`complete`/`stream` facade are **identical**; `mode` is the only variable — the daemon modes add isolation, multi-tenancy, and crash-recovery (auto-reconnect via `IPCRecoveryClient` — Example 10). **Examples 1–8 each run in-process** by flipping `mode` (identical spec + machinery, so the same agent and behaviour — parity validated at the prompt and event level); **recovery (Example 10)** is daemon-only by definition; **cascade (9)** is in-process-capable and landing (it needs the premium reactor engine wired).

`jaato.session(mode=…)` forwards `profile` / `agent` / `cascade_driver_id` to the session, so both the declarative style (`profile="researcher"`, named assets in `.jaato/`) and the programmatic style (`profile={"model": …, "provider": …, "plugins": []}` — an inline spec needs an explicit `plugins` key; `[]` = the minimal framework set) work. The runnable example profiles set two determinism knobs (kept out of the snippets below for brevity): **`"suppress_base_instructions": True`** — drop the operator/user-tier base prompt so the session is **lean, deterministic, and leak-proof** (identical in-process and via the daemon) — and, in the agentic examples (6, 7), **`"cli(preload)"`** in `plugins`, which forces the `cli` tool *eager* onto the wire (plain plugin names are lazy-discovered) so a multi-plugin session is deterministic in both modes. `ask`/`complete`/`stream` wait on the first of `{TURN_COMPLETED, SESSION_TERMINATED}` and **raise** on failure (`AgentError`, `PermissionUnhandled`). `env_file` applies to every mode; `socket_path`/`auto_start` are IPC-only (ignored in-process).

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
import asyncio, jaato

async def main():
    # mode="ipc" → the daemon; mode="in_process" → embedded, no daemon. Same call either way.
    async with jaato.session(mode="ipc",
            profile={"model": "gpt-4o", "provider": "openai", "plugins": []}) as s:
        print(await s.ask("Who are you? One sentence."))

asyncio.run(main())
```

**Runnable:** [`examples/python-sdk/ex01_basic_ask.py`](../examples/python-sdk/ex01_basic_ask.py) — run `… ipc` or `… in_process`

**Side by side.** Pydantic AI is one in-process call returning a typed `result` (`.output` is `str` here). jaato `ask`s the same way — **in your process** (`mode="in_process"`, like Pydantic AI) or **behind the daemon boundary** (`mode="ipc"`/`"ws"`, for isolation/recovery). Same `s.ask`; you choose where the agent runs.

## 2. Streaming the reply

**Pydantic AI**
```python
async with agent.run_stream("Tell me a short story.") as response:
    async for text in response.stream_text(delta=True):
        print(text, end="", flush=True)
```

**jaato-sdk**
```python
async with jaato.session(mode="ipc", profile={"model": "gpt-4o", "provider": "openai", "plugins": []}) as s:
    async for chunk in s.stream("Tell me a short story."):
        print(chunk, end="", flush=True)
```

**Runnable:** [`examples/python-sdk/ex02_streaming.py`](../examples/python-sdk/ex02_streaming.py) — run `… ipc` or `… in_process`

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
async with jaato.session(mode="ipc", agent="pirate", profile={"model": "gpt-4o", "provider": "openai", "plugins": []}) as s:
    await s.ask("Hello")
    print(await s.ask("And your name?"))            # same session → it remembers
```

**Runnable:** [`examples/python-sdk/ex03_persona_memory.py`](../examples/python-sdk/ex03_persona_memory.py) — run `… ipc` or `… in_process`

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
async with jaato.session(mode="ipc", profile="person-extractor") as s:
    person = await s.complete("Alice is 30.")       # dict | None (server-validated payload)
    print(person["name"], person["age"])
```

**Runnable:** [`examples/python-sdk/ex04_typed_completion.py`](../examples/python-sdk/ex04_typed_completion.py) — run `… ipc` or `… in_process`

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
async with jaato.session(mode="ipc",
        profile={"model": "gpt-4o", "provider": "openai", "plugins": []},
        client_tools=[{
            "name": "get_weather", "description": "Return the weather for a city.",
            "parameters": {"type": "object",
                           "properties": {"city": {"type": "string"}}, "required": ["city"]},
            "handler": lambda args: {"weather": f"{args['city']}: sunny, 24C"},   # runs in YOUR process
        }]) as s:
    print(await s.ask("Weather in Paris?"))
```

**Runnable:** [`examples/python-sdk/ex05_client_tool.py`](../examples/python-sdk/ex05_client_tool.py) — run `… ipc` or `… in_process`

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

**jaato-sdk** — the loop runs **in the session** (embedded or daemon); pick the plugin set and `ask`:
```python
async with jaato.session(mode="ipc", profile={"model": "gpt-4o", "provider": "openai", "plugins": ["cli(preload)", "web_search", "todo"]}) as s:
    print(await s.ask("Plan a trip to Paris and save it to trip.md"))
```

**Runnable:** [`examples/python-sdk/ex06_multitool.py`](../examples/python-sdk/ex06_multitool.py) — run `… ipc` or `… in_process`

**Side by side.** Pydantic AI runs the tool-calling loop **inside `run`/`run_sync`**, in your process, until the model returns a final (typed) output. In jaato the loop — model → tool calls (permission-checked, parallelizable) → results → model — runs **wherever the session runs** — embedded (`mode="in_process"`) or the daemon's confined runner (`mode="ipc"`/`"ws"`); same loop, same result; the daemon adds per-session **sandbox isolation**, not different behaviour (so "the daemon runs the loop" is the wrong mental model — the *runtime* runs it); you choose the tools and `ask`. The loop is your dependency's code in one case, infrastructure in the other.

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
async with jaato.session(mode="ipc",
        profile={"model": "gpt-4o", "provider": "openai", "plugins": ["cli(preload)"]},
        on_permission=lambda ev: "y" if approve(ev.tool_name) else "n") as s:
    print(await s.ask("Delete temp.log"))
```

**Runnable:** [`examples/python-sdk/ex07_permissions.py`](../examples/python-sdk/ex07_permissions.py) — run `… ipc` or `… in_process`

**Side by side.** Pydantic AI's deferred-tools model is genuinely close in spirit: a gated tool pauses the run and surfaces `DeferredToolRequests`; you gather approvals and resume with the original `message_history` + a `DeferredToolResults`. It runs **in your process** — you hold the message history and drive the resume (inline `HandleDeferredToolCalls`, or stop-the-world-and-resume for an out-of-process UI). jaato's is **daemon-side**: `on_permission` answers inline, and for *headless* sessions the escalation is a **bus event** a reactor can park on a `HandoffGate`, ask a human **out-of-band** (a webhook bridge), then drive the same session's retry by id — pause→approve→resume with **no client attached** (see the resilience doc). Same shape; in-process-and-you-resume vs daemon-side-and-out-of-band.

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
import asyncio, jaato
from jaato_sdk import EventType

async with jaato.session(mode="ipc", agent="lead",   # mode="in_process" runs the delegation embedded too
        profile={"model": "gpt-4o", "provider": "openai",   # the runnable example uses a capable model (claude-sonnet-4.5) for delegation
                 "plugins": ["subagent(preload)", "permission"]}) as s:
    done, out = asyncio.Event(), []
    s.client.subscribe(EventType.AGENT_OUTPUT, lambda e: out.append(getattr(e, "text", "")))
    s.client.subscribe_once(EventType.SESSION_TERMINATED, lambda e: done.set())   # NOT turn.completed
    await s.client.send_message("Research tide pools, then write a blurb from the findings.")
    await done.wait()   # the daemon auto-continues 'lead' as each subagent COMPLETES
    print("".join(out))
```

**Runnable:** [`examples/python-sdk/ex08_subagent.py`](../examples/python-sdk/ex08_subagent.py) — run `… ipc` or `… in_process`

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

**Runnable:** [`examples/python-sdk/ex09_cascade.py`](../examples/python-sdk/ex09_cascade.py)

**Side by side.** `pydantic-graph` is a **typed, in-process state machine you drive** — node classes return the next node, state passed around, the whole flow one Python program. A jaato **cascade** is **event- and reactor-driven, server-side**: each stage is an **isolated headless session** that just `signal_completion`s 'done' — *ignorant of what comes next* — and a **reactor** reacts to that completion event and spawns the successor (threading the prior stage's typed payload into a freed warm slot). The client only triggers stage 1; the pipeline then runs **decoupled in the daemon** — surviving the client disconnecting, each stage independently isolated/observable, and you branch or fan out by adding **rules, not code**. The cascade machinery is **runtime-level** (the event bus + `create_session` live on the runtime), so the same chain can run **in-process** (`mode="in_process"`) when jaato-premium is installed and its reactor engine is registered — the daemon is just where it runs by default. *(A client `for`-loop over `s.complete` can sequence stages too — but that's **you** orchestrating in-process, which any framework does; the cascade proper is the **daemon** orchestrating on events. Production splits the hop into a two-event `agent.completed`→`slot.settled` handoff for warm-slot reuse — see the cascade docs.)*

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
        profile={"model": "gpt-4o", "provider": "openai", "plugins": []},
        on_status_change=lambda st: print(st.state)) as s:      # auto-reconnect across daemon restarts
    print(await s.ask("Long task…"))                            # survives a daemon bounce
# sessions also persist server-side: detach (fire-and-forget) and re-attach by id with the low-level client.
```

**Runnable:** [`examples/python-sdk/ex10_recovery.py`](../examples/python-sdk/ex10_recovery.py)

**Side by side.** Pydantic AI gives you **first-class observability** (Logfire's LLM-aware traces, token/cost panels — and since it's OTel, any backend) but leaves **durability to you**: the run lives in your process, and you persist `all_messages()` to resume. jaato inherits durability from the **daemon**: `IPCRecoveryClient` auto-reconnects and recovers an in-flight turn across a restart; sessions persist server-side and re-attach by id; OpenTelemetry tracing is a daemon flag. Plus what Pydantic AI has no analog for: each session runs in its **own AppArmor-confinable, workspace-scoped subprocess**.

---

## Coming from Pydantic AI

Not a scorecard — if you already think in Pydantic AI, here's what actually changes when you move to jaato, and what it buys you:

- **Typed output becomes a server-enforced gate.** `output_type=` validates in your process; jaato's `completion_payload_schema` validates *server-side* — the agent can't finish off-shape regardless of which client is attached. Same instinct, enforced at the boundary (you get a validated dict, not a typed object).
- **Your in-process agent can *stay* in-process — or become an isolated daemon session.** jaato runs the *same* agent **embedded** (`mode="in_process"`, like Pydantic AI) **or** as a confined per-session subprocess (`mode="ipc"`/`"ws"`) — so you keep the in-process simplicity *and* gain isolation, multi-tenancy, permissions, and crash-recovery when you want them, by flipping `mode`, not rewriting the agent.
- **You stop wiring the agent loop and cross-provider plumbing.** Any model (local GPUs included), built-in permissions + out-of-band HITL, and reactor-driven cascades are runtime features, not things you assemble.

**What to keep in mind (honest trade-offs).**
- Both sides are Python — a genuine same-language comparison.
- jaato needs a running daemon (auto-started here): a real dependency for a throwaway script; the point for a fleet of isolated, recoverable, multi-tenant agents.
- jaato hands you dicts + server-validated payloads, not Pydantic's in-process typed objects — less type-tight at the call site, stronger at the boundary. Both speak OpenTelemetry; jaato emits the same signals to a backend you choose, with no bundled UI.
- Pydantic AI moves quickly — verify `result.output`, deferred tools, and `pydantic-graph` against the version you install.
