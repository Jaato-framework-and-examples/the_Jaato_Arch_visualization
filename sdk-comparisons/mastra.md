# SDK usage, side by side: **Mastra** vs **jaato-sdk**

Ten worked examples, simplest first, each shown in **Mastra** and **jaato-sdk** — both in **TypeScript** this time (Mastra is TS-native, and jaato ships `@jaato/sdk`), so it's true same-language parity. As with the [LangChain comparison](langchain.md), the point is to make the *shape* of each SDK visible, because they sit in different categories:

- **Mastra** is a **batteries-included TypeScript framework**: you define agents, tools, workflows, and memory in your own codebase and run them in your Node process or server (`mastra dev` in development, Mastra Cloud / any Node runtime in production). Built on the **Vercel AI SDK**, it ships memory, RAG, evals, observability, and a local playground. Your agent code *is* the app.
- **jaato-sdk** is an **async client to a long-lived daemon**: agents run **server-side as isolated, permission-gated, per-session subprocesses**; your code is a thin client that opens a **session** and `ask`s. The agent loop, tools, isolation, persistence, and permissions live in the daemon, not your process.

So unlike the LangChain comparison (a pure in-process library vs a daemon client), here *both* sides have a "server" story — but a different one. Mastra's server runs **your** agent code as a Node app; jaato's daemon runs agents as **isolated subprocesses you connect to**. That shapes the trade: Mastra gives you one type-safe codebase with the whole toolkit in-process; jaato gives you runtime/provider-agnostic, multi-tenant, recoverable agents behind a boundary. Read it as a trade, not a scoreboard.

> **Setup.** Mastra: `npm i @mastra/core @ai-sdk/openai zod` (+ `@mastra/memory @mastra/libsql` for memory). jaato-sdk: `npm i @jaato/sdk` + a reachable daemon (`wss://…`). The facade front door: `import { JaatoClient, ask, AgentError, PermissionUnhandled } from "@jaato/sdk"`. The jaato `Session` is an **`AsyncDisposable`**, so the idiomatic form is `await using` (Node 20.4+ / TS 5.2+; add `ESNext.Disposable` to your tsconfig `lib`) — an explicit `await s.close()` works on older runtimes.

`JaatoClient.session(...)` defaults the load-bearing knobs (`clientType: "api"` so completion works headless; the connection is a `url` + `token`, no daemon autostart — a WS client doesn't spin one up). It forwards `profile` / `agent` / `cascadeDriverId` to the session, so both the declarative style (`profile: "researcher"`, named assets in `.jaato/`) and the programmatic style (`profile: { model, provider }`) work. `ask`/`complete`/`stream` wait on the first of `{TURN_COMPLETED, SESSION_TERMINATED}` (so a plain turn never hangs) and **throw** on failure (`AgentError` on an error terminal, `PermissionUnhandled` if a gated tool goes unanswered). And the facade is **not all-or-nothing**: `s.client` exposes the underlying low-level client, so you can mix `ask`/`complete`/`stream` with raw event-API calls (`s.client.subscribe(EventTypeValue.…)`) on the same session.

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
  url: "wss://localhost:8089",
  profile: { model: "gpt-4o", provider: "openai" },
});
console.log(await s.ask("Who are you? One sentence."));
```
…or the one-shot module helper, for a throwaway call:
```ts
import { ask } from "@jaato/sdk";
console.log(await ask("Who are you? One sentence.", { url: "wss://localhost:8089", profile: { model: "gpt-4o", provider: "openai" } }));
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
await using s = await JaatoClient.session({ url, profile: { model: "gpt-4o", provider: "openai" } });
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
await using s = await JaatoClient.session({ url, agent: "pirate", profile: { model: "gpt-4o", provider: "openai" } });
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
  url, profile: { model: "gpt-4o", provider: "openai" },
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

**The deeper link — pausing a *cascade* for out-of-band approval.** `onPermission` assumes a client is connected to answer. But in jaato, tool-failure escalations are **bus events**, so a **reactor** can handle them with *nothing connected*. The reliability pattern (resilience doc): a **headless cascade stage** (Example 9) keeps failing a tool → the reliability reactor escalates → a reactor **parks the call on a `HandoffGate`** and requests approval **out-of-band** — e.g. a Telegram bot (via a webhook you wire) carrying the tool, its args, and which cascade stage asked → on **approve**, a second reactor flips deny→allow and **drives that same session's retry by id** — even if the runner was **unloaded** while waiting (it's reloaded by id, same session, no fork). So a long-running **cascade can pause mid-flight for a human and resume on approval**, hibernating in between — no client attached, no polling. And the pending approval (the **gate**) is durable: it survives a daemon restart, bounded by its TTL (an expired gate denies rather than hangs). Mastra's workflow `suspend`/`resume` does the same *shape*, but resumption runs in **your** process — you must be alive (and holding the run) to call `run.resume()`; jaato's pause → approve → resume is **daemon-side, out-of-band, and durable**. (A deployment pattern — opt-in premium reactors + a gate + an approval webhook you wire, not client SDK code; mechanism in the resilience doc.)

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

**jaato-sdk** — each agent is its own isolated session; compose by passing output:
```ts
import { ask } from "@jaato/sdk";
const notes = await ask("Research tide pools; return bullet notes.", { url, agent: "researcher", profile: { model: "gpt-4o", provider: "openai" } });
const draft = await ask(`Write a blurb from these notes:\n${notes}`, { url, agent: "writer", profile: { model: "gpt-4o", provider: "openai" } });
```

**Side by side.** Mastra's supervisor keeps one lead agent in control, delegating to sub-agents (declared on `agents`) as needed — all in your process. jaato gives each agent an **isolated session** (own runner, own plugins/persona); you compose them by passing output between calls — or one agent spawns **subagents** server-side via the `subagent` plugin. (Note: Mastra's older `AgentNetwork` is deprecated in favour of supervisor agents.)

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

**jaato-sdk** — a **cascade**: sequential sessions sharing one **warm runner slot**:
```ts
import { randomUUID } from "node:crypto";
const cid = randomUUID();                                  // one id per cascade
for (const prompt of ["Stage 1: extract.", "Stage 2: summarize."]) {
  await using stage = await JaatoClient.session({ url, profile: { model: "gpt-4o", provider: "openai" }, cascadeDriverId: cid });
  await stage.complete(prompt);   // complete() waits SESSION_TERMINATED → slot settled before the next stage
}
```

**Side by side.** Mastra's workflow is a **typed, in-process orchestration graph** — `createStep`/`.then()`/`.branch()`/parallel/loops, each step's I/O Zod-validated, with built-in `suspend`/`resume` and snapshots. jaato's cascade is a chain of **headless sessions** linked by completion events, reusing a pre-warmed runner slot (`cascadeDriverId`) so each stage skips cold-start — and in a real deployment the stage-to-stage handoff is **reactor-driven**. Different shapes: one type-safe graph you author and run, vs decoupled isolated sessions chained by the daemon.

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
  url, profile: { model: "gpt-4o", provider: "openai" },
  recovery: {},                                             // auto-reconnect across daemon restarts
  onStatusChange: (st) => console.log(st.state),            // reconnecting / connected / closed
});
console.log(await s.ask("Long task…"));                      // survives a daemon bounce
// sessions also persist server-side: detach and re-attach by id with the low-level client.
```

**Side by side.** In Mastra you wire durability (a storage adapter) and tracing (the observability config → OTel) into **your** app. jaato inherits them from the **daemon**: `recovery: {}` auto-reconnects and recovers an in-flight turn across a restart; sessions persist server-side and re-attach by id; OpenTelemetry tracing is a daemon flag, not client code. Plus what has no Mastra analog: each session runs in its **own AppArmor-confinable, workspace-scoped subprocess**, with optional per-session memory caps — so one agent can't take your app's process down with it.

---

## When each shines

| You want… | Reach for |
|---|---|
| One type-safe TS codebase with the whole toolkit in-process (agents, tools, workflows, memory, RAG, evals) | **Mastra** |
| A typed, inspectable workflow graph with `suspend`/`resume` and a dev playground | **Mastra** |
| The Vercel AI SDK / Node ecosystem and rapid DX | **Mastra** |
| Multi-tenant, isolated, recoverable agents behind a boundary; built-in permissions / cascades / crash-recovery; provider- and runtime-agnostic (local GPUs); typed completion gates; a thin client with bounded per-agent memory | **jaato-sdk** |

**Honest caveats.**
- Both are TypeScript here, so this is real same-language parity (no "Python for both" asterisk).
- **Mastra's API is still moving** — v1.0 landed January 2026, and there are legacy methods (`generateLegacy`/`streamLegacy`, the deprecated `AgentNetwork`) and v1-beta docs in circulation. The snippets use the current v1 surface; verify exact signatures (especially the workflow run/`resume` and `stream` options) against the version you install.
- **jaato-sdk needs a running daemon** and a WS endpoint (`wss://…` + token); it doesn't autostart one (unlike the Python SDK's local-IPC autostart). For a single throwaway script that's a real dependency; for a fleet of isolated, recoverable, multi-tenant agents it's the point. The `await using` facade needs Node 20.4+ / TS 5.2+ (explicit `close()` otherwise).
- Different runtime models: Mastra runs **your** agent code (and tools) in your Node process/server; jaato runs agents as **isolated subprocesses** behind the daemon, so a tool/agent crash or memory blowup is contained server-side, not in your app.
