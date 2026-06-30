# SDK usage, side by side: **Agno** vs **jaato-sdk**

Ten worked examples, simplest first, each shown in **Agno** and **jaato-sdk** — both in **Python**. The point isn't "which is fewer lines" — it's to make the *shape* of each SDK visible, because they sit in different categories:

- **Agno** is a **high-performance, multi-agent Python framework**: you construct an `Agent` (or a `Team`) and call it; it runs in your process, with fast instantiation, built-in **sessions/memory/storage**, and first-class **Teams** (coordinate / route / collaborate). It also ships **AgentOS** — an optional runtime + control plane to run your agents as production services (tracing, scheduling, RBAC, per-user/session isolation).
- **jaato-sdk** is an **async client to a long-lived daemon**: agents run **server-side as isolated, permission-gated, per-session subprocesses**; your code is a thin client that opens a **session** and `ask`s. The agent loop, tools, isolation, persistence, and permissions live in the daemon.

So *both* have a "runtime" story, but a different one: AgentOS runs **your** agent code as a multi-tenant Python service; jaato's daemon runs agents as **isolated subprocesses you connect to** (provider- and runtime-agnostic, local-GPU-capable, AppArmor-confinable). Agno gives you a fast, batteries-included multi-agent toolkit in one process; jaato gives you isolated, recoverable agents behind a boundary with server-enforced completion gates. Read it as a trade, not a scoreboard.

> **Setup.** Agno: `pip install agno openai`. jaato: `import jaato` → `jaato.session(mode=…)` (errors via `from jaato_sdk import AgentError, PermissionUnhandled`). All jaato calls are `async` (Agno offers `run` (sync) and `arun` (async)).

> **Two ways to run the *same* agent (three transports).** `jaato.session(mode=…)` runs the runtime **embedded in your process** (`mode="in_process"`, no daemon — the direct analog to how Agno runs) **or** against a **daemon**: locally (`mode="ipc"`, what `IPCClient.session` does under the hood) or remotely over WebSocket (`mode="ws", url="wss://…", token=…`). The session spec and the `s.ask`/`complete`/`stream` facade are **identical**; `mode` is the only variable — the daemon modes add isolation, multi-tenancy, and crash-recovery (auto-reconnect via `IPCRecoveryClient` — Example 10). **Examples 1–8 each run in-process** by flipping `mode` (identical spec + machinery, so the same agent and behaviour — parity validated at the prompt and event level); **recovery (Example 10)** is daemon-only by definition; **cascade (9)** is in-process-capable and landing (it needs the premium reactor engine wired).

`jaato.session(mode=…)` forwards `profile` / `agent` / `cascade_driver_id` to the session, so both the declarative style (`profile="researcher"`, named assets in `.jaato/`) and the programmatic style (`profile={"model": …, "provider": …, "plugins": []}` — an inline spec needs an explicit `plugins` key; `[]` = the minimal framework set) work. The runnable example profiles set two determinism knobs (kept out of the snippets below for brevity): **`"suppress_base_instructions": True`** — drop the operator/user-tier base prompt so the session is **lean, deterministic, and leak-proof** (identical in-process and via the daemon) — and, in the agentic examples (6, 7), **`"cli(preload)"`** in `plugins`, which forces the `cli` tool *eager* onto the wire (plain plugin names are lazy-discovered) so a multi-plugin session is deterministic in both modes. `ask`/`complete`/`stream` wait on the first of `{TURN_COMPLETED, SESSION_TERMINATED}` and **raise** on failure (`AgentError`, `PermissionUnhandled`). `env_file` applies to every mode; `socket_path`/`auto_start` are IPC-only (ignored in-process).

---

## 1. Hello world — one prompt, one reply

**Agno**
```python
from agno.agent import Agent
from agno.models.openai import OpenAIChat

agent = Agent(model=OpenAIChat(id="gpt-4o"), instructions="Be concise.")
print(agent.run("Who are you? One sentence.").content)
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

**Side by side.** Agno constructs an `Agent` (model is an object — `OpenAIChat(id=…)`) and runs it **in your process**, returning a `RunOutput` (`.content` is the text; `agent.print_response(...)` pretty-prints). jaato `ask`s the same way — **in your process** (`mode="in_process"`) or **behind the daemon boundary** (`mode="ipc"`/`"ws"`, for isolation/recovery). Same `s.ask`; you choose where the agent runs.

## 2. Streaming the reply

**Agno**
```python
for event in agent.run("Tell me a short story.", stream=True):
    if event.content:
        print(event.content, end="", flush=True)
```

**jaato-sdk**
```python
async with jaato.session(mode="ipc", profile={"model": "gpt-4o", "provider": "openai", "plugins": []}) as s:
    async for chunk in s.stream("Tell me a short story."):
        print(chunk, end="", flush=True)
```

**Runnable:** [`examples/python-sdk/ex02_streaming.py`](../examples/python-sdk/ex02_streaming.py) — run `… ipc` or `… in_process`

**Side by side.** Agno's `run(stream=True)` yields a stream of **run events** (20+ types — content deltas, tool calls, reasoning, memory ops); you filter for content. jaato's `s.stream(...)` is an `AsyncIterable[str]` of model-output chunks that raises `AgentError`/`PermissionUnhandled` after it drains. Both stream; Agno surfaces a richer event taxonomy, jaato a plain text iterator (the events are there too, via `s.client`).

## 3. System prompt + multi-turn memory

**Agno** — built-in sessions + a storage backend:
```python
from agno.db.sqlite import SqliteDb

agent = Agent(model=OpenAIChat(id="gpt-4o"), instructions="You are a terse pirate.",
              db=SqliteDb(db_file="memory.db"), add_history_to_context=True)
agent.run("Hello", session_id="t1", user_id="u1")
print(agent.run("And your name?", session_id="t1", user_id="u1").content)   # same session → remembers
```

**jaato-sdk** — the **session is the memory**; the system prompt is a persona file:
```python
# persona lives in .jaato/agents/pirate.md (the system instructions), referenced by name:
async with jaato.session(mode="ipc", agent="pirate", profile={"model": "gpt-4o", "provider": "openai", "plugins": []}) as s:
    await s.ask("Hello")
    print(await s.ask("And your name?"))            # same session → it remembers
```

**Runnable:** [`examples/python-sdk/ex03_persona_memory.py`](../examples/python-sdk/ex03_persona_memory.py) — run `… ipc` or `… in_process`

**Side by side.** Agno makes memory an explicit, pluggable concern — a `db=` backend (SQLite/Postgres/…) keyed by `session_id`/`user_id`, with `add_history_to_context` to replay history and longer-term user memory. jaato keeps conversation state **in the daemon session**; a second `ask` continues it. A system prompt is a reusable **persona** (`agent="pirate"`), not constructor config.

## 4. Structured / typed output

**Agno** — a Pydantic `output_schema`:
```python
from pydantic import BaseModel
class Person(BaseModel):
    name: str; age: int

agent = Agent(model=OpenAIChat(id="gpt-4o"), output_schema=Person)
person = agent.run("Alice is 30.").content      # a validated Person, in your process
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

**Side by side.** Agno validates against a Pydantic model **in your process** (`output_schema` → `RunOutput.content` is the typed object). jaato makes typed output a **server-side completion gate**: the agent must call `signal_completion(payload)`, the daemon validates it and bounces a wrong-shape payload back to the model to retry — the agent can't "finish" malformed, regardless of which client is connected. Under the hood both lean on **JSON Schema** at the model layer (Agno generates it from your Pydantic model; jaato authors it directly) and can use provider **strict / grammar-constrained decoding**; the difference is Agno validates with **Pydantic** in-process and hands you a **typed object**, while jaato validates **server-side with `jsonschema`** and hands you a **dict**.

## 5. A single tool / function call

**Agno** — pass a plain Python function as a tool:
```python
def get_weather(city: str) -> str:
    "Return the weather for a city."
    return f"{city}: sunny, 24C"

agent = Agent(model=OpenAIChat(id="gpt-4o"), tools=[get_weather])
print(agent.run("Weather in Paris?").content)
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

**Side by side.** Agno derives the tool schema from the function's signature/docstring and runs the call inline in your process (it also ships pre-built **toolkits** for common integrations). jaato's `client_tools` registers a schema **the daemon's agent loop invokes**, calling back into your client for the handler — the loop, retries, and result-threading happen server-side. (jaato can also use **server-side** plugins — `cli`, `web_search`, … — via the profile's `plugins`, with no client code; Example 6.)

## 6. Multi-tool agent loop

**Agno** — give the agent several tools; it loops internally:
```python
agent = Agent(model=OpenAIChat(id="gpt-4o"), tools=[get_weather, search, calculator])
agent.run("Plan a trip to Paris.")      # model → tool calls → results → model, in your process
```

**jaato-sdk** — the loop runs **in the session** (embedded or daemon); pick the plugin set and `ask`:
```python
async with jaato.session(mode="ipc", profile={"model": "gpt-4o", "provider": "openai", "plugins": ["cli(preload)", "web_search", "todo"]}) as s:
    print(await s.ask("Plan a trip to Paris and save it to trip.md"))
```

**Runnable:** [`examples/python-sdk/ex06_multitool.py`](../examples/python-sdk/ex06_multitool.py) — run `… ipc` or `… in_process`

**Side by side.** Agno runs the tool-calling loop **inside `run`**, in your process, until the model returns a final answer. In jaato the loop — model → tool calls (permission-checked, parallelizable) → results → model — runs **wherever the session runs** — embedded (`mode="in_process"`) or the daemon's confined runner (`mode="ipc"`/`"ws"`); same loop, same result; the daemon adds per-session **sandbox isolation**, not different behaviour (so "the daemon runs the loop" is the wrong mental model — the *runtime* runs it); you choose the tools and `ask`. The loop is your dependency's code in one case, infrastructure in the other.

## 7. Human-in-the-loop tool approval

**Agno** — `requires_confirmation` pauses the run for a human:
```python
from agno.tools import tool

@tool(requires_confirmation=True)
def delete_file(path: str) -> str: ...

agent = Agent(model=OpenAIChat(id="gpt-4o"), tools=[delete_file])
run = agent.run("Delete temp.log")
if run.is_paused:                                  # a gated tool is awaiting confirmation
    for t in run.tools_requiring_confirmation:
        t.confirmed = ask_human(t)                 # True/False from your UI
    run = agent.continue_run(run)                  # resume after the decision
print(run.content)
```

**jaato-sdk** — permissions are built-in; pass an `on_permission` callback:
```python
async with jaato.session(mode="ipc",
        profile={"model": "gpt-4o", "provider": "openai", "plugins": ["cli(preload)"]},
        on_permission=lambda ev: "y" if approve(ev.tool_name) else "n") as s:
    print(await s.ask("Delete temp.log"))
```

**Runnable:** [`examples/python-sdk/ex07_permissions.py`](../examples/python-sdk/ex07_permissions.py) — run `… ipc` or `… in_process`

**Side by side.** Agno's `requires_confirmation` pauses the run and returns it with the pending tool calls; you gather decisions and `continue_run` — all **in your process** (you hold the run object and resume it). jaato's is **daemon-side**: `on_permission` answers inline, and for *headless* sessions the escalation is a **bus event** a reactor can park on a `HandoffGate`, ask a human **out-of-band** (a webhook bridge), then drive the same session's retry by id — pause→approve→resume with **no client attached** (see the resilience doc). Same shape; in-process-and-you-resume vs daemon-side-and-out-of-band.

## 8. Multi-agent / delegation

**Agno** — a **Team** with a coordination mode:
```python
from agno.team import Team

researcher = Agent(name="researcher", model=OpenAIChat(id="gpt-4o"), instructions="Research topics.")
writer     = Agent(name="writer", model=OpenAIChat(id="gpt-4o"), instructions="Write blurbs.")
team = Team(members=[researcher, writer], model=OpenAIChat(id="gpt-4o"), mode="coordinate")
print(team.run("Write a blurb about tide pools.").content)
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

**Side by side.** Agno makes multi-agent **first-class**: a `Team` of member agents with a `mode` — `coordinate` (a leader plans and delegates), `route` (a leader forwards to the best member), or `collaborate` (members work together) — all running **in your process**. jaato's delegation is **async and daemon-driven**: the lead persona calls `spawn_subagent(profile=…, task=…)` and **ends its turn**; each specialist runs **server-side** in its own context (a per-subagent isolated runner + cgroup is designed but not yet shipped), and its result returns as a `[SUBAGENT … COMPLETED]` event the daemon uses to auto-continue the lead until it composes and `signal_completion`s. Because that spans many turns, the facade one-shots don't fit — you wait on `s.client` for the final `SESSION_TERMINATED`. (How the lead knows the targets: its **persona** gives the *role*, the **first prompt** carries the *task*, and the `subagent` plugin's `list_subagent_profiles` discovers the available **profiles** from `.jaato/profiles/`.)

## 9. Multi-stage pipeline (workflow vs cascade)

**Agno** — a `Workflow` of `Step`s:
```python
from agno.workflow import Step, Workflow

wf = Workflow(name="extract-then-summarize", steps=[
    Step(name="extract", agent=extract_agent),
    Step(name="summarize", agent=summarize_agent),
])
print(wf.run(input=text).content)
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

**Side by side.** Agno's `Workflow` orchestrates `Step`s (each an agent, team, or function) **in your process** — an in-process orchestration you drive, the run's state flowing between steps. A jaato **cascade** is **event- and reactor-driven, server-side**: each stage is an **isolated headless session** that just `signal_completion`s 'done' — *ignorant of what comes next* — and a **reactor** reacts to that completion event and spawns the successor (threading the prior stage's typed payload into a freed warm slot). The client only triggers stage 1; the pipeline then runs **decoupled in the daemon** — surviving the client disconnecting, each stage independently isolated/observable, and you branch or fan out by adding **rules, not code**. The cascade machinery is **runtime-level** (the event bus + `create_session` live on the runtime), so the same chain can run **in-process** (`mode="in_process"`) when jaato-premium is installed and its reactor engine is registered — the daemon is just where it runs by default. *(A client `for`-loop over `s.complete` can sequence stages too — but that's **you** orchestrating in-process, which any framework does; the cascade proper is the **daemon** orchestrating on events. Production splits the hop into a two-event `agent.completed`→`slot.settled` handoff for warm-slot reuse — see the cascade docs.)*

## 10. Production: persistence, recovery, observability

**Agno** — a storage backend + OpenTelemetry, optionally **AgentOS**:
```python
import agno.observability        # OTel → Arize Phoenix / Langfuse / Logfire / SigNoz / …
# agents persist sessions/memory via db=SqliteDb/PostgresDb; deploy the whole app on AgentOS
# (a runtime + control plane: tracing, scheduling, RBAC, per-user/session isolation).
agent.run("Long task…")
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

**Side by side.** Agno gives you **broad OpenTelemetry** support (Phoenix, Langfuse, Logfire, SigNoz, … out of the box), pluggable **session/memory storage**, and — via **AgentOS** — a runtime that runs *your* agent app with per-user/session isolation and RBAC. jaato inherits durability from the **daemon**: `IPCRecoveryClient` auto-reconnects and recovers an in-flight turn across a restart; sessions persist server-side and re-attach by id; OpenTelemetry tracing is a daemon flag. The isolation model differs: AgentOS isolates *users/sessions within your Python service*; jaato runs each session in its **own AppArmor-confinable, workspace-scoped subprocess**.

---

## Coming from Agno

Not a scorecard — if you already think in Agno, here's what actually changes when you move to jaato, and what it buys you:

- **Your `output_schema` becomes a server-enforced completion gate.** Agno validates a Pydantic model *in your process* and hands you a typed object; jaato's `completion_payload_schema` validates *server-side* — the agent must `signal_completion(payload)`, the daemon bounces a wrong-shape payload back to the model to retry, and it can't "finish" malformed regardless of which client is attached. Same instinct, enforced at the boundary (you get a validated dict, not a typed object).
- **Your in-process agent can *stay* in-process — or become an isolated daemon session.** jaato runs the *same* agent **embedded** (`mode="in_process"`, like Agno) **or** as a confined per-session subprocess (`mode="ipc"`/`"ws"`) — so you keep the in-process simplicity *and* gain isolation, multi-tenancy, permissions, and crash-recovery when you want them, by flipping `mode`, not rewriting the agent.
- **Agno Teams and Workflows become daemon-driven delegation and reactor cascades.** A `Team(mode="coordinate"/"route"/"collaborate")` becomes a supervisor persona that `spawn_subagent`s and ends its turn, each specialist running server-side in its own context while the daemon auto-continues the lead. A `Workflow` of `Step`s becomes an event- and reactor-driven cascade: each stage is an isolated headless session that just `signal_completion`s 'done', ignorant of what comes next, while a reactor reacts to that event and spawns the successor — you branch and fan out by adding rules, not code, and the pipeline survives the client disconnecting.
- **AgentOS-in-your-process becomes a hostable, provider- and runtime-agnostic daemon.** Where AgentOS runs *your* Python agent app with per-user/session isolation and RBAC, jaato's daemon runs agents as isolated subprocesses you connect to — provider-agnostic, local-GPU-capable, crash-recoverable (`IPCRecoveryClient` auto-reconnects and recovers an in-flight turn across a daemon bounce; sessions persist and re-attach by id). Permissions and human-in-the-loop are built in: an `on_permission` callback answers inline, and headless sessions can escalate as a bus event a reactor parks on a `HandoffGate` — approved out-of-band via a webhook bridge, then resumed by id with no client attached.

**What to keep in mind (honest trade-offs).**
- Both sides are Python, so this is a genuine same-language comparison.
- jaato needs a **running daemon** (auto-started in these snippets). For a single throwaway script that's a real dependency the in-process framework doesn't have; for a fleet of isolated, recoverable, multi-tenant agents it's the point — and the facade keeps the common path to one `async with`.
- The runtime models differ: Agno runs **your** agent code and tools in your process (or in AgentOS, isolating users/sessions *within* that service); jaato runs each agent as an **isolated subprocess** behind the daemon, so a tool/agent crash or memory blowup is contained server-side, not in your app.
- **Agno moves quickly** — v2.0 (Sept 2025) was a full rewrite of `Agent`/`Team`/`Workflow`. The snippets here use the current v2 API (`output_schema`, `db=`, `add_history_to_context`, `Team(mode=…)`, `requires_confirmation`/`continue_run`); verify exact signatures — especially the HITL pause/continue and `Workflow`/`Step` APIs — against the version you install.
- You trade typed objects for dicts: jaato validates server-side with `jsonschema` and hands back a validated **dict**, not a Pydantic instance — so the in-process ergonomics of typed attribute access move to the daemon boundary.
- Observability shifts from a library to a daemon flag: Agno ships **broad OpenTelemetry** out of the box (Phoenix, Langfuse, Logfire, SigNoz, …) wired into your process; in jaato OTel tracing is a property of the daemon you point at, not something you import.
