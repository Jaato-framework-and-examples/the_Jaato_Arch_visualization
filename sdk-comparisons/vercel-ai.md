# SDK usage, side by side: **Vercel AI SDK** vs **jaato-sdk**

Ten worked examples, simplest first, each shown in the **Vercel AI SDK** (the `ai` package) and **jaato-sdk** — both in **TypeScript** (the AI SDK is TS-native, and jaato ships `@jaato/sdk`). The point is to make the *shape* of each SDK visible, because they sit in different categories:

- **Vercel AI SDK** is a **provider-agnostic TypeScript toolkit**: a set of composable functions — `generateText` / `streamText` / `generateObject` / `tool` — plus a lightweight `Agent` loop, all running **in your Node/edge process**. Its defining job is standardising the *model* interface across 30+ providers (`@ai-sdk/openai`, `@ai-sdk/anthropic`, … and third-party providers like **`@doubleword/vercel-ai`**), so you swap backends without touching call sites. Memory, multi-agent orchestration, persistence, and human-in-the-loop are **patterns you assemble** from those primitives, not built-in subsystems. *(Mastra — our sibling doc — is a batteries-included framework built directly **on top of** this SDK.)*
- **jaato-sdk** (`@jaato/sdk`) is a **TypeScript client to a long-lived daemon**: you open a **session** against a jaato daemon over `wss://` and `ask` it; agents run **server-side as isolated, permission-gated, per-session subprocesses**, with the loop, tools, persistence, and permissions in the daemon. *(jaato's runtime is **Python**, and can also run **embedded in-process** (`jaato.session(mode="in_process")`) or as the daemon — but there's no TS embedding, so from Node you always drive the daemon; see the cross-language note below.)*

The AI SDK has **no server of its own** — it runs inside whatever you deploy (a Next.js route handler, an edge function, a plain Node script), and that in-process, zero-infrastructure footprint is exactly its strength for serverless/edge. jaato's daemon runs agents as **isolated subprocesses you connect to**. That shapes the trade: the AI SDK gives you a thin, provider-swappable toolkit you compose freely in one process; jaato gives you runtime/provider-agnostic, multi-tenant, recoverable agents behind a boundary (and, in Python, the option to embed that same runtime in-process). Read it as a trade, not a scoreboard.

> **Setup.** AI SDK: `npm i ai @ai-sdk/openai zod` (a provider package per backend). jaato-sdk: `npm i @jaato/sdk` + a reachable daemon (`wss://…`). The facade front door: `import { JaatoClient, ask, AgentError, PermissionUnhandled } from "@jaato/sdk"`. The jaato `Session` is an **`AsyncDisposable`**, so the idiomatic form is `await using` (Node 20.4+ / TS 5.2+; add `ESNext.Disposable` to your tsconfig `lib`) — an explicit `await s.close()` works on older runtimes.

> **The Doubleword angle (why this comparison exists).** Because the AI SDK's whole design is provider-swapping, Doubleword ships a **first-party provider** — `@doubleword/vercel-ai` — so "use Doubleword-served open models" is a one-line `model:` swap that pins every call to the discounted async **`service_tier=flex`** tier:
> ```ts
> import { createDoubleword } from "@doubleword/vercel-ai";
> const doubleword = createDoubleword({ apiKey: process.env.DOUBLEWORD_API_KEY!, baseURL: "https://api.doubleword.ai/v1" });
> const { text } = await generateText({ model: doubleword.languageModel("Qwen/Qwen3.5-397B-A17B-FP8"), prompt: "…" });
> ```
> jaato reaches the *same* backend through its **`doubleword` provider** — a profile knob, not a factory: `profile: { provider: "doubleword", model: "Qwen/Qwen3.5-397B-A17B-FP8", plugin_configs: { doubleword: { context_length: 131072, api_params: { service_tier: "flex" } } } }`. Same tier, different seam: a `model:` provider module you import vs. a declarative profile the daemon resolves. Every `openai("gpt-4o")` in the AI SDK snippets below is that one swap away from Doubleword.

> **Where the agent runs (cross-language).** jaato's runnable runtime is **Python**: it runs **embedded in your process** (`jaato.session(mode="in_process")` — no daemon) or behind a **daemon**, locally (`ipc`) or remotely (`ws`). **`@jaato/sdk` (TypeScript) is the remote `ws` client** — there's no TS in-process embedding (the runtime is Python), so from Node you always drive the daemon over `wss://`. The AI SDK, by contrast, *is* in-process TS. So "both are TypeScript" is real for the call sites, but the agent's execution lives in different places: the AI SDK in your Node process, jaato in a Python daemon subprocess. The examples below are the TS `ws` client.

`JaatoClient.session(...)` defaults the load-bearing knobs (`clientType: "api"` so completion works headless; the connection is a `url` + `token`, no daemon autostart — a WS client doesn't spin one up). It forwards `profile` / `agent` / `cascadeDriverId` to the session, so both the declarative style (`profile: "researcher"`, named assets in `.jaato/`) and the programmatic style (`profile: { model, provider, plugins: [] }` — an inline spec needs an explicit `plugins` key; `[]` = the minimal framework set) work. `ask`/`complete`/`stream` wait on the first of `{TURN_COMPLETED, SESSION_TERMINATED}` (so a plain turn never hangs) and **throw** on failure (`AgentError` on an error terminal, `PermissionUnhandled` if a gated tool goes unanswered). And the facade is **not all-or-nothing**: `s.client` exposes the underlying low-level client, so you can mix `ask`/`complete`/`stream` with raw event-API calls (`s.client.subscribe(EventTypeValue.…)`) on the same session.

---

## 1. Hello world — one prompt, one reply

**Vercel AI SDK**
```ts
import { generateText } from "ai";
import { openai } from "@ai-sdk/openai";

const { text } = await generateText({ model: openai("gpt-4o"), prompt: "Who are you? One sentence." });
console.log(text);
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

**Runnable:** [`examples/ts-sdk/src/ex01_basic_ask.ts`](../examples/ts-sdk/src/ex01_basic_ask.ts)

**Side by side.** The AI SDK is one stateless function call **in your process** — no object, no connection. jaato opens an isolated session **on a daemon** and `ask`s. The AI SDK is lighter for a single call (its point); jaato's one `async with` of overhead buys the session, isolation, and everything the later examples come with built-in.

## 2. Streaming the reply

**Vercel AI SDK**
```ts
import { streamText } from "ai";
const { textStream } = streamText({ model: openai("gpt-4o"), prompt: "Tell me a short story." });
for await (const chunk of textStream) process.stdout.write(chunk);
```

**jaato-sdk**
```ts
await using s = await JaatoClient.session({ url, profile: { model: "gpt-4o", provider: "openai", plugins: [] } });
for await (const chunk of s.stream("Tell me a short story.")) process.stdout.write(chunk);
```

**Runnable:** [`examples/ts-sdk/src/ex02_streaming.ts`](../examples/ts-sdk/src/ex02_streaming.ts)

**Side by side.** Near-identical async iteration. The AI SDK exposes `textStream` (plus `fullStream` for tool/step/reasoning parts); jaato's `s.stream(...)` is an `AsyncIterable<string>` of model-output chunks, raising the same `AgentError`/`PermissionUnhandled` after it drains. Same shape — one iterates a local generation, the other a server-side turn over the wire.

## 3. System prompt + multi-turn memory

**Vercel AI SDK** — stateless: **you** own the message array and thread each reply back in:
```ts
import type { ModelMessage } from "ai";
const messages: ModelMessage[] = [
  { role: "system", content: "You are a terse pirate." },
  { role: "user", content: "Hello" },
];
const r1 = await generateText({ model: openai("gpt-4o"), messages });
messages.push(...r1.response.messages);            // carry the state yourself
messages.push({ role: "user", content: "And your name?" });
console.log((await generateText({ model: openai("gpt-4o"), messages })).text);
```

**jaato-sdk** — the **session is the memory**; the system prompt is a persona file:
```ts
// persona lives in .jaato/agents/pirate.md (the system instructions), referenced by name:
await using s = await JaatoClient.session({ url, agent: "pirate", profile: { model: "gpt-4o", provider: "openai", plugins: [] } });
await s.ask("Hello");
console.log(await s.ask("And your name?"));        // same session → it remembers
```

**Runnable:** [`examples/ts-sdk/src/ex03_persona_memory.ts`](../examples/ts-sdk/src/ex03_persona_memory.ts)

**Side by side.** The AI SDK is **stateless by design** — there is no memory primitive; you accumulate `messages` (and persist them yourself for durable threads, Example 10). jaato keeps conversation state **in the daemon session** — a second `ask` on the same session just continues it — and a system prompt is a reusable **persona** (`agent: "pirate"`), not an inline system message you re-send each call.

## 4. Structured / typed output

**Vercel AI SDK** — `generateObject` with a Zod schema, validated client-side:
```ts
import { generateObject } from "ai";
import { z } from "zod";
const { object } = await generateObject({
  model: openai("gpt-4o"),
  schema: z.object({ name: z.string(), age: z.number() }),
  prompt: "Alice is 30.",
});
console.log(object.name, object.age);              // parsed + Zod-validated in your process
```

**jaato-sdk** — a typed **completion schema** the *server* enforces:
```ts
// the "person-extractor" profile declares a completion_payload_schema (.jaato/completion_schemas/person.json)
await using s = await JaatoClient.session({ url, profile: "person-extractor" });
const person = await s.complete("Alice is 30.");   // object | null (server-validated payload)
console.log(person?.name, person?.age);
```

**Runnable:** [`examples/ts-sdk/src/ex04_typed_completion.ts`](../examples/ts-sdk/src/ex04_typed_completion.ts)

**Side by side.** `generateObject` validates the model's output *after the fact, in your process* and hands you a typed object. jaato makes typed output a **server-side completion gate**: the agent must call `signal_completion(payload)`, the daemon validates it against the schema (and runs completion processors), and `s.complete()` returns that validated payload (or `null`). A wrong-shape payload is bounced back to the model to retry — the agent can't "finish" malformed, regardless of which client is attached. (You get a validated `object | null`, not a typed class instance.)

## 5. A single tool / function call

**Vercel AI SDK** — a Zod-typed `tool()`, passed to `generateText`:
```ts
import { generateText, tool, stepCountIs } from "ai";
import { z } from "zod";

const getWeather = tool({
  description: "Return the weather for a city.",
  inputSchema: z.object({ city: z.string() }),
  execute: async ({ city }) => `${city}: sunny, 24C`,   // runs in YOUR process
});
const { text } = await generateText({
  model: openai("gpt-4o"), tools: { getWeather },
  prompt: "Weather in Paris?", stopWhen: stepCountIs(5),   // allow tool → model follow-up
});
console.log(text);
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

**Runnable:** [`examples/ts-sdk/src/ex05_client_tool.ts`](../examples/ts-sdk/src/ex05_client_tool.ts)

**Side by side.** Both register a typed tool the agent can call, and in both the handler runs **in your process**. The difference is the loop around it: the AI SDK executes the tool inline inside `generateText` and (with `stopWhen`) feeds the result back to the model — all local. In jaato the schema is registered with the daemon and **the runner-tier agent loop invokes it**, calling back into your client for the handler — retries, parallelism, and result-threading happen server-side. (jaato can also use **server-side** tool plugins — `cli`, `web_search`, … — via the profile's `plugins`, with no client code at all; Example 6.) Note the AI SDK's v5 field is `inputSchema` (it was `parameters` in v4).

## 6. Multi-tool agent loop (ReAct)

**Vercel AI SDK** — the v5 `Agent` codifies the loop; give it tools and a stop condition:
```ts
import { Experimental_Agent as Agent, stepCountIs } from "ai";
const agent = new Agent({
  model: openai("gpt-4o"), system: "Plan trips.",
  tools: { getWeather, search, calculator },
  stopWhen: stepCountIs(8),                        // loop runs in-process
});
console.log((await agent.generate({ prompt: "Plan a trip to Paris." })).text);
// (the underlying primitive is generateText({ tools, stopWhen: stepCountIs(8) }) — same loop, no class)
```

**jaato-sdk** — the daemon **is** the loop; pick the plugin set and `ask` once:
```ts
await using s = await JaatoClient.session({ url, profile: {
  model: "gpt-4o", provider: "openai",
  plugins: ["cli", "web_search", "file_edit", "todo"],     // server-side tools, no client glue
} });
console.log(await s.ask("Plan a trip to Paris and save it to trip.md"));
```

**Runnable:** [`examples/ts-sdk/src/ex06_multitool.ts`](../examples/ts-sdk/src/ex06_multitool.ts)

**Side by side.** The AI SDK runs the tool-calling loop **in your process** — `Agent.generate` (or bare `generateText`) iterates model → tool → model until `stopWhen`. In jaato the loop — model → tool calls (permission-checked, parallelizable) → results → model — runs **inside the confined runner**; you choose the tools and `ask`. The loop is your dependency's code in one case, infrastructure in the other. (The AI SDK `Agent` class is `Experimental_Agent` in v5 and was renamed `ToolLoopAgent` in v6 — the `stopWhen`/`prepareStep` shape is the stable part; verify the export against your version.)

## 7. Human-in-the-loop tool approval

**Vercel AI SDK** — define the gated tool **without `execute`**, so the call returns *to you* unresolved; approve, then continue:
```ts
const deleteFile = tool({
  description: "Delete a file.",
  inputSchema: z.object({ path: z.string() }),
  // no execute → the call comes back in `toolCalls` for YOU to resolve
});
const messages: ModelMessage[] = [{ role: "user", content: "Delete temp.log" }];
const r = await generateText({ model: openai("gpt-4o"), tools: { deleteFile }, messages });
messages.push(...r.response.messages);
for (const call of r.toolCalls) {
  const ok = confirm(`allow ${call.toolName}?`);   // your out-of-band gate
  messages.push({ role: "tool", content: [{ type: "tool-result", toolCallId: call.toolCallId,
    toolName: call.toolName, output: { type: "text", value: ok ? doDelete(call.input) : "denied" } }] });
}
console.log((await generateText({ model: openai("gpt-4o"), tools: { deleteFile }, messages })).text);
```

**jaato-sdk** — permissions are built-in; pass an `onPermission` callback:
```ts
await using s = await JaatoClient.session({
  url, profile: { model: "gpt-4o", provider: "openai", plugins: ["cli"] },
  onPermission: (ev) => (confirm(`allow ${ev.tool_name}?`) ? "y" : "n"),   // sync or async; returns the response
});
console.log(await s.ask("Delete temp.log"));
```

**Runnable:** [`examples/ts-sdk/src/ex07_permissions.ts`](../examples/ts-sdk/src/ex07_permissions.ts)

**Side by side.** The AI SDK has **no permission subsystem** — the HITL pattern *is* "omit `execute`, inspect `toolCalls`, append a `tool-result`, call again," a manual approve-then-resume loop you own end-to-end (and the exact tool-result message shape is version-specific — verify it). In jaato it's **first-class on any agent turn**: the daemon asks before a gated tool and your `onPermission(ev)` returns `"y"`/`"n"`/`"a"`/… Omit the callback and a gated tool makes `s.ask()` throw `PermissionUnhandled` (auto-denied so the daemon never wedges). For *headless* sessions the same escalation can route to an out-of-band approval gate — see the resilience doc.

**The deeper link — pausing a *cascade* for out-of-band approval.** `onPermission` assumes a client is connected to answer. But in jaato, tool-failure escalations are **bus events**, so a **reactor** can handle them with *nothing connected*. The reliability pattern (resilience doc): a **headless cascade stage** (Example 9) keeps failing a tool → the reliability reactor escalates → a reactor **parks the call on a `HandoffGate`** and requests approval **out-of-band** — e.g. a chat/notifier service (via a webhook you wire) carrying the tool, its args, and which cascade stage asked → on **approve**, a second reactor flips deny→allow and **drives that same session's retry by id** — even if the runner was **unloaded** while waiting (it's reloaded by id, same session, no fork). So a long-running **cascade can pause mid-flight for a human and resume on approval**, hibernating in between — no client attached, no polling. And the pending approval (the **gate**) is durable: it survives a daemon restart, bounded by its TTL (an expired gate denies rather than hangs). The AI SDK's omit-`execute` loop does the same *shape* for one turn, but resumption runs in **your** process — you must be alive holding the `messages` to call `generateText` again; jaato's pause → approve → resume is **daemon-side, out-of-band, and durable**. (A deployment pattern — opt-in premium reactors + a gate + an approval webhook you wire, not client SDK code; mechanism in the resilience doc.)

## 8. Multi-agent / delegation

**Vercel AI SDK** — no native supervisor; the idiom is **sub-agents wrapped as tools** (the orchestrator-worker pattern):
```ts
const researcher = new Agent({ model: openai("gpt-4o"), system: "Research topics." });
const writer     = new Agent({ model: openai("gpt-4o"), system: "Write blurbs." });
const lead = new Agent({
  model: openai("gpt-4o"), system: "Delegate to researcher, then writer.",
  tools: {
    research: tool({ description: "Research a topic.", inputSchema: z.object({ topic: z.string() }),
      execute: async ({ topic }) => (await researcher.generate({ prompt: topic })).text }),
    write: tool({ description: "Write a blurb from findings.", inputSchema: z.object({ findings: z.string() }),
      execute: async ({ findings }) => (await writer.generate({ prompt: findings })).text }),
  },
  stopWhen: stepCountIs(8),
});
console.log((await lead.generate({ prompt: "Write a blurb about tide pools." })).text);   // all in-process
```

**jaato-sdk** — the supervisor's **persona** gives it a delegating *role* (its "soul" — how it behaves, **not** a task; jaato's analog of the AI SDK's `system`). The actual work arrives separately, as the **first prompt** (like the AI SDK's `generate({ prompt })` argument). The delegation it triggers is **async + daemon-driven**, so the client drops to the event API. The persona:
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

**Runnable:** [`examples/ts-sdk/src/ex08_subagent.ts`](../examples/ts-sdk/src/ex08_subagent.ts)

**Side by side.** Both are true **delegation** — one lead in control. But the AI SDK's supervisor runs **entirely in your process**: sub-agents are just tools whose `execute` calls `generate`, and `lead.generate(...)` blocks until it composes — synchronous, nested `generateText` calls. jaato's is **async and daemon-driven**: the lead calls `spawn_subagent(profile=…, task=…)` and **ends its turn**; each specialist runs **server-side** (sharing the parent's runner — a per-subagent *isolated* runner + cgroup is designed but **not yet shipped**), and its result returns as a `[SUBAGENT … COMPLETED]` event the **daemon uses to auto-continue the lead** until it composes and `signal_completion`s. Spanning many turns, this is the one example that uses the **event API** — the facade's `ask`/`complete`/`stream` return on the first `TURN_COMPLETED` (the spawn turn), so you await the final `SESSION_TERMINATED` on `s.client`. **How the lead knows to delegate, and to whom:** three inputs combine — the **persona** gives it the *role* (a coordinator that delegates; ≈ the AI SDK's `system`), the **first prompt** carries the *task* (≈ the `generate({ prompt })` argument), and the **`subagent` plugin** supplies the *means + targets*: the lead calls `list_subagent_profiles` to read each profile's name + description, then `spawn_subagent(profile="researcher", task=…)`. That registry is jaato's analog of the AI SDK's `tools: { research, write }` wiring (where the model sees each entry's `description`) — except jaato *discovers* the profiles from `.jaato/profiles/` rather than declaring them inline, and each specialist is an isolated session rather than a nested in-process call.

## 9. Multi-stage pipeline (chain vs cascade)

**Vercel AI SDK** — a **sequential chain you drive**: each call's output feeds the next (the AI SDK's "workflow patterns" are code you write, not an engine):
```ts
// step 1 → step 2, threaded in-process by you
const { object: extracted } = await generateObject({
  model: openai("gpt-4o"),
  schema: z.object({ facts: z.string() }),
  prompt: `Extract the facts from this doc: ${text}`,
});
const { text: summary } = await generateText({
  model: openai("gpt-4o"),
  prompt: `Summarise these findings: ${extracted.facts}`,
});
console.log(summary);
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

**Runnable:** [`examples/ts-sdk/src/ex09_cascade.ts`](../examples/ts-sdk/src/ex09_cascade.ts)

**Side by side.** The AI SDK chain is **synchronous, in-process data flow you drive** — two `await`s, you thread the output; parallel/routing/orchestrator-worker/evaluator-optimizer are the same idea, just more `Promise.all`/`if` in your code. A jaato **cascade** is **event- and reactor-driven, server-side**: each stage is an **isolated headless session** that just `signal_completion`s 'done' — *ignorant of what comes next* — and a **reactor** (running in the daemon, Python, whatever your client's language) reacts to that completion event and spawns the successor, threading the prior stage's typed payload into a freed warm slot. The client only triggers stage 1; the pipeline runs **decoupled in the daemon** — surviving the client disconnecting, each stage independently isolated, and you branch or fan out by adding **rules, not code**. *(A client loop over `s.complete` can sequence stages too — the direct analog of the AI SDK chain above — but that's **you** orchestrating in-process; the cascade proper is the **daemon** orchestrating on events. Production splits the hop into a two-event `agent.completed`→`slot.settled` handoff for warm-slot reuse.)*

## 10. Production: persistence, recovery, observability

**Vercel AI SDK** — durability and recovery are **yours to build**; tracing is a flag:
```ts
const { text, response } = await generateText({
  model: openai("gpt-4o"), messages,
  maxRetries: 3,                                    // transient-error retries (built in)
  experimental_telemetry: { isEnabled: true },      // → OpenTelemetry spans (Langfuse, Datadog, Braintrust…)
});
await db.save(threadId, [...messages, ...response.messages]);   // durable threads = your store
// no mid-generation recovery: if the process dies in-flight, you replay from the persisted messages
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

**Runnable:** [`examples/ts-sdk/src/ex10_recovery.ts`](../examples/ts-sdk/src/ex10_recovery.ts)

**Side by side.** The AI SDK gives you `maxRetries` and OpenTelemetry hooks, but **persistence and recovery are patterns you own** — you save `response.messages` to your store and replay them; a crash mid-generation loses the in-flight turn. jaato inherits durability from the **daemon**: `recovery: {}` auto-reconnects and recovers an in-flight turn across a restart; sessions persist server-side and re-attach by id; OpenTelemetry tracing is a daemon flag, not client code. Plus what has no AI SDK analog: each session runs in its **own AppArmor-confinable, workspace-scoped subprocess**, with optional per-session memory caps — so one agent can't take your process down with it.

---

## Coming from the Vercel AI SDK

Not a scorecard — if you already think in the AI SDK, here's what actually changes when you move to jaato, and what it buys you:

- **Your `generateObject` schema becomes a server-enforced completion gate.** In the AI SDK you pass `schema: z.object(...)` and validate the model's reply *in your process* (`res.object`). jaato moves that to the boundary: a profile's `completion_payload_schema` is checked *server-side* — the agent must `signal_completion(payload)`, the daemon validates it (and runs completion processors), and `s.complete()` hands you the validated payload or `null`. A wrong-shape payload is bounced back to the model to retry; the agent can't "finish" off-shape, no matter which client is attached.
- **Your stateless `generateText` + `messages` array becomes a stateful daemon session over WebSocket.** The AI SDK is memoryless by design — you thread `messages` and persist them yourself. `JaatoClient.session({ url: "wss://…", ... })` opens a session on a daemon where the conversation *is* the session (a second `s.ask` just continues it), the system prompt is a reusable **persona** (`agent: "pirate"`) instead of a re-sent system message, and history/isolation live behind the boundary. The TS `Session` is an `AsyncDisposable` (`await using`), so cleanup is a scope, not bookkeeping.
- **You stop assembling the loop, HITL, multi-agent, and durability from primitives.** The AI SDK is a *toolkit*: the ReAct loop is `stopWhen` over `generateText`, HITL is the omit-`execute`/inspect-`toolCalls`/resubmit pattern, multi-agent is sub-agents-as-tools, persistence is your database. In jaato these are **runtime features**: the loop runs in the confined runner; server-side tool **plugins** (`cli`, `web_search`, `file_edit`, …) need no client glue; HITL is an `onPermission(ev)` callback (or a durable out-of-band gate for headless sessions); delegation is `spawn_subagent`; durability/recovery/OTel are daemon properties. You compose *less* and inherit *more*.
- **Your in-process chain becomes a reactor-driven, server-side cascade.** An AI SDK "workflow" is a sequence of calls **you** drive in your process; if the process dies, the pipeline dies. A jaato cascade is **event- and reactor-driven inside the daemon**: each stage is an isolated headless session that just `signal_completion`s 'done', and a reactor reacts and spawns the successor, threading the typed payload forward. The client only triggers stage 1 — the pipeline survives the client disconnecting, and you branch or fan out by adding **rules, not code**. The pause-for-a-human case is durable too: an approval can park on a `HandoffGate` that outlives a daemon restart (bounded by its TTL) and drive the same session's retry by id even if the runner was unloaded while waiting.
- **Reaching Doubleword: a `model:` swap becomes a profile knob.** In the AI SDK you point `model:` at `@doubleword/vercel-ai`'s `doubleword.languageModel("…")` and every call runs on `service_tier=flex`. jaato reaches the same backend through its **`doubleword` provider** — `profile.provider: "doubleword"` with `plugin_configs.doubleword.api_params.service_tier: "flex"` (and a required `context_length`, since Doubleword's catalog reports no per-model window). Same tier, same models; the AI SDK makes it a per-call factory, jaato a declarative profile the daemon resolves — so switching a whole fleet to Doubleword is one profile edit, not a code change at every call site.

**What to keep in mind (honest trade-offs).**
- Both sides are TypeScript, so these examples are a genuine same-language comparison — but the *execution* isn't symmetric: the AI SDK runs the agent **in your Node/edge process**, jaato runs it in a **Python daemon subprocess** you reach over `wss://`. "Same language" is the call site, not where the model loop lives.
- **The AI SDK's zero-infrastructure footprint is a real advantage jaato doesn't match.** No daemon, no connection, runs on edge/serverless — for a single request handler or a Next.js route, that's genuinely simpler, and jaato's WS-client-needs-a-running-daemon (no autostart, unlike the Python SDK's local IPC) is a real dependency. jaato earns its keep when you want a *fleet* of isolated, recoverable, multi-tenant agents, not one request.
- **The AI SDK is lower-level than jaato's managed pieces — sometimes that's what you want.** Memory, multi-agent, persistence, and HITL being *patterns you assemble* means total control and no opinionated runtime; jaato trades that flexibility for built-ins and a boundary. If your value is a thin provider-agnostic model layer you compose freely, the AI SDK is already that; if it's isolation/recovery/multi-tenancy, that's assembly you'd repeat.
- **The AI SDK's API is still moving.** v5 (2025) renamed tool `parameters` → `inputSchema` and `maxSteps` → `stopWhen: stepCountIs(n)`; the `Agent` class shipped as `Experimental_Agent` and was renamed `ToolLoopAgent` in v6; message/tool-result shapes (`ModelMessage`, `tool-result` parts) differ across majors. The snippets use the current v5 surface — verify exact signatures against the version you install.
- **Provider-agnostic, two ways.** The AI SDK abstracts *providers* behind a `model:` object in your process; jaato abstracts them behind a `provider`/`model` profile the daemon resolves (local GPUs included) — and behind that same boundary adds isolation, permissions, recovery, and cascades the AI SDK leaves to you. Different seams onto the same "swap the backend freely" goal.
- Apples-to-apples: both ship **TypeScript** first-class (this is the AI SDK's home turf, and jaato's `@jaato/sdk` is a real TS client) — so unlike our Python-vs-Python docs, none of the change above is "switch languages," it's "move the agent across a boundary."
