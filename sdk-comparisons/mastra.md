# SDK usage, side by side: **Mastra** vs **jaato-sdk**

Ten worked examples, simplest first, each shown in **Mastra** and **jaato-sdk** — both in **TypeScript** (Mastra is TS-native, and jaato ships `@jaato/sdk`). The point is to make the *shape* of each SDK visible, because they sit in different categories:

- **Mastra** is a **batteries-included TypeScript framework**: you define agents, tools, workflows, and memory in your own codebase and run them in your Node process or server (`mastra dev` in development, Mastra Cloud / any Node runtime in production). Built on the **Vercel AI SDK**, it ships memory, RAG, evals, observability, and a local playground. Your agent code *is* the app.
- **jaato-sdk** is an **async client to a long-lived daemon**: agents run **server-side as isolated, permission-gated, per-session subprocesses**; your code is a thin client that opens a **session** and `ask`s. The agent loop, tools, isolation, persistence, and permissions live in the daemon, not your process.

*Both* sides have a "server" story — but a different one. Mastra's server runs **your** agent code as a Node app; jaato's daemon runs agents as **isolated subprocesses you connect to**. That shapes the trade: Mastra gives you one type-safe codebase with the whole toolkit in-process; jaato gives you runtime/provider-agnostic, multi-tenant, recoverable agents behind a boundary. Read it as a trade, not a scoreboard.

> **Setup.** Mastra: `npm i @mastra/core @ai-sdk/openai zod` (+ `@mastra/memory @mastra/libsql` for memory). jaato-sdk: `npm i @jaato/sdk` + a reachable daemon (`wss://…`). The facade front door: `import { JaatoClient, ask, AgentError, PermissionUnhandled } from "@jaato/sdk"`. The jaato `Session` is an **`AsyncDisposable`**, so the idiomatic form is `await using` (Node 20.4+ / TS 5.2+; add `ESNext.Disposable` to your tsconfig `lib`) — an explicit `await s.close()` works on older runtimes.

`JaatoClient.session(...)` defaults the load-bearing knobs (`clientType: "api"` so completion works headless; the connection is a `url` + `token`, no daemon autostart — a WS client doesn't spin one up). It forwards `profile` / `agent` / `cascadeDriverId` to the session, so both the declarative style (`profile: "researcher"`, named assets in `.jaato/`) and the programmatic style (`profile: { model, provider, plugins: [] }` — an inline spec needs an explicit `plugins` key; `[]` = the minimal framework set) work. `ask`/`complete`/`stream` wait on the first of `{TURN_COMPLETED, SESSION_TERMINATED}` (so a plain turn never hangs) and **throw** on failure (`AgentError` on an error terminal, `PermissionUnhandled` if a gated tool goes unanswered). And the facade is **not all-or-nothing**: `s.client` exposes the underlying low-level client, so you can mix `ask`/`complete`/`stream` with raw event-API calls (`s.client.subscribe(EventTypeValue.…)`) on the same session.

---

## 1. Hello world — one prompt, one reply

**Mastra**
```ts
import { Agent } from "@mastra/core/agent";
import { openai } from "@ai-sdk/openai";

const agent = new Agent({ name: "assistant", instructions: "You are helpful.", model: openai("gpt-4o") });
const res = await agent.generate("Who are you? One sentence.");
console.log(res.text);
```

**jaato-sdk**
```ts
import { JaatoClient } from "@jaato/sdk";

await using s = await JaatoClient.session({
  url: "wss://localhost:8080",
  profile: { model: "gpt-4o", provider: "openai", plugins: [] },
});
console.log(await s.ask("Who are you? One sentence."));
```
…or the one-shot module helper, for a throwaway call:
```ts
import { ask } from "@jaato/sdk";
console.log(await ask("Who are you? One sentence.", { url: "wss://localhost:8080", profile: { model: "gpt-4o", provider: "openai", plugins: [] } }));
```

**Side by side.** Both are a few lines. Mastra constructs an agent object and runs it **in your process**; jaato opens an isolated session **on a daemon** and `ask`s. Comparable ceremony — the difference is *where the agent runs*, not how much code you write.

## 2. Streaming the reply

**Mastra**
```ts
const stream = await agent.stream("Tell me a short story.");
for await (const chunk of stream.textStream) process.stdout.write(chunk);
```

**jaato-sdk**
```ts
await using s = await JaatoClient.session({ url, profile: { model: "gpt-4o", provider: "openai", plugins: [] } });
for await (const chunk of s.stream("Tell me a short story.")) process.stdout.write(chunk);
```

**Side by side.** Near-identical async iteration. Mastra exposes `stream.textStream` (it also has `stream.fullStream` for tool/step events, being built on the Vercel AI SDK); jaato's `s.stream(...)` is an `AsyncIterable<string>` of model-output chunks, raising the same `AgentError`/`PermissionUnhandled` after it drains.

## 3. System prompt + multi-turn memory

**Mastra** — a persistent `Memory` keyed by `threadId` / `resourceId`:
```ts
import { Memory } from "@mastra/memory";
import { LibSQLStore } from "@mastra/libsql";

const agent = new Agent({
  name: "pirate", instructions: "You are a terse pirate.", model: openai("gpt-4o"),
  memory: new Memory({ storage: new LibSQLStore({ url: "file:./memory.db" }) }),
});
const ctx = { memory: { thread: "t1", resource: "user-42" } };
await agent.generate("Hello", ctx);
console.log((await agent.generate("And your name?", ctx)).text);   // same thread → remembers
```

**jaato-sdk** — the **session is the memory**; the system prompt is a persona file:
```ts
// persona lives in .jaato/agents/pirate.md (the system instructions), referenced by name:
await using s = await JaatoClient.session({ url, agent: "pirate", profile: { model: "gpt-4o", provider: "openai", plugins: [] } });
await s.ask("Hello");
console.log(await s.ask("And your name?"));        // same session → it remembers
```

**Side by side.** Mastra makes memory an explicit, pluggable store (LibSQL/Postgres/…) addressed by `threadId`/`resourceId`, with working-memory and semantic-recall features. jaato keeps conversation state **in the daemon session** — a second `ask` on the same session just continues it — and a system prompt is a reusable **persona** (`agent: "pirate"`), not constructor config.

## 4. Structured / typed output

**Mastra** — a Zod schema validated client-side:
```ts
import { z } from "zod";
const res = await agent.generate("Alice is 30.", {
  structuredOutput: { schema: z.object({ name: z.string(), age: z.number() }), model: openai("gpt-4o") },
});
console.log(res.object.name, res.object.age);      // parsed + Zod-validated in your process
```

**jaato-sdk** — a typed **completion schema** the *server* enforces:
```ts
// the "person-extractor" profile declares a completion_payload_schema (.jaato/completion_schemas/person.json)
await using s = await JaatoClient.session({ url, profile: "person-extractor" });
const person = await s.complete("Alice is 30.");   // object | null (server-validated payload)
console.log(person?.name, person?.age);
```

**Side by side.** Mastra validates the model's output *after the fact, in your process* (`structuredOutput` → `res.object`). jaato makes typed output a **server-side completion gate**: the agent must call `signal_completion(payload)`, the daemon validates it against the schema (and runs completion processors), and `s.complete()` returns that validated payload (or `null`). A wrong-shape payload is bounced back to the model to retry — the agent can't "finish" malformed.

## 5. A single tool / function call

**Mastra** — a typed tool defined with Zod, attached to the agent:
```ts
import { createTool } from "@mastra/core/tools";
import { z } from "zod";

const getWeather = createTool({
  id: "get-weather", description: "Return the weather for a city.",
  inputSchema: z.object({ city: z.string() }),
  outputSchema: z.object({ weather: z.string() }),
  execute: async ({ inputData }) => ({ weather: `${inputData.city}: sunny, 24C` }),
});
const agent = new Agent({ name: "a", instructions: "Use tools.", model: openai("gpt-4o"), tools: { getWeather } });
console.log((await agent.generate("Weather in Paris?")).text);
```

**jaato-sdk** — a client-provided ("host") tool the daemon calls back into, passed as `clientTools`:
```ts
await using s = await JaatoClient.session({
  url, profile: { model: "gpt-4o", provider: "openai", plugins: [] },
  clientTools: [{
    name: "get_weather", description: "Return the weather for a city.",
    parameters: { type: "object", properties: { city: { type: "string" } }, required: ["city"] },
    handler: (args) => ({ weather: `${args.city}: sunny, 24C` }),   // runs in YOUR process
  }],
});
console.log(await s.ask("Weather in Paris?"));
```

**Side by side.** Both register a typed tool the agent can call. In Mastra the tool's `execute` runs **in your Node process**, inline with the agent. In jaato the schema is registered with the daemon and **the runner-tier agent loop invokes it**, calling back into your client for the handler — the loop, retries, and result-threading happen server-side. (jaato can also use **server-side** tool plugins — `cli`, `web_search`, … — via the profile's `plugins`, with no client code at all; Example 6.)

## 6. Multi-tool agent loop (ReAct)

**Mastra** — give the agent several tools; it loops until done (bounded by `stopWhen`):
```ts
import { stepCountIs } from "@mastra/core/agent";
const agent = new Agent({ name: "planner", instructions: "Plan trips.",
  model: openai("gpt-4o"), tools: { getWeather, search, calculator } });
await agent.generate("Plan a trip to Paris.", { stopWhen: stepCountIs(8) });   // loop runs in-process
```

**jaato-sdk** — the daemon **is** the loop; pick the plugin set and `ask` once:
```ts
await using s = await JaatoClient.session({ url, profile: {
  model: "gpt-4o", provider: "openai",
  plugins: ["cli", "web_search", "file_edit", "todo"],     // server-side tools, no client glue
} });
console.log(await s.ask("Plan a trip to Paris and save it to trip.md"));
```

**Side by side.** Mastra runs the tool-calling loop **inside `agent.generate`**, in your process, with `stopWhen` as the stop condition. In jaato the loop — model → tool calls (permission-checked, parallelizable) → results → model — runs **inside the confined runner**; you choose the tools and `ask`. The loop is your dependency's code in one case, infrastructure in the other.

## 7. Human-in-the-loop tool approval

**Mastra** — a **workflow** that suspends for input, then resumes:
```ts
const review = createStep({
  id: "review", inputSchema: z.object({ cmd: z.string() }), outputSchema: z.object({ ok: z.boolean() }),
  resumeSchema: z.object({ approved: z.boolean() }),
  execute: async ({ inputData, resumeData, suspend }) => {
    if (!resumeData) return await suspend({ cmd: inputData.cmd });    // pause for a human
    return { ok: resumeData.approved };
  },
});
const run = await workflow.createRunAsync();
let result = await run.start({ inputData: { cmd: "rm temp.log" } });   // → status "suspended"
result = await run.resume({ step: "review", resumeData: { approved: true } });
```

**jaato-sdk** — permissions are built-in; pass an `onPermission` callback:
```ts
await using s = await JaatoClient.session({
  url, profile: { model: "gpt-4o", provider: "openai", plugins: ["cli"] },
  onPermission: (ev) => (confirm(`allow ${ev.tool_name}?`) ? "y" : "n"),   // sync or async; returns the response
});
console.log(await s.ask("Delete temp.log"));
```

**Side by side.** In Mastra, HITL is a **workflow** concern: you wrap the gated action in a step that `suspend()`s and a host that `resume()`s with the human's input (snapshotted to storage). In jaato it's **first-class on any agent turn**: the daemon asks before a gated tool and your `onPermission(ev)` returns `"y"`/`"n"`/`"a"`/… Omit the callback and a gated tool makes `s.ask()` throw `PermissionUnhandled` (auto-denied so the daemon never wedges). For *headless* sessions the same escalation can route to an out-of-band approval gate — see the resilience doc.

**The deeper link — pausing a *cascade* for out-of-band approval.** `onPermission` assumes a client is connected to answer. But in jaato, tool-failure escalations are **bus events**, so a **reactor** can handle them with *nothing connected*. The reliability pattern (resilience doc): a **headless cascade stage** (Example 9) keeps failing a tool → the reliability reactor escalates → a reactor **parks the call on a `HandoffGate`** and requests approval **out-of-band** — e.g. a chat/notifier service (via a webhook you wire) carrying the tool, its args, and which cascade stage asked → on **approve**, a second reactor flips deny→allow and **drives that same session's retry by id** — even if the runner was **unloaded** while waiting (it's reloaded by id, same session, no fork). So a long-running **cascade can pause mid-flight for a human and resume on approval**, hibernating in between — no client attached, no polling. And the pending approval (the **gate**) is durable: it survives a daemon restart, bounded by its TTL (an expired gate denies rather than hangs). Mastra's workflow `suspend`/`resume` does the same *shape*, but resumption runs in **your** process — you must be alive (and holding the run) to call `run.resume()`; jaato's pause → approve → resume is **daemon-side, out-of-band, and durable**. (A deployment pattern — opt-in premium reactors + a gate + an approval webhook you wire, not client SDK code; mechanism in the resilience doc.)

## 8. Multi-agent / delegation

**Mastra** — a **supervisor** agent with sub-agents on its `agents` property:
```ts
const researcher = new Agent({ name: "researcher", instructions: "Research topics.", model: openai("gpt-4o") });
const writer     = new Agent({ name: "writer", instructions: "Write blurbs.", model: openai("gpt-4o") });
const supervisor = new Agent({
  name: "lead", instructions: "Delegate to researcher, then writer.",
  model: openai("gpt-4o"), agents: { researcher, writer },     // sub-agents act as delegate tools
});
console.log((await supervisor.generate("Write a blurb about tide pools.")).text);
```

**jaato-sdk** — the supervisor's **persona** gives it a delegating *role* (its "soul" — how it behaves, **not** a task; jaato's analog of Mastra's `instructions`). The actual work arrives separately, as the **first prompt** (like Mastra's `generate(...)` argument). The delegation it triggers is **async + daemon-driven**, so the client drops to the event API. The persona:
```markdown
<!-- .jaato/agents/lead.md — role & behaviour, NOT a task -->
You are a coordinator. You get work done by delegating to specialist subagents
rather than doing it yourself: break the request into pieces, hand each to the
right specialist, and synthesise their results into the final answer.
```
The client opens the session and sends the **task** as the first prompt — the persona's role plus the `subagent` tools turn it into delegation:
```ts
import { JaatoClient, EventTypeValue } from "@jaato/sdk";

await using s = await JaatoClient.session({ url, agent: "lead",
  profile: { model: "gpt-4o", provider: "openai", plugins: ["subagent"] } });
const out: string[] = [];
s.client.subscribe(EventTypeValue.AGENT_OUTPUT, (e) => { if (e.text) out.push(e.text); });
await new Promise<void>((resolve) => {
  s.client.subscribeOnce(EventTypeValue.SESSION_TERMINATED, () => resolve());   // NOT turn.completed
  void s.client.sendMessage("Research tide pools, then write a blurb from the findings.");
});
// the daemon auto-continues 'lead' as each subagent COMPLETES; resolves only when 'lead' signal_completion's
console.log(out.join(""));
```

**Side by side.** Both are true **delegation** — one lead in control. But Mastra's supervisor runs **in your process**, `supervisor.generate(...)` blocking until it composes. jaato's is **async and daemon-driven**: the lead calls `spawn_subagent(profile=…, task=…)` and **ends its turn**; each specialist runs **server-side** (sharing the parent's runner — a per-subagent *isolated* runner + cgroup is designed but **not yet shipped**), and its result returns as a `[SUBAGENT … COMPLETED]` event the **daemon uses to auto-continue the lead** until it composes and `signal_completion`s. Spanning many turns, this is the one example that uses the **event API** — the facade's `ask`/`complete`/`stream` return on the first `TURN_COMPLETED` (the spawn turn), so you await the final `SESSION_TERMINATED` on `s.client`. (Personas live in `.jaato/agents/`; the lead must be **completion-gated**. Mastra's older `AgentNetwork` is deprecated in favour of supervisor agents.) **How the lead knows to delegate, and to whom:** three inputs combine — the **persona** gives it the *role* (a coordinator that delegates rather than working directly; ≈ Mastra's `instructions`), the **first prompt** carries the *task* (≈ Mastra's `generate(...)` argument), and the **`subagent` plugin** supplies the *means + targets*: the lead calls `list_subagent_profiles` to read each profile's name + description, then `spawn_subagent(profile="researcher", task=…)`. That `list_subagent_profiles` registry is jaato's analog of Mastra's `agents:{}` declaration (where the model sees each sub-agent's `description`) — except jaato *discovers* the profiles from `.jaato/profiles/` rather than declaring them inline. (The `agent=` persona axis is a *separate*, non-discovered selector.)

## 9. Multi-stage pipeline (workflow vs cascade)

**Mastra** — a typed `Workflow` of composed steps:
```ts
import { createWorkflow, createStep } from "@mastra/core/workflows";
const extract = createStep({ id: "extract", inputSchema: z.object({ doc: z.string() }), outputSchema: z.object({ facts: z.string() }), execute: async ({ inputData }) => ({ facts: extractFrom(inputData.doc) }) });
const summarize = createStep({ id: "summarize", inputSchema: z.object({ facts: z.string() }), outputSchema: z.object({ summary: z.string() }), execute: async ({ inputData }) => ({ summary: summarise(inputData.facts) }) });
const wf = createWorkflow({ inputSchema: z.object({ doc: z.string() }), outputSchema: z.object({ summary: z.string() }) })
  .then(extract).then(summarize).commit();
const run = await wf.createRunAsync();
await run.start({ inputData: { doc: text } });
```

**jaato-sdk** — a real cascade is **event + reactor driven**, not a client loop. Each stage runs a **persona** (`agent`, its soul) under a **profile**, and needs a **first message** (its task): the client (TS here) supplies **stage 1**'s, and a **reactor** *injects* every later stage's from the prior stage's output (no human types it):
```ts
import { randomUUID } from "node:crypto";
const cid = randomUUID();
await using s = await JaatoClient.session({ url, agent: "extract", profile: "extract", cascadeDriverId: cid });
await s.complete("Extract the facts from this doc: …");   // stage 1's first message (its task)
```
For the typed handoff to work, the **producer's profile must declare a `completion_payload_schema`** — without it `signal_completion` is a legacy summary and `event.get("facts")` below is `None`:
```yaml
# .jaato/profiles/extract.yaml (excerpt)
completion_payload_schema: { type: object, properties: { facts: { type: string } }, required: [facts] }
# → the extract agent then calls signal_completion(facts="…")  — a schema's top-level props are FLAT args, not wrapped
```
The hop lives in a **deployment reactor** that runs **inside the daemon** (Python, regardless of your client language) — `.jaato/reactors/` + `.jaato/scripts/`:
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

**Side by side.** Mastra's `Workflow` is a **typed, in-process orchestration you drive** — `createStep`/`.then()`/`.branch()`/parallel, Zod-validated, with `suspend`/`resume` and snapshots. A jaato **cascade** is **event- and reactor-driven, server-side**: each stage is an **isolated headless session** that just `signal_completion`s 'done' — *ignorant of what comes next* — and a **reactor** (running in the daemon, Python, whatever your client's language) reacts to that completion event and spawns the successor, threading the prior stage's typed payload into a freed warm slot. The client only triggers stage 1; the pipeline runs **decoupled in the daemon** — surviving the client disconnecting, each stage independently isolated, and you branch or fan out by adding **rules, not code**. *(A client loop over `s.complete` can sequence stages too — but that's **you** orchestrating in-process, which any framework does; the cascade proper is the **daemon** orchestrating on events. Production splits the hop into a two-event `agent.completed`→`slot.settled` handoff for warm-slot reuse.)*

## 10. Production: persistence, recovery, observability

**Mastra** — register everything on a `Mastra` instance with storage + tracing:
```ts
import { Mastra } from "@mastra/core";
export const mastra = new Mastra({
  agents: { agent }, workflows: { wf },
  storage: new LibSQLStore({ url: "file:./mastra.db" }),   // memory + workflow snapshots
  observability: { default: { enabled: true } },            // AI tracing → OTel exporters (Datadog, SigNoz, Langfuse…)
});
// deploy on any Node runtime / Mastra Cloud; `mastra dev` gives a local playground.
```

**jaato-sdk** — durability/recovery/tracing are daemon properties; recovery is a session option:
```ts
await using s = await JaatoClient.session({
  url, profile: { model: "gpt-4o", provider: "openai", plugins: [] },
  recovery: {},                                             // auto-reconnect across daemon restarts
  onStatusChange: (st) => console.log(st.state),            // reconnecting / connected / closed
});
console.log(await s.ask("Long task…"));                      // survives a daemon bounce
// sessions also persist server-side: detach and re-attach by id with the low-level client.
```

**Side by side.** In Mastra you wire durability (a storage adapter) and tracing (the observability config → OTel) into **your** app. jaato inherits them from the **daemon**: `recovery: {}` auto-reconnects and recovers an in-flight turn across a restart; sessions persist server-side and re-attach by id; OpenTelemetry tracing is a daemon flag, not client code. Plus what has no Mastra analog: each session runs in its **own AppArmor-confinable, workspace-scoped subprocess**, with optional per-session memory caps — so one agent can't take your app's process down with it.

---

## Coming from Mastra

Not a scorecard — if you already think in Mastra, here's what actually changes when you move to jaato, and what it buys you:

- **Your Zod output schema becomes a server-enforced completion gate.** In Mastra you pass `structuredOutput: { schema: z.object(...) }` and validate the model's reply *in your process* (`res.object`). jaato moves that to the boundary: a profile's `completion_payload_schema` is checked *server-side* — the agent must `signal_completion(payload)`, the daemon validates it (and runs completion processors), and `s.complete()` hands you the validated payload or `null`. A wrong-shape payload is bounced back to the model to retry; the agent can't "finish" off-shape, no matter which client is attached.
- **Your in-process `agent.generate` becomes an isolated daemon session over WebSocket.** A Mastra `Agent` lives in your Node process; `JaatoClient.session({ url: "wss://…", ... })` opens a session on a daemon where the agent runs as a **permission-gated, workspace-scoped subprocess**. The conversation *is* the session (a second `s.ask` just continues it), the system prompt is a reusable **persona** (`agent: "pirate"`) instead of constructor config, and the loop/memory/isolation live behind the boundary rather than in your app. The TS `Session` is an `AsyncDisposable` (`await using`), so cleanup is a scope, not a lifecycle you manage.
- **You stop wiring the agent loop and provider plumbing.** Mastra runs the ReAct loop inside `agent.generate` (bounded by `stopWhen`) on top of the Vercel AI SDK; client-side tools execute inline in your process. In jaato the loop — model → permission-checked tool calls → results → model — runs inside the confined runner. Server-side tool **plugins** (`cli`, `web_search`, `file_edit`, …) need no client glue at all, and you're **provider- and runtime-agnostic**: swap `provider`/`model` (including local GPUs) without touching app code. HITL is first-class on any turn — an `onPermission(ev)` callback returns `"y"`/`"n"`/`"a"` — not something you hand-build as a workflow step.
- **Mastra workflows and `suspend`/`resume` become reactor-driven, server-side cascades with durable HITL gates.** A Mastra `Workflow` is a typed graph **you** drive in-process; resuming a suspended run means *you* are alive holding the run to call `run.resume()`. A jaato cascade is **event- and reactor-driven inside the daemon**: each stage is an isolated headless session that just `signal_completion`s 'done', and a reactor reacts to that event and spawns the successor, threading the typed payload forward. The client only triggers stage 1 — the pipeline survives the client disconnecting, and you branch or fan out by adding **rules, not code**. The pause-for-a-human case is durable too: an approval can park on a `HandoffGate` that outlives a daemon restart (bounded by its TTL) and drive the same session's retry by id even if the runner was unloaded while waiting.

**What to keep in mind (honest trade-offs).**
- Both sides are TypeScript, so these examples are a genuine same-language comparison — none of the change above is "switch languages," it's "move the agent across a boundary."
- **jaato-sdk needs a running daemon** and a WS endpoint (`wss://…` + token); it doesn't autostart one (unlike the Python SDK's local-IPC autostart). For a single throwaway script that's a real dependency; for a fleet of isolated, recoverable, multi-tenant agents it's the point. The `await using` facade needs Node 20.4+ / TS 5.2+ (an explicit `close()` works otherwise).
- Different runtime models: Mastra runs **your** agent code (and tools) in your Node process/server; jaato runs agents as **isolated subprocesses** behind the daemon, so a tool/agent crash or memory blowup is contained server-side, not in your app. That isolation is also remoteness — your calls cross a WebSocket to a daemon you have to run and reach, rather than executing inline.
- **Mastra's API is still moving** — v1.0 landed January 2026, and there are legacy methods (`generateLegacy`/`streamLegacy`, the deprecated `AgentNetwork`) and v1-beta docs in circulation. The snippets use the current v1 surface; verify exact signatures (especially the workflow run/`resume` and `stream` options) against the version you install.
- You give up Mastra's in-process conveniences as in-process things: observability is a **daemon** property (OpenTelemetry is a daemon flag, not the Mastra `observability` config wired into your app), and there's no local `mastra dev` playground or in-codebase typed workflow graph to inspect — the orchestration lives in `.jaato/` reactors and runs server-side.
