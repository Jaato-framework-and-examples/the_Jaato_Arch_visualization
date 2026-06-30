# SDK usage, side by side: **LangChain** vs **jaato-sdk**

Ten worked examples, simplest first, each shown in **LangChain** (Python) and **jaato-sdk** (Python). The point isn't "which is fewer lines" — it's to make the *shape* of each SDK visible, because they sit in different categories:

- **LangChain** is an **in-process library**: you construct an `llm`/agent object and call it; everything runs inside your Python process. State, tools, isolation, and durability are yours to assemble.
- **jaato-sdk** is a **runtime you run two ways**: `jaato.session(mode=…)` runs the *same* agent **embedded in your process** (no daemon — like LangChain/LangGraph) **or** against a **long-lived daemon** (local `ipc`, auto-started if needed, or remote `ws`), where each agent runs in a confined, isolated, permission-gated per-session runner. Either way you open a **session** and `ask` it — the agent loop, tool execution, persistence, and permissions live in the **runtime**; the daemon adds isolation, multi-tenancy, and recovery.

Running behind the daemon is a real architectural option — but with the **convenience facade** (`jaato.session(mode=…)` → `s.ask` / `s.complete` / `s.stream`) it costs about **one line** (`async with`), not the page of event-plumbing it used to. So the basic examples are now close to LangChain in size, and the advanced ones (multi-agent, human approval, cascades, crash-recovery) come built-in rather than assembled. Read it as a trade, not a scoreboard.

> **Setup.** LangChain: `pip install langchain langchain-openai` (`langgraph` for the agent/HITL/durability examples). jaato: `import jaato` → `jaato.session(mode=…)` (errors via `from jaato_sdk import AgentError, PermissionUnhandled`). All jaato calls are `async`. The LangChain snippets use current LCEL / `langchain_openai` / LangGraph idioms (the API churns across majors — see the caveat at the end).

> **Two ways to run the *same* agent (three transports).** `jaato.session(mode=…)` runs the runtime **embedded in your process** (`mode="in_process"`, no daemon — the direct analog to how LangChain/LangGraph runs) **or** against a **daemon**: locally (`mode="ipc"`, what `IPCClient.session` does under the hood) or remotely over WebSocket (`mode="ws", url="wss://…", token=…`). The session spec and the `s.ask`/`complete`/`stream` facade are **identical**; `mode` is the only variable — the daemon modes add isolation, multi-tenancy, and crash-recovery (auto-reconnect via `session(recovery=True)` on either daemon mode — Example 10). **Examples 1–8 each run in-process** by flipping `mode` (identical spec + machinery, so the same agent and behaviour — parity validated at the prompt and event level); **recovery (Example 10)** is daemon-only by definition; **cascade (9)** is in-process-capable and landing (it needs the premium reactor engine wired).

`jaato.session(mode=…)` defaults the load-bearing knobs (`client_type=ClientType.API` so completion works headless, `env_file=".env"`, `auto_start=True`, `connect_timeout=120.0` for a cold autostart). It forwards `profile` / `agent` / `agent_params` / `cascade_driver_id` straight to `create_session`, so **both** the declarative style (`profile="researcher"`, named assets in `.jaato/`) and the programmatic style (`profile={"model": …, "provider": …, "plugins": []}` — an inline spec needs an explicit `plugins` key; `[]` = the minimal framework set) work. The runnable example profiles set two determinism knobs (kept out of the snippets below for brevity): **`"suppress_base_instructions": True`** — drop the operator/user-tier base prompt so the session is **lean, deterministic, and leak-proof** (identical in-process and via the daemon) — and, in the agentic examples (6, 7), **`"cli(preload)"`** in `plugins`, which forces the `cli` tool *eager* onto the wire (plain plugin names are lazy-discovered) so a multi-plugin session is deterministic in both modes. `ask`/`complete`/`stream` wait on the first of `{TURN_COMPLETED, SESSION_TERMINATED}` (so a plain turn never hangs) and **raise** on failure — `AgentError` on an error terminal, `PermissionUnhandled` if a gated tool goes unanswered — so there's no manual `if reason == "error"` bookkeeping. And the facade is **not all-or-nothing**: `s.client` exposes the underlying low-level client, so you can mix high-level `ask`/`complete`/`stream` with raw event-API calls — `s.client.subscribe(EventType.…)`, `s.client.cascade_events(...)`, `s.client.respond_to_permission(req_id, "e", edited_arguments={...})` (edit a tool's args before it runs) — on the **same session and connection** (listeners you add persist across turns). `ask`/`complete`/`stream` also take `attachments=[...]` for multimodal image/file inputs.

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
import asyncio, jaato

async def main():
    # mode="ipc" → the daemon; mode="in_process" → embedded, no daemon. Same call either way.
    async with jaato.session(mode="ipc",
            profile={"model": "gpt-4o", "provider": "openai", "plugins": []}) as s:
        print(await s.ask("Who are you? One sentence."))

asyncio.run(main())
```

**Runnable:** [`examples/python-sdk/ex01_basic_ask.py`](../examples/python-sdk/ex01_basic_ask.py) — run `… ipc` or `… in_process`

**Side by side.** LangChain is one in-process call. jaato-sdk opens an isolated session on a (possibly auto-started) daemon and `ask`s — one `async with` of overhead, not a page of `connect`/`subscribe`/`done.wait`. The daemon is still there; it just costs a line now.

## 2. Streaming the reply

**LangChain**
```python
for chunk in llm.stream("Tell me a short story."):
    print(chunk.content, end="", flush=True)
```

**jaato-sdk**
```python
async with jaato.session(mode="ipc", profile={"model": "gpt-4o", "provider": "openai", "plugins": []}) as s:
    async for chunk in s.stream("Tell me a short story."):
        print(chunk, end="", flush=True)
```

**Runnable:** [`examples/python-sdk/ex02_streaming.py`](../examples/python-sdk/ex02_streaming.py) — run `… ipc` or `… in_process`

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
async with jaato.session(mode="ipc", agent="pirate", profile={"model": "gpt-4o", "provider": "openai", "plugins": []}) as s:
    await s.ask("Hello")
    print(await s.ask("And your name?"))            # same session → it remembers
```

**Runnable:** [`examples/python-sdk/ex03_persona_memory.py`](../examples/python-sdk/ex03_persona_memory.py) — run `… ipc` or `… in_process`

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
async with jaato.session(mode="ipc", profile="person-extractor") as s:
    person = await s.complete("Alice is 30.")        # -> dict | None (server-validated payload)
    print(person["name"], person["age"])
```

**Runnable:** [`examples/python-sdk/ex04_typed_completion.py`](../examples/python-sdk/ex04_typed_completion.py) — run `… ipc` or `… in_process`

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

async with jaato.session(mode="ipc",
        profile={"model": "gpt-4o", "provider": "openai", "plugins": []},
        client_tools=[{
            "name": "get_weather", "description": "Return the weather for a city.",
            "parameters": {"type": "object",
                           "properties": {"city": {"type": "string"}}, "required": ["city"]},
            "handler": get_weather,
        }]) as s:
    print(await s.ask("Weather in Paris?"))
```

**Runnable:** [`examples/python-sdk/ex05_client_tool.py`](../examples/python-sdk/ex05_client_tool.py) *(named-fn variant — same SDK call shape)* — run `… ipc` or `… in_process`

**Side by side.** LangChain's `bind_tools` hands *you* the tool-call to execute. jaato-sdk's `register_client_tools` registers a schema **the daemon's agent loop invokes**, calling back into your process for the handler — the loop, retries, and result-threading happen server-side. (jaato can also use **server-side** tool plugins — `cli`, `web_search`, `file_edit` — by listing them in the profile's `plugins`, with no client code at all — see Example 6.)

## 6. Multi-tool agent loop (ReAct)

**LangChain** — you construct the agent that runs the loop:
```python
from langgraph.prebuilt import create_react_agent
agent = create_react_agent("openai:gpt-4o", tools=[get_weather, search, calculator])
agent.invoke({"messages": [("user", "Plan a trip to Paris.")]})   # loop runs in-process
```

**jaato-sdk** — the loop runs **in the session** (embedded or daemon); pick the plugin set and `ask`:
```python
async with jaato.session(mode="ipc", profile={"model": "gpt-4o", "provider": "openai", "plugins": ["cli(preload)", "web_search", "todo"]}) as s:
    print(await s.ask("Plan a trip to Paris and save it to trip.md"))
```

**Runnable:** [`examples/python-sdk/ex06_multitool.py`](../examples/python-sdk/ex06_multitool.py) — run `… ipc` or `… in_process`

**Side by side.** In LangChain *you* assemble and own the agent loop. In jaato the loop — model → tool calls (permission-checked, parallelizable) → results → model, until done — runs **wherever the session runs** — embedded (`mode="in_process"`) or the daemon's confined runner (`mode="ipc"`/`"ws"`); same loop, same result; the daemon adds per-session **sandbox isolation**, not different behaviour (so "the daemon runs the loop" is the wrong mental model — the *runtime* runs it); you choose the plugin set and `ask`. The loop is infrastructure, not your code.

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

async with jaato.session(mode="ipc",
        profile={"model": "gpt-4o", "provider": "openai", "plugins": ["cli(preload)"]},
        on_permission=approve) as s:
    print(await s.ask("Delete temp.log"))
```

**Runnable:** [`examples/python-sdk/ex07_permissions.py`](../examples/python-sdk/ex07_permissions.py) *(named-fn variant — same SDK call shape)* — run `… ipc` or `… in_process`

**Side by side.** In LangGraph HITL is *assembled* from a checkpointer + `interrupt_before` + manual resume. In jaato-sdk it's **first-class**: the daemon asks before a gated tool and your `on_permission(ev)` returns `"y"`/`"n"`/`"a"`/… (sync or async; may set `edited_arguments` via the low-level `respond_to_permission`). Omit the callback and a gated tool makes `s.ask()` raise `PermissionUnhandled` (the facade auto-denies to keep the daemon unstuck). For *headless* sessions the same escalation can route to an out-of-band approval **gate** (the reliability reactor) instead of prompting — see the resilience doc.

**The deeper link — pausing a *cascade* for out-of-band approval.** `on_permission` assumes a client is connected to answer. But in jaato, tool-failure escalations are **bus events**, so a **reactor** can handle them with *nothing connected*. The reliability pattern (resilience doc): a **headless cascade stage** (Example 9) keeps failing a tool → the reliability reactor escalates → a reactor **parks the call on a `HandoffGate`** and requests approval **out-of-band** — e.g. a chat/notifier service (via a webhook you wire) carrying the tool, its args, and which cascade stage asked → on **approve**, a second reactor flips deny→allow and **drives that same session's retry by id** — even if the runner was **unloaded** while waiting (it's reloaded by id, same session, no fork). So a long-running **cascade can pause mid-flight for a human and resume on approval**, hibernating in between — no client attached, no polling. And the pending approval (the **gate**) is durable: it survives a daemon restart, bounded by its TTL (an expired gate denies rather than hangs). LangGraph's `interrupt` does the same *shape*, but resumption runs in **your** process — you must be alive to call `.invoke(None, cfg)`; jaato's pause → approve → resume is **daemon-side, out-of-band, and durable**. (A deployment pattern — opt-in premium reactors + a gate + an approval webhook you wire, not client code; mechanism in the resilience doc.)

## 8. Multi-agent / subagent delegation

**LangChain (LangGraph)** — a **supervisor** that *dynamically* delegates to worker agents (`langgraph-supervisor`):
```python
from langgraph_supervisor import create_supervisor
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI

researcher = create_react_agent("openai:gpt-4o", tools=[web_search], name="researcher", prompt="Research topics.")
writer     = create_react_agent("openai:gpt-4o", tools=[], name="writer", prompt="Write blurbs.")
supervisor = create_supervisor(
    [researcher, writer], model=ChatOpenAI(model="gpt-4o"),
    prompt="You manage a researcher and a writer. Delegate to each as the task needs.",
).compile()
supervisor.invoke({"messages": [("user", "Write a blurb about tide pools.")]})   # supervisor routes via handoff tools
```

**jaato-sdk** — the supervisor's **persona** gives it a delegating *role* (its "soul" — how it behaves, **not** a task; the equivalent of the system prompt you'd give a LangGraph supervisor). The actual work arrives separately, as the **first prompt**. The delegation it triggers is **async + daemon-driven**, so the client drops to the event API. The persona:
```markdown
<!-- .jaato/agents/lead.md — role & behaviour, NOT a task -->
You are a coordinator. You get work done by delegating to specialist subagents
rather than doing it yourself: break the request into pieces, hand each to the
right specialist, and synthesise their results into the final answer.
```
The client opens the session and sends the **task** as the first prompt — the persona's role plus the `subagent` tools turn it into delegation:
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
    await done.wait()   # the daemon auto-continues 'lead' as each subagent COMPLETES;
                        # resolves only when 'lead' signal_completion's (the true end)
    print("".join(out))
```

**Runnable:** [`examples/python-sdk/ex08_subagent.py`](../examples/python-sdk/ex08_subagent.py) — run `… ipc` or `… in_process`

**Side by side.** Both are true **delegation** — one lead agent decides when to hand off. But the execution models differ sharply. LangGraph runs the supervisor graph **in your process**, blocking until it composes. jaato's is **async and daemon-driven**: the lead calls `spawn_subagent(profile=…, task=…)` and **ends its turn**; each specialist runs **server-side** (sharing the parent's runner — a per-subagent *isolated* runner + cgroup is designed but **not yet shipped**), and its result returns as a `[SUBAGENT … COMPLETED]` event that **the daemon uses to auto-continue the lead** on a later turn, until the lead composes and `signal_completion`s. Because that spans many turns, this is the one example that uses the **event API**: the facade's `ask`/`complete`/`stream` all return on the first `TURN_COMPLETED` (the spawn turn), so you wait on `s.client` for the final `SESSION_TERMINATED`. (The `lead`/`researcher`/`writer` personas live in `.jaato/agents/`, and the lead must be **completion-gated**. You can also orchestrate from the *client* instead — separate `ask()` calls passing output — when you'd rather own the control flow.) **How the lead knows to delegate, and to whom:** three inputs combine — the **persona** gives it the *role* (a coordinator that delegates rather than working directly), the **first prompt** carries the *task*, and the **`subagent` plugin** supplies the *means + targets*: the lead calls `list_subagent_profiles` (jaato's analog of a declared agent registry, discovered from `.jaato/profiles/`) to read each profile's name + description, then `spawn_subagent(profile="researcher", task=…)`. (The `agent=` persona axis is a *separate*, non-discovered selector. LangGraph's supervisor packs the same three inline: its `prompt` is the role, the `[researcher, writer]` list is the registry, and auto-generated handoff tools are the delegation.)

## 9. Multi-stage pipeline (chain vs cascade)

**LangChain** — an in-process LCEL pipeline:
```python
chain = extract_prompt | llm | parser | summarize_prompt | llm
chain.invoke({"doc": text})                           # synchronous data flow, your process
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

**Side by side.** A LangChain LCEL chain is **synchronous, in-process data flow you drive**. A jaato **cascade** is **event- and reactor-driven, server-side**: each stage is an **isolated headless session** that just `signal_completion`s 'done' — *ignorant of what comes next* — and a **reactor** reacts to that completion event and spawns the successor (threading the prior stage's typed payload into a freed warm slot). The client only triggers stage 1; the pipeline runs **decoupled in the daemon** — surviving the client disconnecting, each stage independently isolated, and you branch or fan out by adding **rules, not code**. The cascade machinery is **runtime-level** (the event bus + `create_session` live on the runtime), so the same chain can run **in-process** (`mode="in_process"`) when jaato-premium is installed and its reactor engine is registered — the daemon is just where it runs by default. *(A client `for`-loop over `s.complete` can sequence stages too — but that's **you** orchestrating in-process, which any framework does; the cascade proper is the **daemon** orchestrating on events. Production splits the hop into a two-event `agent.completed`→`slot.settled` handoff for warm-slot reuse.)* To *watch* a running cascade read-only, use the low-level event iterator — `async for ev in client.cascade_events(cid, event_types=[...], role="observer"): ...` — the *same* surface the facade exposes as `s.client`.

## 10. Production: persistence, recovery, observability

**LangChain (LangGraph)** — configure durable state + tracing:
```python
from langgraph.checkpoint.postgres import PostgresSaver
agent = create_react_agent("openai:gpt-4o", tools=tools, checkpointer=PostgresSaver(...))
# durable threads via thread_id; tracing via LangSmith (LANGCHAIN_TRACING_V2=true)
```

**jaato-sdk** — durability/recovery/tracing are daemon properties; `recovery=True` swaps in the auto-reconnect client on **either daemon transport**:
```python
import jaato
# recovery=True → IPCRecoveryClient (mode="ipc") or WSRecoveryClient (mode="ws"); not in_process (no daemon)
async with jaato.session(mode="ipc", recovery=True,
        profile="recovery-demo",          # a NAMED profile — see note below
        on_status_change=print) as s:     # prints reconnecting / connected / closed
    print(await s.ask("Long task…"))      # survives a daemon bounce
# sessions also persist server-side: detach (fire-and-forget) and re-attach by id with the low-level client.
```
> **Recovery needs a *named* profile.** The session record persists the profile **name** (+ workspace), not an inline spec — so the fresh daemon re-resolves the profile's `pass://` credential by name. An inline `profile={…}` has no name to recover from.

**Runnable:** [`examples/python-sdk/ex10_recovery.py`](../examples/python-sdk/ex10_recovery.py) *(named-fn variant — same SDK call shape)* — run `… ipc` or `… ws` (the two daemon transports)

**Side by side.** In LangGraph you *opt into* durability (a checkpointer backend) and tracing (LangSmith). jaato-sdk inherits them from the **daemon**: `session(recovery=True)` auto-reconnects and recovers an in-flight turn across a restart — on **either daemon transport** (`mode="ipc"` or `"ws"`; in-process has no daemon to recover); sessions persist server-side and can be detached and **re-attached by id**; OpenTelemetry/OpenInference tracing (to Arize Phoenix) is a daemon env-flag, not client code. Plus what has no LangChain analog: each session runs in an **AppArmor-confined, workspace-scoped subprocess**.

---

## Coming from LangChain / LangGraph

Not a scorecard — if you already think in LangChain/LangGraph, here's what actually changes when you move to jaato, and what it buys you:

- **Your LCEL chain / LangGraph `StateGraph` becomes a reactor-driven server-side cascade.** What you wire as `extract_prompt | llm | parser | …` (or a graph you drive in-process) jaato runs as **event- and reactor-driven** stages in the daemon: each stage is an isolated headless session that just `signal_completion`s 'done', and a **reactor** reacts and spawns the successor — threading the prior stage's typed payload in. You branch or fan out by adding **rules, not code**, and the pipeline survives the client disconnecting.
- **Supervisor delegation becomes daemon-driven subagents.** A `langgraph-supervisor` graph routes via handoff tools **in your process, blocking until it composes**; jaato's lead calls `spawn_subagent(profile=…, task=…)` and **ends its turn** — each specialist runs **server-side** and its completion event drives the daemon to auto-continue the lead, across turns, until it composes and `signal_completion`s. Same three inputs (role, registry, means), but execution is async and decoupled.
- **Typed output becomes a server-enforced completion gate.** `with_structured_output(Person)` validates the model's output *after the fact, in your process*; jaato's `completion_payload_schema` validates **server-side** — the agent must `signal_completion(payload)`, the daemon validates against the JSON schema (and runs completion processors), and a wrong-shape payload is bounced back to the model to retry. The agent can't "finish" malformed, regardless of which client is attached (you get a validated dict, not a typed object).
- **Your in-process agent can *stay* in-process — or become an isolated daemon session.** jaato runs the *same* agent **embedded** (`mode="in_process"`, like LangChain/LangGraph) **or** as a confined per-session subprocess (`mode="ipc"`/`"ws"`) — so you keep the in-process simplicity *and* gain isolation, multi-tenancy, permissions, and crash-recovery when you want them, by flipping `mode`, not rewriting the agent.
- **You stop assembling the agent loop, HITL, and durability — they're runtime features.** The ReAct loop (model → permission-checked, parallelized tool calls → results → model) runs **inside the confined runner**; permissions + out-of-band HITL are built in (an `on_permission` callback, or a reactor that parks a call on a durable `HandoffGate` and resumes by id with **nothing connected**); any model — local GPUs included — is provider-agnostic config; and durability/crash-recovery/OTel tracing are **daemon properties** (`session(recovery=True)` auto-reconnects on either daemon transport), not a checkpointer + LangSmith you opt into. Each session also runs in an **AppArmor-confined, workspace-scoped subprocess** — no LangChain analog.

**What to keep in mind (honest trade-offs).**
- **LangChain's API churns** across majors (LCEL, `langchain` 0.x→1.x, the LangGraph split). The snippets above use the current idioms as of early 2026; verify against the version you install.
- **jaato-sdk needs a running daemon** (auto-started here). For one throwaway call that's a real dependency the in-process libraries don't have; for a fleet of isolated, recoverable agents it's the point. The facade keeps the common path to one `async with`, and `s.client` drops to the full low-level API on the same session when you need it (custom event routing, the cascade observer) — a front door, not a wall. Scaffold a known-good client with `jaato-scaffold new client` (see doc 23).
- **Client memory — thin client vs. in-process.** A LangChain process accumulates the model client, conversation history, tool outputs, and any RAG/vector data in *your* process, so its RSS grows with the workload. The jaato-sdk client holds only the connection, its event subscriptions, and the text you collect — history, the agent loop, and tool execution run in the **daemon + the per-session runner subprocess**, so the client stays small and roughly flat (you can even detach the session and exit, then reattach by id). It's memory *relocation + isolation*, not less total RAM: the daemon, the per-session runners, and the **pre-warm pool of idle warm runners** all carry it server-side, so on one box total RAM can be *higher*. Each agent runs in its own subprocess (so a runaway agent can't bloat *your* client), and a runner **can** additionally be memory-capped — a cgroup `memory.max` from a per-session `memory_max_mb` — but that's **opt-in**: only when the daemon runs as a WS server with cgroups enabled (`JAATO_CGROUPS_ROOT`) and a limit is configured. IPC sessions (like every example here) get no cgroup, and `memory_max_mb` defaults unset. Biggest win when the client is constrained/edge, or you fan out many agents.
- **Dicts vs. objects.** Where LangChain hands you a typed Pydantic object (`with_structured_output`), jaato's `s.complete()` returns a **server-validated `dict | None`** — same validation guarantee, but you index `person["name"]`, not `person.name`.
- Apples-to-apples: both SDKs also ship **TypeScript** (`jaato-sdk-ts`, LangChain JS); these examples are Python for parity.
