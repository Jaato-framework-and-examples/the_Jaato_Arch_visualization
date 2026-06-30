# SDK usage, side by side: **Strands Agents** vs **jaato-sdk**

Ten worked examples, simplest first, each shown in **Strands Agents** and **jaato-sdk** — both in **Python**. The point isn't "which is fewer lines" — it's to make the *shape* of each SDK visible, because they sit in different categories:

- **Strands Agents** is a **model-driven, in-process Python SDK** (open-sourced by AWS; "any model, any cloud"): you give an `Agent` a system prompt and a list of tools, and the model drives its own reasoning/tool loop with minimal scaffolding. It runs in your process, defaults to Amazon Bedrock (but is model-agnostic), and ships rich **multi-agent primitives** — agents-as-tools, Swarm, Graph, Workflow.
- **jaato-sdk** is a **runtime you run two ways**: `jaato.session(mode=…)` runs the *same* agent **embedded in your process** (no daemon — like Strands) **or** against a **long-lived daemon** (local `ipc` or remote `ws`), where each agent is an isolated, permission-gated, per-session subprocess. Either way your code opens a **session** and `ask`s — the agent loop, tools, persistence, and permissions live in the **runtime**; the daemon adds isolation, multi-tenancy, and recovery.

So Strands gives you a minimal, model-first agent that lives in your process and composes into multi-agent topologies you assemble; jaato gives you a runtime/provider-agnostic agent that's the same agent you run in your process — *and* can move **behind a daemon boundary** for isolation and recovery when you want it, with server-enforced completion gates. Read it as a trade, not a scoreboard.

> **Setup.** Strands: `pip install strands-agents` (`strands-agents-tools` for the built-in toolset). jaato: `import jaato` → `jaato.session(mode=…)` (errors via `from jaato_sdk import AgentError, PermissionUnhandled`). All jaato calls are `async` (Strands agents are callable synchronously and via `invoke_async` / `stream_async`).

> **Two ways to run the *same* agent (three transports).** `jaato.session(mode=…)` runs the runtime **embedded in your process** (`mode="in_process"`, no daemon — the direct analog to how Strands runs) **or** against a **daemon**: locally (`mode="ipc"`, what `IPCClient.session` does under the hood) or remotely over WebSocket (`mode="ws", url="wss://…", token=…`). The session spec and the `s.ask`/`complete`/`stream` facade are **identical**; `mode` is the only variable — the daemon modes add isolation, multi-tenancy, and crash-recovery (auto-reconnect via `session(recovery=True)` on either daemon mode — Example 10). **Examples 1–8 each run in-process** by flipping `mode` (identical spec + machinery, so the same agent and behaviour — parity validated at the prompt and event level); **recovery (Example 10)** is daemon-only by definition; **cascade (9)** runs over the daemon transports (`ipc`/`ws`) — no in-process variant (the reactor engine is a daemon extension, not wired to the embedded runtime; the cascade's value *is* the daemon decoupling).

`jaato.session(mode=…)` defaults the load-bearing knobs (`client_type=ClientType.API` so completion works headless, `env_file=".env"`, `auto_start=True`, `connect_timeout=120.0`). It forwards `profile` / `agent` / `cascade_driver_id` to the session, so both the declarative style (`profile="researcher"`, named assets in `.jaato/`) and the programmatic style (`profile={"model": …, "provider": …, "plugins": []}` — an inline spec needs an explicit `plugins` key; `[]` = the minimal framework set) work. The runnable example profiles set two determinism knobs (kept out of the snippets below for brevity): **`"suppress_base_instructions": True`** — drop the operator/user-tier base prompt so the session is **lean, deterministic, and leak-proof** (identical in-process and via the daemon) — and, in the agentic examples (6, 7), **`"cli(preload)"`** in `plugins`, which forces the `cli` tool *eager* onto the wire (plain plugin names are lazy-discovered) so a multi-plugin session is deterministic in both modes. `ask`/`complete`/`stream` wait on the first of `{TURN_COMPLETED, SESSION_TERMINATED}` and **raise** on failure (`AgentError`, `PermissionUnhandled`). `s.client` exposes the underlying low-level client for mixing high- and low-level calls on one session.

---

## 1. Hello world — one prompt, one reply

**Strands Agents**
```python
from strands import Agent

agent = Agent(system_prompt="Be concise.")     # default model is Amazon Bedrock; pass model= for others
result = agent("Who are you? One sentence.")
print(result)                                   # AgentResult is stringable to the final text
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

**Side by side.** A Strands `Agent` is **callable** — `agent("…")` runs the model-driven loop **in your process** and returns an `AgentResult`. jaato `ask`s the same way — **in your process** (`mode="in_process"`) or **behind the daemon boundary** (`mode="ipc"`/`"ws"`, for isolation/recovery). Same `s.ask`; you choose where the agent runs.

## 2. Streaming the reply

**Strands Agents**
```python
async for event in agent.stream_async("Tell me a short story."):
    if "data" in event:
        print(event["data"], end="", flush=True)
```

**jaato-sdk**
```python
async with jaato.session(mode="ipc", profile={"model": "gpt-4o", "provider": "openai", "plugins": []}) as s:
    async for chunk in s.stream("Tell me a short story."):
        print(chunk, end="", flush=True)
```

**Runnable:** [`examples/python-sdk/ex02_streaming.py`](../examples/python-sdk/ex02_streaming.py) — run `… ipc` or `… in_process`

**Side by side.** Strands' `stream_async` yields **all** agent events — text deltas, tool usage, reasoning steps (with built-in cancellation); you filter for the text. jaato's `s.stream(...)` is an `AsyncIterable[str]` of model-output chunks that raises `AgentError`/`PermissionUnhandled` after it drains (the richer event stream is there too, via `s.client`).

## 3. System prompt + multi-turn memory

**Strands Agents** — a `SessionManager` persists the conversation:
```python
from strands import Agent
from strands.session import FileSessionManager

agent = Agent(system_prompt="You are a terse pirate.",
              session_manager=FileSessionManager(session_id="t1"))
agent("Hello")
print(agent("And your name?"))                  # same session → it remembers (persisted)
```

**jaato-sdk** — the **session is the memory**; the system prompt is a persona file:
```python
# persona lives in .jaato/agents/pirate.md (the system instructions), referenced by name:
async with jaato.session(mode="ipc", agent="pirate", profile={"model": "gpt-4o", "provider": "openai", "plugins": []}) as s:
    await s.ask("Hello")
    print(await s.ask("And your name?"))         # same session → it remembers
```

**Runnable:** [`examples/python-sdk/ex03_persona_memory.py`](../examples/python-sdk/ex03_persona_memory.py) — run `… ipc` or `… in_process`

**Side by side.** Strands keeps conversation in the `Agent`'s in-memory `messages`, optionally persisted by a pluggable `SessionManager` (File / S3 / Redis / Bedrock AgentCore Memory) and trimmed by a `ConversationManager`. jaato keeps state **in the daemon session**; a second `ask` continues it. A system prompt is a reusable **persona** (`agent="pirate"`), not constructor config.

## 4. Structured / typed output

**Strands Agents** — `structured_output` with a Pydantic model:
```python
from pydantic import BaseModel
class Person(BaseModel):
    name: str; age: int

person = agent.structured_output(Person, "Alice is 30.")    # a validated Person, in your process
print(person.name, person.age)
```

**jaato-sdk** — a typed **completion schema** the *server* enforces:
```python
# the "person-extractor" profile declares a completion_payload_schema (.jaato/completion_schemas/person.json)
async with jaato.session(mode="ipc", profile="person-extractor") as s:
    person = await s.complete("Alice is 30.")   # dict | None (server-validated payload)
    print(person["name"], person["age"])
```

**Runnable:** [`examples/python-sdk/ex04_typed_completion.py`](../examples/python-sdk/ex04_typed_completion.py) — run `… ipc` or `… in_process`

**Side by side.** Strands' `structured_output(Model, prompt)` constrains the model to a Pydantic schema and validates **in your process**, returning the typed object. jaato makes typed output a **server-side completion gate**: the agent must call `signal_completion(payload)`, the daemon validates it and bounces a wrong-shape payload back to the model to retry — the agent can't "finish" malformed, regardless of which client is connected. Under the hood both lean on **JSON Schema** at the model layer (Strands generates it from your Pydantic model; jaato authors it directly) and can use provider **strict / grammar-constrained decoding**; the difference is Strands validates with **Pydantic** in-process and hands you a **typed object**, while jaato validates **server-side with `jsonschema`** and hands you a **dict**.

## 5. A single tool / function call

**Strands Agents** — the `@tool` decorator on a Python function:
```python
from strands import Agent, tool

@tool
def get_weather(city: str) -> str:
    "Return the weather for a city."
    return f"{city}: sunny, 24C"

agent = Agent(tools=[get_weather])
print(agent("Weather in Paris?"))
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

**Side by side.** Strands derives the tool schema from the function's hints/docstring (`@tool`) and runs the call inline in your process (it also ships a `strands-agents-tools` package and speaks MCP). jaato's `client_tools` registers a schema **the daemon's agent loop invokes**, calling back into your client for the handler — the loop, retries, and result-threading happen server-side. (jaato can also use **server-side** plugins — `cli`, `web_search`, … — via the profile's `plugins`, with no client code; Example 6.)

## 6. Multi-tool agent loop

**Strands Agents** — give the agent several tools; the **model drives** the loop:
```python
agent = Agent(tools=[get_weather, search, calculator])
agent("Plan a trip to Paris.")      # model → tool calls → results → model, in your process
```

**jaato-sdk** — the loop runs **in the session** (embedded or daemon); pick the plugin set and `ask`:
```python
async with jaato.session(mode="ipc", profile={"model": "gpt-4o", "provider": "openai", "plugins": ["cli(preload)", "web_search", "todo"]}) as s:
    print(await s.ask("Plan a trip to Paris and save it to trip.md"))
```

**Runnable:** [`examples/python-sdk/ex06_multitool.py`](../examples/python-sdk/ex06_multitool.py) — run `… ipc` or `… in_process`

**Side by side.** Strands' whole premise is the **model-driven loop** — you supply tools and a prompt, the model plans and chains the calls **in your process** with minimal scaffolding. In jaato the loop — model → tool calls (permission-checked, parallelizable) → results → model — runs **wherever the session runs** — embedded (`mode="in_process"`) or the daemon's confined runner (`mode="ipc"`/`"ws"`); same loop, same result; the daemon adds per-session **sandbox isolation**, not different behaviour (so "the daemon runs the loop" is the wrong mental model — the *runtime* runs it); you choose the tools and `ask`. The loop is your dependency's code in one case, infrastructure in the other.

## 7. Human-in-the-loop tool approval

**Strands Agents** — a **hook** raises an **interrupt** before a tool runs:
```python
from strands.hooks import BeforeToolCallEvent

def approve_tools(event: BeforeToolCallEvent):
    if event.tool_use["name"] in SENSITIVE and not human_approves(event.tool_use):
        event.interrupt("denied by reviewer")     # pauses the agent loop for a human

agent = Agent(tools=[delete_file], hooks=[approve_tools])
agent("Delete temp.log")                           # the hook intercepts the gated tool call
```

**jaato-sdk** — permissions are built-in; pass an `on_permission` callback:
```python
async with jaato.session(mode="ipc",
        profile={"model": "gpt-4o", "provider": "openai", "plugins": ["cli(preload)"]},
        on_permission=lambda ev: "y" if approve(ev.tool_name) else "n") as s:
    print(await s.ask("Delete temp.log"))
```

**Runnable:** [`examples/python-sdk/ex07_permissions.py`](../examples/python-sdk/ex07_permissions.py) — run `… ipc` or `… in_process`

**Side by side.** Strands intercepts tool calls at the **agent-loop level** via its hook system — a `BeforeToolCallEvent` hook can raise an **interrupt** to pause for human approval and resume, all **in your process** (you handle the interrupt and continue). jaato's is **daemon-side**: `on_permission` answers inline, and for *headless* sessions the escalation is a **bus event** a reactor can park on a `HandoffGate`, ask a human **out-of-band** (a webhook bridge), then drive the same session's retry by id — pause→approve→resume with **no client attached** (see the resilience doc). Same shape; in-process-and-you-resume vs daemon-side-and-out-of-band.

## 8. Multi-agent / delegation

**Strands Agents** — **agents as tools**: pass specialist agents in the `tools` list:
```python
from strands import Agent

researcher = Agent(name="researcher", system_prompt="Research topics, return bullet notes.")
writer     = Agent(name="writer", system_prompt="Write blurbs from notes.")
lead = Agent(system_prompt="Delegate research, then writing.", tools=[researcher, writer])

print(lead("Write a blurb about tide pools."))     # the lead calls researcher/writer as tools
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

**Side by side.** Strands offers a *menu* of multi-agent patterns — **agents-as-tools** (a lead agent treats specialists as callable tools, shown here), **Swarm** (agents autonomously hand off), **Graph** (a deterministic directed graph of agents), and **Workflow** — all running **in your process**. jaato's delegation is **async and daemon-driven**: the lead persona calls `spawn_subagent(profile=…, task=…)` and **ends its turn**; each specialist runs **server-side** in its own context (a per-subagent isolated runner + cgroup is designed but not yet shipped), and its result returns as a `[SUBAGENT … COMPLETED]` event the daemon uses to auto-continue the lead until it composes and `signal_completion`s. Because that spans many turns, the facade one-shots don't fit — you wait on `s.client` for the final `SESSION_TERMINATED`. (How the lead knows the targets: its **persona** gives the *role*, the **first prompt** carries the *task*, and the `subagent` plugin's `list_subagent_profiles` discovers the available **profiles** from `.jaato/profiles/`.)

## 9. Multi-stage pipeline (graph vs cascade)

**Strands Agents** — a deterministic agent `Graph`:
```python
from strands.multiagent import GraphBuilder

builder = GraphBuilder()
builder.add_node(extract_agent, "extract")
builder.add_node(summarize_agent, "summarize")
builder.add_edge("extract", "summarize")        # extract → summarize
graph = builder.build()
graph("Summarize this document: …")
```

**jaato-sdk** — a real cascade is **event + reactor driven**, not a client loop. Each stage runs a **persona** (`agent=`, its soul) under a **profile**, and needs a **first message** (its task): the client supplies **stage 1**'s, and a **reactor** *injects* every later stage's from the prior stage's output (no human types it):
```python
import uuid
cid = uuid.uuid4().hex
async with jaato.session(mode="ipc", agent="extract", profile="extract",   # mode="ws" works too — cascade is daemon-only
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

**Runnable:** [`examples/python-sdk/ex09_cascade.py`](../examples/python-sdk/ex09_cascade.py) — run `… ipc` or `… ws` (the two daemon transports)

**Side by side.** Strands' `Graph` is a **deterministic, in-process orchestration you drive** (DAG or cyclic), with state flowing along the edges. A jaato **cascade** is **event- and reactor-driven, server-side**: each stage is an **isolated headless session** that just `signal_completion`s 'done' — *ignorant of what comes next* — and a **reactor** reacts to that completion event and spawns the successor (threading the prior stage's typed payload into a freed warm slot). The client only triggers stage 1; the pipeline then runs **decoupled in the daemon** — surviving the client disconnecting, each stage independently isolated/observable, and you branch or fan out by adding **rules, not code**. The cascade is a **daemon feature**: it runs over either daemon transport (`mode="ipc"` or `"ws"`, threading `cascade_driver_id` identically) but has **no in-process variant** — the reactor engine is a daemon extension (not wired to the embedded runtime), and the cascade's value *is* the daemon decoupling. *(A client `for`-loop over `s.complete` can sequence stages too — but that's **you** orchestrating in-process, which any framework does; the cascade proper is the **daemon** orchestrating on events. Production splits the hop into a two-event `agent.completed`→`slot.settled` handoff for warm-slot reuse — see the cascade docs.)*

## 10. Production: persistence, recovery, observability

**Strands Agents** — OpenTelemetry tracing + a `SessionManager` for persistence:
```python
from strands.telemetry import StrandsTelemetry
StrandsTelemetry().setup_otlp_exporter()        # trajectories → X-Ray / CloudWatch / Jaeger / Langfuse / …
# persistence: a SessionManager (File / S3 / Redis / AgentCore Memory) restores the conversation.
agent("Long task…")
```

**jaato-sdk** — durability/recovery/tracing are daemon properties; `recovery=True` swaps in the auto-reconnect client on **either daemon transport**:
```python
import jaato
# recovery=True → IPCRecoveryClient (mode="ipc") or WSRecoveryClient (mode="ws"); not in_process (no daemon)
async with jaato.session(mode="ipc", recovery=True,
        profile="recovery-demo",                              # a NAMED profile — see note below
        on_status_change=lambda st: print(st.state)) as s:    # reconnecting / connected / closed
    print(await s.ask("Long task…"))                          # survives a daemon bounce
# sessions also persist server-side: detach (fire-and-forget) and re-attach by id with the low-level client.
```
> **Recovery needs a *named* profile.** The session record persists the profile **name** (+ workspace), not an inline spec — so the fresh daemon re-resolves the profile's `pass://` credential by name. An inline `profile={…}` has no name to recover from.

**Runnable:** [`examples/python-sdk/ex10_recovery.py`](../examples/python-sdk/ex10_recovery.py) — run `… ipc` or `… ws` (the two daemon transports)

**Side by side.** Strands emits **OpenTelemetry** trajectories (every model/tool step) to any OTel backend (X-Ray, CloudWatch, Jaeger, Langfuse, …) and persists conversations via a pluggable `SessionManager` — durability and the run live **in your process / your chosen store**. jaato inherits durability from the **daemon**: `session(recovery=True)` auto-reconnects and recovers an in-flight turn across a restart — on **either daemon transport** (`mode="ipc"` or `"ws"`; in-process has no daemon to recover); sessions persist server-side and re-attach by id; OpenTelemetry tracing is a daemon flag. Plus what Strands runs in-process, jaato runs in its **own AppArmor-confinable, workspace-scoped subprocess**.

---

## Coming from Strands

Not a scorecard — if you already think in Strands, here's what actually changes when you move to jaato, and what it buys you:

- **`structured_output` becomes a server-enforced completion gate.** `agent.structured_output(Model, …)` constrains the model and validates with **Pydantic in your process**, handing back a typed object; jaato's `completion_payload_schema` makes the agent call `signal_completion(payload)`, the **daemon** validates it with `jsonschema` and bounces a wrong-shape payload back to the model to retry — the agent literally can't "finish" off-shape regardless of which client is attached. Same instinct, enforced at the boundary (you get a validated **dict**, not a typed object).
- **Your in-process callable `Agent` can *stay* in-process — or become an isolated daemon session.** jaato runs the *same* agent **embedded** (`mode="in_process"`, like Strands) **or** as a confined per-session subprocess (`mode="ipc"`/`"ws"`) — so you keep the in-process simplicity *and* gain isolation, multi-tenancy, permissions, and crash-recovery when you want them, by flipping `mode`, not rewriting the agent. State lives server-side under the daemon modes, a persona file (`agent="pirate"`) replaces constructor config, and it's **provider- and runtime-agnostic** (OpenAI / Anthropic / local GPUs), with no Bedrock default to override.
- **You stop wiring the agent loop and the multi-agent topologies yourself.** Strands' premise is that *you* assemble the loop and pick from a menu — agents-as-tools, **Swarm**, **Graph**, **Workflow** — all running in your process and driven by your code. In jaato the loop (model → permission-checked tool calls → results → model) is **infrastructure inside the confined runner**; delegation is **async + daemon-driven** (a supervisor persona `spawn_subagent`s and ends its turn, the daemon auto-continues it as each specialist completes); and a multi-stage pipeline isn't a `Graph` you drive but an **event- + reactor-driven cascade** — each stage an isolated headless session that just `signal_completion`s 'done', with reactors spawning the successor server-side. You branch and fan out by adding **rules, not code**, and the pipeline survives the client disconnecting.
- **Hooks/interrupts HITL becomes daemon-side permissions and out-of-band gates.** A Strands `BeforeToolCallEvent` hook raising an `interrupt()` pauses the loop **in your process** and you resume it; jaato's permissions are **built-in** — `on_permission` answers inline, and for *headless* sessions the escalation is a **bus event** a reactor parks on a `HandoffGate` to ask a human **out-of-band** (a webhook bridge), then drives the same session's retry by id — pause→approve→resume with **no client attached**. Durability and recovery come the same way: `session(recovery=True)` auto-reconnects across a daemon bounce (on either daemon transport), sessions persist server-side and re-attach by id.

**What to keep in mind (honest trade-offs).**
- Both sides are Python, so this is a genuine same-language move — no FFI or language switch to absorb.
- **jaato-sdk needs a running daemon** (auto-started here). For a single throwaway script that's a real dependency the in-process Strands SDK doesn't have; for a fleet of isolated, recoverable, multi-tenant agents it's the point. The facade keeps the common path to one `async with`.
- The runtime model genuinely differs: Strands runs **your** agent code (and tools) *in your process*; jaato runs agents as **isolated subprocesses** behind the daemon. That isolation is the win, but it's also the cost — there's a boundary (and a `client_tools` callback hop for host tools) where Strands just calls a function inline.
- **Strands is young and fast-moving** (open-sourced 2025, v1.0 in 2025). What you know today — `Agent(...)`, `stream_async`, `structured_output`, `@tool`, `SessionManager`, the hooks/interrupts HITL, `GraphBuilder` — may shift under you; verify exact signatures (especially the interrupts and multi-agent APIs) against the version you install. jaato's surface is the daemon contract, not a rapidly churning Python API.
- You trade **typed objects for dicts**. Strands' `structured_output` hands back a validated Pydantic instance; jaato hands back a server-validated **dict | None**. The guarantee moves to the boundary, but you lose the in-IDE typed-attribute ergonomics — re-wrap into your own model client-side if you want them back.
- **Observability shifts from in-process to a daemon flag.** Strands emits **OpenTelemetry** trajectories (every model/tool step) to any OTel backend — X-Ray, CloudWatch, Jaeger, Langfuse — and persists conversations via a pluggable `SessionManager` (File / S3 / Redis / AgentCore Memory), all living in *your* process and *your* chosen store. With jaato, durability and OTel tracing are **daemon properties** you turn on, not libraries you wire — less to assemble, but you observe and persist through the daemon's model rather than your own.
