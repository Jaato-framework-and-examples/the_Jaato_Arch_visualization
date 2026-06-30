# SDK usage, side by side: **OpenAI Agents SDK** vs **jaato-sdk**

Ten worked examples, simplest first, each shown in the **OpenAI Agents SDK** and **jaato-sdk** — both in **Python**. The point isn't "which is fewer lines" — it's to make the *shape* of each SDK visible, because they sit in different categories:

- **OpenAI Agents SDK** is a **lightweight, in-process Python library** for agentic and multi-agent workflows: you define an `Agent` (instructions + tools + handoffs) and run it with `Runner`, which drives the model/tool loop in your process. Its signature moves are **handoffs** (agents delegating to agents), **sessions**, **guardrails**, and built-in **tracing**. OpenAI-first, but it can drive other model providers.
- **jaato-sdk** is a **runtime you run two ways**: `jaato.session(mode=…)` runs the *same* agent **embedded in your process** (no daemon — like the OpenAI Agents SDK) **or** against a **long-lived daemon** (local `ipc` or remote `ws`), where each agent is an isolated, permission-gated, per-session subprocess. Either way your code opens a **session** and `ask`s — the agent loop, tools, persistence, and permissions live in the **runtime**; the daemon adds isolation, multi-tenancy, and recovery.

So the OpenAI SDK gives you a minimal, composable agent that lives in your process and coordinates other agents by handoff; jaato gives you a runtime/provider-agnostic agent — the same agent you run in your process — *and* can move **behind a daemon boundary** for isolation and recovery when you want it, with server-enforced completion gates. Read it as a trade, not a scoreboard.

> **Setup.** OpenAI Agents SDK: `pip install openai-agents` (`from agents import Agent, Runner, function_tool, SQLiteSession`). jaato: `import jaato` → `jaato.session(mode=…)` (errors via `from jaato_sdk import AgentError, PermissionUnhandled`). All jaato calls are `async`; `Runner.run` is async (`Runner.run_sync` for sync).

> **Two ways to run the *same* agent (three transports).** `jaato.session(mode=…)` runs the runtime **embedded in your process** (`mode="in_process"`, no daemon — the direct analog to how the OpenAI Agents SDK runs) **or** against a **daemon**: locally (`mode="ipc"`, what `IPCClient.session` does under the hood) or remotely over WebSocket (`mode="ws", url="wss://…", token=…`). The session spec and the `s.ask`/`complete`/`stream` facade are **identical**; `mode` is the only variable — the daemon modes add isolation, multi-tenancy, and crash-recovery (auto-reconnect via `IPCRecoveryClient` — Example 10). **Examples 1–8 each run in-process** by flipping `mode` (identical spec + machinery, so the same agent and behaviour — parity validated at the prompt and event level); **recovery (Example 10)** is daemon-only by definition; **cascade (9)** is in-process-capable and landing (it needs the premium reactor engine wired).

`jaato.session(mode=…)` defaults the load-bearing knobs (`client_type=ClientType.API` so completion works headless, `env_file=".env"`, `auto_start=True`, `connect_timeout=120.0`). It forwards `profile` / `agent` / `cascade_driver_id` to the session, so both the declarative style (`profile="researcher"`, named assets in `.jaato/`) and the programmatic style (`profile={"model": …, "provider": …, "plugins": []}` — an inline spec needs an explicit `plugins` key; `[]` = the minimal framework set) work. The runnable example profiles set two determinism knobs (kept out of the snippets below for brevity): **`"suppress_base_instructions": True`** — drop the operator/user-tier base prompt so the session is **lean, deterministic, and leak-proof** (identical in-process and via the daemon) — and, in the agentic examples (6, 7), **`"cli(preload)"`** in `plugins`, which forces the `cli` tool *eager* onto the wire (plain plugin names are lazy-discovered) so a multi-plugin session is deterministic in both modes. `ask`/`complete`/`stream` wait on the first of `{TURN_COMPLETED, SESSION_TERMINATED}` and **raise** on failure (`AgentError`, `PermissionUnhandled`). `s.client` exposes the underlying low-level client for mixing high- and low-level calls on one session.

---

## 1. Hello world — one prompt, one reply

**OpenAI Agents SDK**
```python
from agents import Agent, Runner

agent = Agent(name="assistant", instructions="Be concise.", model="gpt-4o")
result = await Runner.run(agent, "Who are you? One sentence.")
print(result.final_output)
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

**Side by side.** The OpenAI SDK splits the *agent* (config) from the *run* — `Runner.run(agent, …)` drives the loop **in your process** and returns a `RunResult` (`.final_output`). jaato `ask`s the same way — **in your process** (`mode="in_process"`) or **behind the daemon boundary** (`mode="ipc"`/`"ws"`, for isolation/recovery). Same `s.ask`; you choose where the agent runs.

## 2. Streaming the reply

**OpenAI Agents SDK**
```python
from openai.types.responses import ResponseTextDeltaEvent

result = Runner.run_streamed(agent, "Tell me a short story.")
async for event in result.stream_events():
    if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
        print(event.data.delta, end="", flush=True)
```

**jaato-sdk**
```python
async with jaato.session(mode="ipc", profile={"model": "gpt-4o", "provider": "openai", "plugins": []}) as s:
    async for chunk in s.stream("Tell me a short story."):
        print(chunk, end="", flush=True)
```

**Runnable:** [`examples/python-sdk/ex02_streaming.py`](../examples/python-sdk/ex02_streaming.py) — run `… ipc` or `… in_process`

**Side by side.** `Runner.run_streamed(...).stream_events()` yields a **typed event stream** — raw model deltas, run-item events (tool calls, handoffs), agent-updated events; you filter for the text deltas. jaato's `s.stream(...)` is an `AsyncIterable[str]` of model-output chunks that raises `AgentError`/`PermissionUnhandled` after it drains (the richer event stream is there too, via `s.client`).

## 3. System prompt + multi-turn memory

**OpenAI Agents SDK** — pass a `Session` to the runner:
```python
from agents import SQLiteSession

agent = Agent(name="pirate", instructions="You are a terse pirate.", model="gpt-4o")
session = SQLiteSession("conv-1")                 # in-memory; pass a file path to persist
await Runner.run(agent, "Hello", session=session)
print((await Runner.run(agent, "And your name?", session=session)).final_output)  # remembers
```

**jaato-sdk** — the **session is the memory**; the system prompt is a persona file:
```python
# persona lives in .jaato/agents/pirate.md (the system instructions), referenced by name:
async with jaato.session(mode="ipc", agent="pirate", profile={"model": "gpt-4o", "provider": "openai", "plugins": []}) as s:
    await s.ask("Hello")
    print(await s.ask("And your name?"))          # same session → it remembers
```

**Runnable:** [`examples/python-sdk/ex03_persona_memory.py`](../examples/python-sdk/ex03_persona_memory.py) — run `… ipc` or `… in_process`

**Side by side.** The OpenAI SDK makes memory an explicit `Session` you pass to each `Runner.run` (`SQLiteSession`/`SQLAlchemySession`/`RedisSession`/an OpenAI-native one), and it auto-stores/retrieves history. jaato keeps conversation state **in the daemon session**; a second `ask` continues it. A system prompt is a reusable **persona** (`agent="pirate"`), not constructor config.

## 4. Structured / typed output

**OpenAI Agents SDK** — an `output_type` Pydantic model:
```python
from pydantic import BaseModel
class Person(BaseModel):
    name: str; age: int

agent = Agent(name="x", instructions="Extract a person.", model="gpt-4o", output_type=Person)
result = await Runner.run(agent, "Alice is 30.")
print(result.final_output.name, result.final_output.age)   # final_output is a typed Person
```

**jaato-sdk** — a typed **completion schema** the *server* enforces:
```python
# the "person-extractor" profile declares a completion_payload_schema (.jaato/completion_schemas/person.json)
async with jaato.session(mode="ipc", profile="person-extractor") as s:
    person = await s.complete("Alice is 30.")   # dict | None (server-validated payload)
    print(person["name"], person["age"])
```

**Runnable:** [`examples/python-sdk/ex04_typed_completion.py`](../examples/python-sdk/ex04_typed_completion.py) — run `… ipc` or `… in_process`

**Side by side.** The OpenAI SDK validates against a Pydantic `output_type` **in your process** — the run isn't "final" until the model emits the typed object. jaato makes typed output a **server-side completion gate**: the agent must call `signal_completion(payload)`, the daemon validates it and bounces a wrong-shape payload back to the model to retry — regardless of which client is connected. Under the hood both lean on **JSON Schema** at the model layer (the OpenAI SDK generates it from your Pydantic model; jaato authors it directly) and can use provider **strict / grammar-constrained decoding**; the difference is the OpenAI SDK validates with **Pydantic** in-process and hands you a **typed object**, while jaato validates **server-side with `jsonschema`** and hands you a **dict**.

## 5. A single tool / function call

**OpenAI Agents SDK** — the `@function_tool` decorator:
```python
from agents import function_tool

@function_tool
def get_weather(city: str) -> str:
    "Return the weather for a city."
    return f"{city}: sunny, 24C"

agent = Agent(name="x", tools=[get_weather], model="gpt-4o")
print((await Runner.run(agent, "Weather in Paris?")).final_output)
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

**Side by side.** The OpenAI SDK derives the tool schema from your function's hints/docstring (`@function_tool`) and runs the call inline in your process (it also ships **hosted tools** — web search, file search, computer use — that run on OpenAI's side). jaato's `client_tools` registers a schema **the daemon's agent loop invokes**, calling back into your client for the handler — the loop, retries, and result-threading happen server-side. (jaato can also use **server-side** plugins — `cli`, `web_search`, … — via the profile's `plugins`, with no client code; Example 6.)

## 6. Multi-tool agent loop

**OpenAI Agents SDK** — give the agent several tools; the `Runner` loops:
```python
agent = Agent(name="planner", tools=[get_weather, search, calculator], model="gpt-4o")
await Runner.run(agent, "Plan a trip to Paris.")   # model → tool calls → results → model, in your process
```

**jaato-sdk** — the loop runs **in the session** (embedded or daemon); pick the plugin set and `ask`:
```python
async with jaato.session(mode="ipc", profile={"model": "gpt-4o", "provider": "openai", "plugins": ["cli(preload)", "web_search", "todo"]}) as s:
    print(await s.ask("Plan a trip to Paris and save it to trip.md"))
```

**Runnable:** [`examples/python-sdk/ex06_multitool.py`](../examples/python-sdk/ex06_multitool.py) — run `… ipc` or `… in_process`

**Side by side.** The OpenAI SDK's `Runner` runs the tool-calling loop **in your process** until the agent produces a final output (text with no tool calls). In jaato the loop — model → tool calls (permission-checked, parallelizable) → results → model — runs **wherever the session runs** — embedded (`mode="in_process"`) or the daemon's confined runner (`mode="ipc"`/`"ws"`); same loop, same result; the daemon adds per-session **sandbox isolation**, not different behaviour (so "the daemon runs the loop" is the wrong mental model — the *runtime* runs it); you choose the tools and `ask`. The loop is your dependency's code in one case, infrastructure in the other.

## 7. Human-in-the-loop tool approval

**OpenAI Agents SDK** — a tool with `needs_approval`; the run **pauses** as an interruption:
```python
@function_tool(needs_approval=True)
def delete_file(path: str) -> str: ...

agent = Agent(name="ops", tools=[delete_file], model="gpt-4o")
result = await Runner.run(agent, "Delete temp.log")
while result.interruptions:                        # ToolApprovalItem(s) pending
    state = result.to_state()                      # a serialisable, resumable run state
    for item in result.interruptions:
        state.approve(item) if human_ok(item) else state.reject(item)
    result = await Runner.run(agent, state)        # resume after the decision
print(result.final_output)
```

**jaato-sdk** — permissions are built-in; pass an `on_permission` callback:
```python
async with jaato.session(mode="ipc",
        profile={"model": "gpt-4o", "provider": "openai", "plugins": ["cli(preload)"]},
        on_permission=lambda ev: "y" if approve(ev.tool_name) else "n") as s:
    print(await s.ask("Delete temp.log"))
```

**Runnable:** [`examples/python-sdk/ex07_permissions.py`](../examples/python-sdk/ex07_permissions.py) — run `… ipc` or `… in_process`

**Side by side.** The OpenAI SDK's model is close in spirit: a `needs_approval` tool **pauses** the run and surfaces `ToolApprovalItem`s in `result.interruptions`; you capture a **resumable `RunState`** (`to_state()`), `approve`/`reject`, and re-run. It runs **in your process** — you hold the state and drive the resume (and `to_state()` can be serialised for an out-of-process UI). jaato's is **daemon-side**: `on_permission` answers inline, and for *headless* sessions the escalation is a **bus event** a reactor can park on a `HandoffGate`, ask a human **out-of-band** (a webhook bridge), then drive the same session's retry by id — pause→approve→resume with **no client attached** (see the resilience doc). Same shape; in-process-and-you-resume vs daemon-side-and-out-of-band.

## 8. Multi-agent / delegation

**OpenAI Agents SDK** — **handoffs**: an agent transfers control to a specialist:
```python
researcher = Agent(name="researcher", instructions="Research topics, return bullet notes.", model="gpt-4o")
writer     = Agent(name="writer", instructions="Write a blurb from notes.", model="gpt-4o")
lead = Agent(name="lead", model="gpt-4o",
             instructions="Hand off research to the researcher, then writing to the writer.",
             handoffs=[researcher, writer])         # the SDK adds transfer_to_* tools

print((await Runner.run(lead, "Write a blurb about tide pools.")).final_output)
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

**Side by side.** The OpenAI SDK's **handoffs** transfer *control* between agents — the lead exposes `transfer_to_researcher`/`transfer_to_writer` tools, the model decides when to hand off, and the receiving agent takes over the conversation, **all in your process**. jaato's delegation is **async and daemon-driven**: the lead persona calls `spawn_subagent(profile=…, task=…)` and **ends its turn**; each specialist runs **server-side** in its own context (a per-subagent isolated runner + cgroup is designed but not yet shipped), and its result returns as a `[SUBAGENT … COMPLETED]` event the daemon uses to auto-continue the lead until it composes and `signal_completion`s. Because that spans many turns, the facade one-shots don't fit — you wait on `s.client` for the final `SESSION_TERMINATED`. (How the lead knows the targets: its **persona** gives the *role*, the **first prompt** carries the *task*, and the `subagent` plugin's `list_subagent_profiles` discovers the available **profiles** from `.jaato/profiles/`.) The OpenAI SDK's handoff *transfers* control to one agent; jaato's lead *spawns* isolated subagents and synthesises — different shapes.

## 9. Multi-stage pipeline (code chain vs cascade)

**OpenAI Agents SDK** — there's no dedicated pipeline primitive; you **orchestrate in code** (or let the model drive it via handoffs):
```python
notes = (await Runner.run(researcher, "Research tide pools.")).final_output
draft = (await Runner.run(writer, f"Write a blurb from these notes:\n{notes}")).final_output
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

**Side by side.** The OpenAI SDK has **no pipeline object** — sequential work is either *you* chaining `Runner.run` calls in code, or the *model* routing via handoffs; both run **in your process**. A jaato **cascade** is **event- and reactor-driven, server-side**: each stage is an **isolated headless session** that just `signal_completion`s 'done' — *ignorant of what comes next* — and a **reactor** reacts to that completion and spawns the successor (threading the prior stage's typed payload into a freed warm slot). The client only triggers stage 1; the pipeline then runs **decoupled in the daemon** — surviving the client disconnecting, each stage independently isolated/observable, and you branch or fan out by adding **rules, not code**. The cascade machinery is **runtime-level** (the event bus + `create_session` live on the runtime), so the same chain can run **in-process** (`mode="in_process"`) when jaato-premium is installed and its reactor engine is registered — the daemon is just where it runs by default. *(A client `for`-loop over `s.complete` can sequence stages too — but that's **you** orchestrating in-process, which any framework does; the cascade proper is the **daemon** orchestrating on events. Production splits the hop into a two-event `agent.completed`→`slot.settled` handoff for warm-slot reuse — see the cascade docs.)*

## 10. Production: persistence, recovery, observability

**OpenAI Agents SDK** — built-in tracing + a `Session` backend, guardrails:
```python
# Tracing is ON by default → the OpenAI Traces dashboard; add trace processors to export to
# OTel / Langfuse / etc. Persistence is a Session (SQLite / SQLAlchemy / Redis); guardrails
# (input/output) run validation in parallel and fail fast.
await Runner.run(agent, "Long task…", session=SQLiteSession("c1", "conv.db"))
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

**Side by side.** The OpenAI SDK gives you **first-class tracing** (on by default, exportable via OTel) and pluggable **session** persistence + **guardrails** — but the run and durability live **in your process / your store**. jaato inherits durability from the **daemon**: `IPCRecoveryClient` auto-reconnects and recovers an in-flight turn across a restart; sessions persist server-side and re-attach by id; OpenTelemetry tracing is a daemon flag. Plus what the OpenAI SDK runs in-process, jaato runs in its **own AppArmor-confinable, workspace-scoped subprocess**.

---

## Coming from the OpenAI Agents SDK

Not a scorecard — if you already think in the OpenAI Agents SDK, here's what actually changes when you move to jaato, and what it buys you:

- **`output_type` becomes a server-enforced completion gate.** A Pydantic `output_type` validates the final output **in your process** — the run isn't "final" until the model emits the typed object. jaato's `completion_payload_schema` makes the agent call `signal_completion(payload)` and validates it *server-side* with `jsonschema`, bouncing a wrong-shape payload back to the model to retry — regardless of which client is attached. Same instinct, enforced at the boundary (you get a validated dict, not a typed `BaseModel`).
- **Your in-process `Runner` loop can *stay* in-process — or become an isolated daemon session.** `Runner.run` drives the model→tool→model loop **in your process** and hands back a `RunResult`; jaato runs the *same* agent **embedded** (`mode="in_process"`, like the OpenAI Agents SDK) **or** as a confined per-session subprocess (`mode="ipc"`/`"ws"`), where the loop — permission-checked, parallelizable tool calls — runs **inside a workspace-scoped, AppArmor-confinable subprocess** — so you keep the in-process simplicity *and* gain isolation, multi-tenancy, permissions, and crash-recovery when you want them, by flipping `mode`, not rewriting the agent. Conversation state isn't a `Session` you thread through every call; it *is* the daemon session, so a second `ask` just continues it, and a system prompt is a reusable **persona** file, not constructor config.
- **Handoffs become daemon-driven spawn-isolated-subagents and reactor cascades.** A handoff *transfers control* between agents (the SDK adds `transfer_to_*` tools and the receiving agent takes over the conversation, all in-process). jaato's lead persona instead calls `spawn_subagent(profile=…, task=…)` and **ends its turn**; each specialist runs server-side in its own context and returns a `[SUBAGENT … COMPLETED]` event the daemon uses to auto-continue the lead. Multi-stage work that you'd chain with `Runner.run` calls (or let the model route via handoffs) becomes an **event- and reactor-driven cascade**: each stage is an ignorant, isolated headless session that just signals 'done', and a reactor spawns the successor — you branch and fan out by adding **rules, not code**, and the pipeline survives the client disconnecting.
- **`needs_approval`/interruptions and tracing/Sessions become daemon properties.** A `needs_approval` tool pauses the run into `result.interruptions`; you capture a resumable `RunState`, `approve`/`reject`, and re-run — you hold the state and drive the resume. jaato answers inline via `on_permission`, but for *headless* sessions the escalation is a **bus event** a reactor can park on a `HandoffGate`, ask a human **out-of-band** (a webhook bridge), then drive the same session's retry by id — pause→approve→resume with **no client attached**. Likewise, tracing, durability, and persistence stop being your-process/your-store concerns: `IPCRecoveryClient` auto-reconnects and recovers an in-flight turn across a daemon restart, sessions persist server-side and re-attach by id, and OpenTelemetry is a daemon flag — and OpenAI-first becomes provider/runtime-agnostic, including local GPUs.

**What to keep in mind (honest trade-offs).**
- Both sides are Python, so this is a genuine same-language move — what changes is the runtime model, not the language.
- **The OpenAI Agents SDK is young and moving** (HITL/tool-approval landed recently). The snippets above use the current API (`Runner.run`/`run_streamed`, `final_output`, `output_type`, `@function_tool`, `Session`, `handoffs`, `needs_approval`/`interruptions`/`to_state`); verify exact signatures against the version you install. It's OpenAI-first, with non-OpenAI models reached through the provider/LiteLLM integrations — jaato is provider- and runtime-agnostic out of the gate.
- **jaato-sdk needs a running daemon** (auto-started here). For a single throwaway script that's a real dependency the in-process library doesn't have; for a fleet of isolated, recoverable, multi-tenant agents it's the whole point. The facade keeps the common path to one `async with`.
- Different runtime models: the OpenAI SDK runs **your** agent code (and tools) in your process; jaato runs agents as **isolated subprocesses** behind the daemon, so a tool/agent crash or memory blowup is contained server-side, not in your app.
