# SDK usage, side by side: **LlamaIndex** vs **jaato-sdk**

Ten worked examples, simplest first, each shown in **LlamaIndex** (Python) and **jaato-sdk** (Python). The point isn't "which is fewer lines" — it's to make the *shape* of each SDK visible, because they sit in different categories:

- **LlamaIndex** is a **data framework for LLM apps, RAG-first**: its defining job is turning *your data* into indexes, retrievers, and query engines (`VectorStoreIndex`, `QueryEngine`, node parsers, 300+ readers). On top of that data layer sits an **agent** layer (`FunctionAgent` / `AgentWorkflow`) and an **event-driven `Workflow`** engine. Everything runs **in-process** in your Python program; state, isolation, durability, and multi-tenancy are yours to assemble. *(This comparison focuses on the agent / LLM-app surface — the part that lines up with jaato. Two scope clarifications: **(1)** LlamaIndex's **retrieval** pipeline — chunk → embed → vector-index → retrieve (`VectorStoreIndex`, query engines, node parsers) — has **no jaato analog**: jaato ships `filesystem_query` / `web_search` tool plugins, but it is not a document-ingestion or vector-retrieval framework. If your center of gravity is RAG over your own corpus, that's LlamaIndex's job. **(2)** But **multimodal document input** — handing an image or PDF *straight to a vision model* — is **not** retrieval, and jaato supports it too (`attachments=…`); the two are real peers there, so it gets its own side-by-side after Example 10.)*
- **jaato-sdk** is a **runtime you run two ways**: `jaato.session(mode=…)` runs the *same* agent **embedded in your process** (no daemon — like LlamaIndex's in-process agents) **or** against a **long-lived daemon** (local `ipc`, auto-started if needed, or remote `ws`), where each agent runs in a confined, isolated, permission-gated per-session runner. Either way you open a **session** and `ask` it — the agent loop, tool execution, persistence, and permissions live in the **runtime**; the daemon adds isolation, multi-tenancy, and recovery.

Running behind the daemon is a real architectural option — but with the **convenience facade** (`jaato.session(mode=…)` → `s.ask` / `s.complete` / `s.stream`) it costs about **one line** (`async with`), not a page of event-plumbing. So the basic examples are close to LlamaIndex in size, and the advanced ones (multi-agent, human approval, cascades, crash-recovery) come built-in rather than assembled. Read it as a trade, not a scoreboard.

> **Setup.** LlamaIndex: `pip install llama-index` (the meta-package; or `llama-index-core` + `llama-index-llms-openai` for just the LLM/agent surface below). jaato: `import jaato` → `jaato.session(mode=…)` (errors via `from jaato_sdk import AgentError, PermissionUnhandled`). All jaato calls are `async`. LlamaIndex's agent surface is also async (`await agent.run(...)`); the LLM calls have sync (`complete`) and async (`acomplete`) forms — the snippets mix them as each example reads most clearly.

> **The Doubleword angle.** Unlike the Vercel AI SDK (which gets a *first-party* `@doubleword/vercel-ai` provider), LlamaIndex reaches Doubleword through the **generic OpenAI-compatible seam** — the `OpenAILike` LLM pointed at Doubleword's endpoint:
> ```python
> from llama_index.llms.openai_like import OpenAILike
> llm = OpenAILike(model="Qwen/Qwen3.5-397B-A17B-FP8", api_base="https://api.doubleword.ai/v1",
>                  api_key=os.environ["JAATO_DOUBLEWORD_API_KEY"], is_chat_model=True,
>                  is_function_calling_model=True, context_window=131072)   # catalog reports no window → set it
> ```
> jaato reaches the *same* backend through its **`doubleword` provider** — `profile: { provider: "doubleword", model: "…", plugin_configs: { doubleword: { context_length: 131072, api_params: { service_tier: "flex" } } } }`. Note the two things you must supply on *both* sides: a **context window** (Doubleword's catalog reports none per-model) and — to get the discounted async tier — `service_tier="flex"` (jaato via the profile knob; LlamaIndex via `additional_kwargs={"service_tier": "flex"}` on the call). Every `OpenAI(model="gpt-4o")` in the snippets below is that one swap away from Doubleword.

> **Two ways to run the *same* agent (three transports).** `jaato.session(mode=…)` runs the runtime **embedded in your process** (`mode="in_process"`, no daemon — the direct analog to how LlamaIndex runs) **or** against a **daemon**: locally (`mode="ipc"`, what `IPCClient.session` does under the hood) or remotely over WebSocket (`mode="ws", url="wss://…", token=…`). The session spec and the `s.ask`/`complete`/`stream` facade are **identical**; `mode` is the only variable — the daemon modes add isolation, multi-tenancy, and crash-recovery. **Examples 1–8 each run in-process** by flipping `mode` (identical spec + machinery, same agent and behaviour); **recovery (Example 10)** is daemon-only by definition; **cascade (9)** runs over the daemon transports (`ipc`/`ws`) — no in-process variant today (the reactor engine is a daemon extension not wired to the embedded runtime; and the cascade's value *is* the daemon decoupling).

`jaato.session(mode=…)` defaults the load-bearing knobs (`client_type=ClientType.API` so completion works headless, `env_file=".env"`, `auto_start=True`, `connect_timeout=120.0` for a cold autostart). It forwards `profile` / `agent` / `agent_params` / `cascade_driver_id` straight to `create_session`, so **both** the declarative style (`profile="researcher"`, named assets in `.jaato/`) and the programmatic style (`profile={"model": …, "provider": …, "plugins": []}` — an inline spec needs an explicit `plugins` key; `[]` = the minimal framework set) work. `ask`/`complete`/`stream` wait on the first of `{TURN_COMPLETED, SESSION_TERMINATED}` (so a plain turn never hangs) and **raise** on failure — `AgentError` on an error terminal, `PermissionUnhandled` if a gated tool goes unanswered. And the facade is **not all-or-nothing**: `s.client` exposes the underlying low-level client, so you can mix high-level `ask`/`complete`/`stream` with raw event-API calls on the **same session and connection**.

---

## 1. Hello world — one prompt, one reply

**LlamaIndex**
```python
from llama_index.llms.openai import OpenAI

llm = OpenAI(model="gpt-4o")
print(llm.complete("Who are you? One sentence."))    # a CompletionResponse; str() → the text
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

**Side by side.** LlamaIndex constructs an `llm` and calls it — one in-process call. jaato-sdk opens an isolated session on a (possibly auto-started) daemon and `ask`s — one `async with` of overhead, not a page of plumbing. The daemon is still there; it just costs a line now.

## 2. Streaming the reply

**LlamaIndex**
```python
for chunk in llm.stream_complete("Tell me a short story."):
    print(chunk.delta, end="", flush=True)           # each chunk carries the incremental .delta
```

**jaato-sdk**
```python
async with jaato.session(mode="ipc", profile={"model": "gpt-4o", "provider": "openai", "plugins": []}) as s:
    async for chunk in s.stream("Tell me a short story."):
        print(chunk, end="", flush=True)
```

**Runnable:** [`examples/python-sdk/ex02_streaming.py`](../examples/python-sdk/ex02_streaming.py) — run `… ipc` or `… in_process`

**Side by side.** Both are iterators of text. LlamaIndex yields `CompletionResponse` chunks whose `.delta` is the new text; jaato's `s.stream(...)` yields ready-to-print string chunks (model output by default; `sources=None` for everything incl. tool narration) and stops at turn end, raising the same `AgentError`/`PermissionUnhandled` after draining.

## 3. System prompt + multi-turn memory

**LlamaIndex** — you thread `ChatMessage`s (or hand memory to a chat engine):
```python
from llama_index.core.llms import ChatMessage
history = [ChatMessage(role="system", content="You are a terse pirate."),
           ChatMessage(role="user", content="Hello")]
history.append(llm.chat(history).message)            # thread the reply back in
history.append(ChatMessage(role="user", content="And your name?"))
print(llm.chat(history).message.content)             # you carry the state
```

**jaato-sdk** — the **session is the memory**; the system prompt is a persona file:
```python
# persona lives in .jaato/agents/pirate.md (the system instructions), referenced by name:
async with jaato.session(mode="ipc", agent="pirate", profile={"model": "gpt-4o", "provider": "openai", "plugins": []}) as s:
    await s.ask("Hello")
    print(await s.ask("And your name?"))             # same session → it remembers
```

**Runnable:** [`examples/python-sdk/ex03_persona_memory.py`](../examples/python-sdk/ex03_persona_memory.py) — run `… ipc` or `… in_process`

**Side by side.** LlamaIndex threads the conversation through your own list (or you bolt on `ChatMemoryBuffer` / `SimpleChatEngine`, its managed-memory objects). jaato keeps history **in the daemon session** — two `s.ask()` calls in one `async with` just continue it — and a system prompt is a reusable **persona** (`agent="pirate"`), not an inline message re-sent each call.

## 4. Structured / typed output

**LlamaIndex** — a Pydantic class via `as_structured_llm`, validated client-side:
```python
from pydantic import BaseModel
class Person(BaseModel):
    name: str; age: int
person = llm.as_structured_llm(Person).complete("Alice is 30.").raw   # a validated Person, in your process
print(person.name, person.age)
```

**jaato-sdk** — a typed **completion schema** the *server* enforces:
```python
# the "person-extractor" profile declares completion_payload_schema -> .jaato/completion_schemas/person.json
async with jaato.session(mode="ipc", profile="person-extractor") as s:
    person = await s.complete("Alice is 30.")        # -> dict | None (server-validated payload)
    print(person["name"], person["age"])
```

**Runnable:** [`examples/python-sdk/ex04_typed_completion.py`](../examples/python-sdk/ex04_typed_completion.py) — run `… ipc` or `… in_process`

**Side by side.** LlamaIndex validates the model's output *after the fact, in your process* (`as_structured_llm(...).complete(...).raw`, a Pydantic instance; `output_cls=` does the same for agents). jaato makes typed output a **server-side completion gate**: the agent must call `signal_completion(payload)`, the daemon validates it against the JSON schema (and runs **completion processors**), and `s.complete()` returns only that validated `payload` (or `None`). A wrong-shape payload is bounced back to the model to retry — the agent can't "finish" malformed. (Author + check with `jaato-scaffold validate`.)

## 5. A single tool / function call

**LlamaIndex** — a `FunctionTool` handed to a `FunctionAgent`:
```python
from llama_index.core.tools import FunctionTool
from llama_index.core.agent.workflow import FunctionAgent

def get_weather(city: str) -> str:
    "Return the weather for a city."
    return f"{city}: sunny, 24C"

agent = FunctionAgent(tools=[FunctionTool.from_defaults(fn=get_weather)], llm=llm)
print(await agent.run("Weather in Paris?"))          # the agent runs the call in-process
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

**Side by side.** LlamaIndex wraps a Python function as a `FunctionTool` and the agent executes it **in your process**. jaato-sdk registers a schema **the daemon's agent loop invokes**, calling back into your process for the handler — the loop, retries, and result-threading happen server-side. (jaato can also use **server-side** tool plugins — `cli`, `web_search`, `file_edit` — by listing them in the profile's `plugins`, with no client code at all — see Example 6.)

## 6. Multi-tool agent loop (ReAct)

**LlamaIndex** — `FunctionAgent` runs the tool-calling loop until done:
```python
from llama_index.core.agent.workflow import FunctionAgent
agent = FunctionAgent(tools=[get_weather, search, calculator], llm=llm, system_prompt="Plan trips.")
print(await agent.run("Plan a trip to Paris."))       # loop runs in-process
```

**jaato-sdk** — the loop runs **in the session** (embedded or daemon); pick the plugin set and `ask`:
```python
async with jaato.session(mode="ipc", profile={"model": "gpt-4o", "provider": "openai", "plugins": ["cli(preload)", "web_search", "todo"]}) as s:
    print(await s.ask("Plan a trip to Paris and save it to trip.md"))
```

**Runnable:** [`examples/python-sdk/ex06_multitool.py`](../examples/python-sdk/ex06_multitool.py) — run `… ipc` or `… in_process`

**Side by side.** In LlamaIndex the `FunctionAgent` (or a hand-built `Workflow`) *is* the loop, running in your process. In jaato the loop — model → tool calls (permission-checked, parallelizable) → results → model, until done — runs **wherever the session runs** — embedded (`mode="in_process"`) or the daemon's confined runner (`mode="ipc"`/`"ws"`); same loop, same result; the daemon adds per-session **sandbox isolation**, not different behaviour. You choose the plugin set and `ask`. The loop is infrastructure, not your code.

## 7. Human-in-the-loop tool approval

**LlamaIndex** — stream the run and answer an `InputRequiredEvent` with a `HumanResponseEvent`:
```python
from llama_index.core.workflow import InputRequiredEvent, HumanResponseEvent
# a gated tool routes through ctx.wait_for_event(HumanResponseEvent, ...), surfacing an InputRequiredEvent:
handler = agent.run("Delete temp.log")
async for ev in handler.stream_events():
    if isinstance(ev, InputRequiredEvent):
        ok = input(f"{ev.prefix} ")                    # your out-of-band gate
        handler.ctx.send_event(HumanResponseEvent(response=ok))
print(await handler)
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

**Side by side.** In LlamaIndex HITL is a **Workflow** concern: a step (or tool) `wait_for_event`s, emitting an `InputRequiredEvent` you answer with a `HumanResponseEvent` on the run handler's context (and you can break out and resume later, persisting the context). In jaato-sdk it's **first-class on any agent turn**: the daemon asks before a gated tool and your `on_permission(ev)` returns `"y"`/`"n"`/`"a"`/… (sync or async; may set `edited_arguments` via the low-level `respond_to_permission`). Omit the callback and a gated tool makes `s.ask()` raise `PermissionUnhandled` (the facade auto-denies to keep the daemon unstuck). For *headless* sessions the same escalation can route to an out-of-band approval **gate** (the reliability reactor) instead of prompting — see the resilience doc.

**The deeper link — pausing a *cascade* for out-of-band approval.** `on_permission` assumes a client is connected to answer. But in jaato, tool-failure escalations are **bus events**, so a **reactor** can handle them with *nothing connected*. The reliability pattern (resilience doc): a **headless cascade stage** (Example 9) keeps failing a tool → the reliability reactor escalates → a reactor **parks the call on a `HandoffGate`** and requests approval **out-of-band** — e.g. a chat/notifier service (via a webhook you wire) carrying the tool, its args, and which cascade stage asked → on **approve**, a second reactor flips deny→allow and **drives that same session's retry by id** — even if the runner was **unloaded** while waiting (it's reloaded by id, same session, no fork). So a long-running **cascade can pause mid-flight for a human and resume on approval**, hibernating in between — no client attached, no polling. And the pending approval (the **gate**) is durable: it survives a daemon restart, bounded by its TTL (an expired gate denies rather than hangs). LlamaIndex's `InputRequiredEvent`/`HumanResponseEvent` does the same *shape* — and it, too, can serialize the context and resume later — but resumption runs in **your** process: you must reload that context and drive the run; jaato's pause → approve → resume is **daemon-side, out-of-band, and durable**. (A deployment pattern — opt-in premium reactors + a gate + an approval webhook you wire, not client code; mechanism in the resilience doc.)

## 8. Multi-agent / subagent delegation

**LlamaIndex** — an `AgentWorkflow` of agents that **hand off** to each other:
```python
from llama_index.core.agent.workflow import FunctionAgent, AgentWorkflow
researcher = FunctionAgent(name="researcher", description="Researches topics.",
                           system_prompt="Research topics.", llm=llm, tools=[web_search],
                           can_handoff_to=["writer"])
writer     = FunctionAgent(name="writer", description="Writes blurbs from findings.",
                           system_prompt="Write blurbs.", llm=llm, tools=[])
workflow = AgentWorkflow(agents=[researcher, writer], root_agent="researcher")
print(await workflow.run("Research tide pools, then write a blurb."))   # agents hand off in-process
```

**jaato-sdk** — the supervisor's **persona** gives it a delegating *role* (its "soul" — how it behaves, **not** a task; the equivalent of a `system_prompt` on a LlamaIndex agent). The actual work arrives separately, as the **first prompt**. The delegation it triggers is **async + daemon-driven**, so the client drops to the event API. The persona:
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

**Side by side.** Both are true **delegation** — one lead agent decides when to hand off. But the execution models differ sharply. LlamaIndex runs the `AgentWorkflow` **in your process**, handing off between agents (a shared `Context` carries state), blocking until it composes. jaato's is **async and daemon-driven**: the lead calls `spawn_subagent(profile=…, task=…)` and **ends its turn**; each specialist runs **server-side** (sharing the parent's runner — a per-subagent *isolated* runner + cgroup is designed but **not yet shipped**), and its result returns as a `[SUBAGENT … COMPLETED]` event that **the daemon uses to auto-continue the lead** on a later turn, until the lead composes and `signal_completion`s. Because that spans many turns, this is the one example that uses the **event API**: the facade's `ask`/`complete`/`stream` all return on the first `TURN_COMPLETED` (the spawn turn), so you wait on `s.client` for the final `SESSION_TERMINATED`. **How the lead knows to delegate, and to whom:** three inputs combine — the **persona** gives it the *role* (a coordinator that delegates rather than working directly), the **first prompt** carries the *task*, and the **`subagent` plugin** supplies the *means + targets*: the lead calls `list_subagent_profiles` (jaato's analog of the agent registry, discovered from `.jaato/profiles/`) to read each profile's name + description, then `spawn_subagent(profile="researcher", task=…)`. (LlamaIndex's `AgentWorkflow` packs the same three inline: each agent's `system_prompt` is its role, the `agents=[…]` list + `description`s are the registry, and `can_handoff_to` wires the delegation — all resolved and run in one process.)

## 9. Multi-stage pipeline (workflow vs cascade)

**LlamaIndex** — an event-driven `Workflow`: `@step` methods consume and emit typed `Event`s:
```python
from llama_index.core.workflow import Workflow, StartEvent, StopEvent, Event, step

class Facts(Event):
    facts: str

class Pipeline(Workflow):
    @step
    async def extract(self, ev: StartEvent) -> Facts:
        return Facts(facts=str(await llm.acomplete(f"Extract the facts from this doc: {ev.doc}")))
    @step
    async def summarize(self, ev: Facts) -> StopEvent:
        return StopEvent(result=str(await llm.acomplete(f"Summarise these findings: {ev.facts}")))

print(await Pipeline().run(doc=text))                 # event-driven — but ONE process, you drive run()
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

**Side by side.** This is the closest architectural cousin of any framework here — LlamaIndex's `Workflow` is genuinely **event-driven** (steps consume/emit typed `Event`s, dispatched by an in-process event loop), which is the *same idea* as a jaato cascade. The difference is the **locus**: a LlamaIndex `Workflow` runs **in one process, driven by `w.run()`** — the steps are methods on one object sharing one `Context`, and if that process dies the run dies. A jaato **cascade** is **event- and reactor-driven, server-side and decoupled**: each stage is an **isolated headless session** that just `signal_completion`s 'done' — *ignorant of what comes next* — and a **reactor** reacts to that completion event and spawns the successor (threading the prior stage's typed payload into a freed warm slot). The client only triggers stage 1; the pipeline runs **decoupled in the daemon** — surviving the client disconnecting, each stage independently isolated (its own runner/workspace), and you branch or fan out by adding **rules, not code**. So: same event-driven spirit, but LlamaIndex's events flow between *methods in your process* while jaato's flow between *isolated sessions in a daemon*. *(A client `for`-loop over `s.complete` can sequence stages too — the direct analog of driving `Workflow.run()` — but that's **you** orchestrating in-process; the cascade proper is the **daemon** orchestrating on events. Production splits the hop into a two-event `agent.completed`→`slot.settled` handoff for warm-slot reuse.)*

## 10. Production: persistence, recovery, observability

**LlamaIndex** — serialize the workflow `Context` for durability; instrument for tracing:
```python
from llama_index.core.workflow import Context, JsonSerializer
handler = workflow.run(doc=text)
ctx_dict = handler.ctx.to_dict(serializer=JsonSerializer())    # persist THIS yourself (your DB/file)
# … later, in a fresh process, resume from the saved state:
restored = Context.from_dict(workflow, ctx_dict, serializer=JsonSerializer())

import llama_index.core
llama_index.core.set_global_handler("arize_phoenix")           # OpenInference spans → Arize Phoenix / OTel
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

**Side by side.** In LlamaIndex you *opt into* durability (serialize the `Context` and resume it in a fresh process — **you** own the store and the re-drive) and tracing (a global handler / OpenInference instrumentation). jaato-sdk inherits both from the **daemon**: `session(recovery=True)` auto-reconnects and recovers an *in-flight* turn across a restart — on **either daemon transport** — with no context you serialize by hand; sessions persist server-side and re-attach by id. Notably, **both target the same observability stack** — OpenInference spans to Arize Phoenix — but LlamaIndex wires it *in your app* while jaato's is a **daemon env-flag** (doc 17), zero client code. Plus what has no LlamaIndex analog: each session runs in an **AppArmor-confined, workspace-scoped subprocess**.

---

## Bonus axis: multimodal input (images & PDFs)

LlamaIndex is the **document / multimodal** framework of this set, so it's worth showing the one document-handling axis where jaato is a genuine peer: sending an **image or PDF directly to a vision-capable model** — no retrieval, no index, the file *is* the input. Both SDKs support it; the earlier "RAG has no jaato analog" line is about *retrieval*, not this.

**LlamaIndex** — typed content blocks on a `ChatMessage`:
```python
from llama_index.core.llms import ChatMessage, TextBlock, ImageBlock, DocumentBlock
llm = OpenAI(model="gpt-4o")                          # a vision-capable model
resp = llm.chat([ChatMessage(role="user", blocks=[
    TextBlock(text="What's in this chart? Summarise the PDF."),
    ImageBlock(path="chart.png"),
    DocumentBlock(path="report.pdf", document_mimetype="application/pdf"),
])])
print(resp.message.content)
```

**jaato-sdk** — `attachments=` on any `ask` / `complete` / `stream`:
```python
async with jaato.session(mode="ipc",
        profile={"model": "gpt-4o", "provider": "openai", "plugins": []}) as s:   # vision-capable model
    print(await s.ask("What's in this chart? Summarise the PDF.",
                      attachments=["chart.png", "report.pdf"]))   # file paths → base64'd client-side
# each item may instead be a dict: {"mime_type": "application/pdf", "data": <bytes|base64>, "display_name": "report.pdf"}
```

**Side by side.** Same capability, different shape. LlamaIndex models the message as a list of typed **content blocks** (`ImageBlock` / `DocumentBlock` with an explicit `document_mimetype`) you assemble. jaato takes a flat `attachments=` list — a **file path** (bytes read, mime guessed from the extension, base64-encoded *client-side*, so a remote `ws` daemon never needs your filesystem) or a `{mime_type, data, display_name}` dict — and delivers it to the provider's multimodal path. Two shared caveats: **(1)** it only works on a **vision/PDF-capable model** — in jaato that's gated by the provider's declared **input modalities** (catalog-detected, or asserted via the provider's `modalities` knob; for **Doubleword** you *must* assert vision through `plugin_configs.doubleword.modalities`, since its catalog classifies none), and in LlamaIndex by whether the LLM + `document_mimetype` combo is wired (`DocumentBlock` isn't supported on every model path). **(2)** This is the **non-RAG** route — the whole file lands in the context window; for a large corpus you'd still reach for LlamaIndex's retrieval, the part jaato doesn't do. jaato also supports the *reverse* direction, with no LlamaIndex analog: a **tool result** can carry image/PDF `attachments` *back* to the model (a tool that renders a chart, screenshots a page, returns a generated PDF).

---

## Coming from LlamaIndex

Not a scorecard — if you already think in LlamaIndex, here's what actually changes when you move to jaato, and what it buys you:

- **RAG-*retrieval* stays LlamaIndex's job — but multimodal input doesn't.** LlamaIndex's *retrieval* core — data → indexes → retrievers → query engines — has **no** jaato equivalent (its `filesystem_query` / `web_search` plugins are tools an agent calls, not an ingestion/retrieval framework); the realistic pattern is *both*: keep LlamaIndex's retrievers for RAG and expose retrieval to a jaato agent as a **client tool** (Example 5) or a server-side plugin. Don't over-scope that, though: **direct image/PDF input to a vision model** is *not* retrieval, and jaato does it via `attachments=` (the bonus section) — so "LlamaIndex handles documents, jaato doesn't" is true only for the *retrieval* half, not the multimodal one.
- **Your `as_structured_llm` / `output_cls` becomes a server-enforced completion gate.** In LlamaIndex you validate the model's reply *in your process* into a Pydantic object. jaato moves that to the boundary: a profile's `completion_payload_schema` is checked *server-side* — the agent must `signal_completion(payload)`, the daemon validates it (and runs completion processors), and `s.complete()` hands you the validated payload or `None`. A wrong-shape payload is bounced back to the model to retry; the agent can't "finish" off-shape, no matter which client is attached (you get a `dict`, not a typed object — see the trade-offs).
- **Your in-process `FunctionAgent` can *stay* in-process — or become an isolated daemon session.** jaato runs the *same* agent **embedded** (`mode="in_process"`, like a LlamaIndex agent) **or** as a confined per-session subprocess (`mode="ipc"`/`"ws"`) — so you keep the in-process simplicity *and* gain isolation, multi-tenancy, permissions, and crash-recovery when you want them, by flipping `mode`, not rewriting the agent. The conversation *is* the session (a second `s.ask` continues it), and the system prompt is a reusable **persona** (`agent="pirate"`) instead of a constructor arg.
- **Your `AgentWorkflow` handoffs become daemon-driven subagents.** A LlamaIndex `AgentWorkflow` routes between agents **in your process**, blocking until it composes. jaato's lead calls `spawn_subagent(profile=…, task=…)` and **ends its turn** — each specialist runs **server-side** and its completion event drives the daemon to auto-continue the lead, across turns, until it composes and `signal_completion`s. Same three inputs (role, registry, means), but execution is async and decoupled.
- **Your event-driven `Workflow` becomes an event-driven *cascade* — same idea, different locus.** This is the sharpest mapping: LlamaIndex `@step`/`Event` dispatch and a jaato cascade are both event-driven, but LlamaIndex's events flow between **methods in one process you drive with `run()`**, while jaato's flow between **isolated headless sessions in a daemon**, wired by **reactors** (`.jaato/reactors/`), surviving the client disconnecting and isolating each stage. You branch or fan out by adding **rules, not code**, and durable HITL gates let a stage pause for a human and resume by id even if its runner was unloaded.

**What to keep in mind (honest trade-offs).**
- **Same language, both Python** — so none of the change above is "switch languages," it's "move the agent across a boundary" (or keep it in-process via `mode="in_process"`). Both also ship TypeScript SDKs (LlamaIndex.TS, `@jaato/sdk`); these examples are Python for parity.
- **jaato-sdk needs a running daemon** (auto-started here for `ipc`). For one throwaway call that's a real dependency the in-process library doesn't have; for a fleet of isolated, recoverable agents it's the point. The facade keeps the common path to one `async with`, and `s.client` drops to the full low-level API on the same session when you need it. Scaffold a known-good client with `jaato-scaffold new client` (doc 23).
- **LlamaIndex's API has churned** — the v0.10 namespace split (`llama-index-core` + integration packages), and the agent surface moving from `OpenAIAgent`/`ReActAgent.from_tools(...)` to today's `FunctionAgent` / `AgentWorkflow` / `Workflow`. The snippets use the current agent-workflow idioms; verify against the version you install.
- **Dicts vs. objects.** Where LlamaIndex hands you a typed Pydantic object (`as_structured_llm(...).raw`), jaato's `s.complete()` returns a **server-validated `dict | None`** — same validation guarantee, but you index `person["name"]`, not `person.name`.
- **Reaching Doubleword differs by seam.** LlamaIndex has **no first-party Doubleword package** (unlike the Vercel AI SDK); you point `OpenAILike` at `api_base="https://api.doubleword.ai/v1"` with `is_chat_model=True`, a manual `context_window`, and `service_tier="flex"` in `additional_kwargs`. jaato bakes those into a **`doubleword` provider profile** (`context_length` + `api_params.service_tier`), so switching a fleet to Doubleword's discounted async tier is one profile edit, not per-call kwargs at every site.
