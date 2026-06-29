# Platform comparison: **Ona** vs **jaato**

> A different genre from the [SDK comparisons](../sdk-comparisons/): those put jaato-sdk next to *libraries* you build an agent with. **Ona is a platform, not a library** — there's no `Agent(...)` to write; you call an API to launch agents that run in its cloud. So this compares the two as **platform peers** — managed cloud agent service vs self-hosted agent daemon — on their orchestration API and their architecture.

Of everything compared in this series, Ona is the **closest architectural peer** to jaato: in both, a thin client **launches isolated, long-running, recoverable agents that run server-side**, and you observe/steer them over an API. The split is *where the server is and how open it is*:

- **Ona** (formerly Gitpod; **acquired by OpenAI, June 2026**) is a **managed cloud platform** for background software-engineering agents. You `POST` to its API to start an agent that runs in a **devcontainer-based cloud environment** (Ona's cloud or your VPC), governed by enterprise controls (RBAC/SSO/OIDC/audit). It is **OpenAI/Codex-centric** (`codexSettings`), with **Automations** that fire agents on git/schedule events and ~10-minute checkpointing for long runs.
- **jaato** is a **self-hosted daemon**: you run it, and a thin client opens **sessions** that run as **isolated, AppArmor-confinable per-session subprocesses** with your own personas/profiles/plugins. It is **provider- and runtime-agnostic** (any model, local GPUs), with **reactor-driven cascades**, **server-enforced completion gates**, and out-of-band HITL.

So both are "launch agents server-side and drive them as a client." Ona gives you a managed, governed, OpenAI-powered cloud you call; jaato gives you a provider-agnostic engine you host and shape. Read it as a trade, not a scoreboard.

> **Setup.** Ona: a `GITPOD_API_KEY`; calls are **gRPC-JSON over HTTPS** at `https://app.gitpod.io/api/` (the `gitpod.v1` namespace persists from the Gitpod heritage) — **no first-party SDK**, so its examples are `curl`. jaato has **two transports**: **IPC** (a *local* Unix socket — the Python `IPCClient`) and **WebSocket** (`--web-socket :8080` + a bearer token — *remote*). Ona is a remote service over HTTPS, so the apt analog is jaato's **WS / remote path**: the open wire protocol (JSON frames, callable with `curl`/`websocat`) **plus** the **TypeScript** facade (`JaatoClient.session({url:"wss://…"})`). Example 1 compares **raw protocol on both sides** (Ona REST ↔ jaato WS frames) and also shows jaato's **TS facade** once — the SDK Ona has no equivalent of; the **rest stay at the raw-WS level on both sides**, wire-for-wire. *(The Python `IPCClient` is the local IPC client — not the remote analog; see the caveats.)*

---

## 1. Launch a background agent

**Ona** — `StartAgent` returns an execution id; the agent runs in the cloud:
```bash
curl -X POST https://app.gitpod.io/api/gitpod.v1.AgentService/StartAgent \
  -H "Authorization: Bearer $GITPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{
        "codeContext": { "projectId": "proj_123",
                         "contextUrl": { "url": "https://github.com/acme/api" } },
        "mode": "AGENT_MODE_EXECUTION",
        "codexSettings": { "model": "CODEX_OPEN_AI_MODEL_GPT_5_5",
                           "reasoningEffort": "CODEX_REASONING_EFFORT_HIGH" }
      }'
# → { "agentExecutionId": "uuid" }
```

**jaato** — *same wire level as Ona:* raw **WS frames** over the daemon's remote WebSocket endpoint (bearer token):
```bash
websocat "wss://localhost:8080/?token=$JAATO_WS_TOKEN"   # CLI clients may use an Authorization: Bearer header
# ← {"type":"connected","server_info":{...}}              # wait for this greeting, then send commands
→ {"type":"command.execute","command":"session.new","args":["--profile","backend"],"payload":{}}
→ {"type":"message.send","text":"Refactor the auth module and open a PR."}
# ← {"type":"agent.output","text":"…"} … {"type":"turn.completed", ...}   # close the socket → the run keeps going
```
…or jaato's **SDK** over the *same* protocol — the **TypeScript** facade (Ona has no SDK at all):
```ts
import { JaatoClient } from "@jaato/sdk";
await using s = await JaatoClient.session({ url: "wss://localhost:8080", token, profile: "backend" });
console.log(await s.complete("Refactor the auth module and open a PR."));
// to launch-and-DETACH like Ona's StartAgent, use the low-level client (createSession + sendMessage,
// don't dispose) — the run continues daemon-side; the session id comes back on the session.new reply,
// so you can reattach by it later (§2).
```

**Runnable:** [`examples/ws/ex1_basic_session.mjs`](../examples/ws/ex1_basic_session.mjs)

**Side by side.** At the **wire level both are raw protocols** — Ona's REST `POST`, jaato's WS frames; jaato additionally layers an SDK on top (above), which Ona has no equivalent of. Both hand back an **id for a server-side run** (`agentExecutionId` / `sid`) and detach. Ona starts the agent in a **cloud devcontainer** it provisions (with a Codex/OpenAI model + a `mode` — execution / planning / "RALPH"); jaato starts a **session** in an isolated runner on the daemon **you host**, with the model/provider/plugins from a profile. Ona binds the run to a **git project / PR / context URL**; jaato binds it to a **workspace**.

## 2. Check status / collect output

**Ona** — poll the execution:
```bash
curl -X POST https://app.gitpod.io/api/gitpod.v1.AgentService/GetAgentExecution \
  -H "Authorization: Bearer $GITPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{ "agentExecutionId": "uuid" }'
# → status.phase: PHASE_PENDING|RUNNING|WAITING_FOR_INPUT|STOPPED
#   status.conversationUrl, status.transcriptUrl, inputTokensUsed/outputTokensUsed
```

**jaato** — reconnect and reattach by id. A fresh WS connection auto-provisions its *own* workspace, so re-attaching a detached run is a 3-step handshake — discover it, select its workspace, then attach:
```bash
→ {"type":"command.execute","command":"session.list"}                                 # find the session + its workspace_path
→ {"type":"command.execute","command":"workspace.select","args":["<workspace_path>"]}  # re-target the session's workspace
→ {"type":"command.execute","command":"session.attach","args":["<sid>"]}
# ← {"type":"agent.output","text":"…"}        # FIRST replayed history, THEN live output (raw attach replays prior turns)
# ← {"type":"turn.completed", ...}             # a plain turn ends here…
# ← {"type":"session.terminated", ...}         # …or here if the agent is completion-gated
```

**Runnable:** [`examples/ws/ex2_attach_replay.mjs`](../examples/ws/ex2_attach_replay.mjs)

**Side by side.** Ona is **poll-based** — you `GetAgentExecution` for a `phase` and links to the conversation/transcript (and token usage). jaato is **event-based** — you re-attach and consume `AGENT_OUTPUT`/lifecycle events live (no polling), with the run's transcript persisted server-side. (On a raw attach the daemon first **replays the session's prior history** as `agent.output` events, *then* streams live output — declare a `chat` presentation via `ClientConfigRequest` to skip the replay.) Attaching a session you haven't `workspace.select`'d first returns a bare **`Session not found`** — **intentionally opaque** (confirming the session by name would leak cross-workspace session existence), so `workspace.select` is the legitimate re-target, not a rough edge. Different I/O models for the same "watch a detached run" need.

## 3. Send follow-up input to a running agent

**Ona**
```bash
curl -X POST https://app.gitpod.io/api/gitpod.v1.AgentService/SendToAgentExecution \
  -H "Authorization: Bearer $GITPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{ "agentExecutionId": "uuid", "userInput": { "text": { "content": "Also add tests." } } }'
```

**jaato** — after the §2 re-attach handshake (`session.list` → `workspace.select` → `session.attach`), just send:
```bash
→ {"type":"command.execute","command":"session.attach","args":["<sid>"]}   # workspace already selected — see §2
→ {"type":"message.send","text":"Also add tests."}     # continue the same running session
```

**Runnable:** [`examples/ws/ex3_attach_followup.mjs`](../examples/ws/ex3_attach_followup.mjs)

**Side by side.** Same capability — steer a long-running agent mid-flight. Ona's `WAITING_FOR_INPUT` phase + `SendToAgentExecution` mirrors jaato re-attaching and sending a `message.send` frame. (jaato can also push a non-blocking nudge via `inject_prompt`, and a *reactor* can do this server-side with no client — see the resilience doc.)

## 4. Stop / list runs

**Ona** — `StopAgentExecution` and `ListAgentExecutions` (filter by agent/project/environment/phase):
```bash
curl -X POST .../StopAgentExecution    -d '{ "agentExecutionId": "uuid" }'   # …auth headers…
curl -X POST .../ListAgentExecutions   -d '{ "projectIds": ["proj_123"] }'    # …auth headers…
```

**jaato**
```bash
→ {"type":"session.stop","agent_id":null}                        # cancel the in-flight turn (null = current/all)
→ {"type":"command.execute","command":"session.end","args":[]}   # end current; or session.delete ["<sid>"] by id
→ {"type":"command.execute","command":"session.list","args":[]}  # ← replies with a SessionList event
```

**Runnable:** [`examples/ws/ex4_lifecycle.mjs`](../examples/ws/ex4_lifecycle.mjs)

**Side by side.** Symmetric lifecycle controls — stop a run, enumerate runs. Ona scopes its list by **project/environment**; jaato by the **daemon's** session registry.

## 5. Event-triggered background agents

**Ona** — **Automations** (`automations.yaml` + `devcontainer.json`) run agents on a schedule, on PR events, or from an issue tracker, in a fully provisioned environment:
```yaml
# automations.yaml — a proactive background agent
services: {}
tasks:
  review-prs:
    triggeredBy: ["pullRequestOpened"]
    command: "ona-agent run --task 'Review this PR for security issues'"
```

**jaato** — a long-running **host session** loads the `webhook` plugin; inbound webhooks publish an `external_event` on the bus, which a **reactor** turns into a review session:
```jsonc
// .jaato/reactors/on_pr.json — fire on an inbound webhook, spawn a review session
{ "rules": [{ "id": "review.on_pr",
              "match": { "event_type": "external_event", "where": "source == 'github'" },
              "action": { "script": "scripts/spawn_review.py" } }] }
```
```python
# scripts/spawn_review.py — runs INSIDE the daemon on that event
def execute(params, event, ctx):
    ctx.create_session(agent="reviewer", profile="reviewer",        # persona (soul) + profile (substrate)
                       initial_prompt=f"Review PR {event.get('pr')} for security issues.")
```

**Runnable** *(reactor asset — the same pattern as the cascade, not a WS frame)*: [`examples/python-sdk/.jaato/reactors/cascade.json`](../examples/python-sdk/.jaato/reactors/cascade.json) + [`scripts/spawn_summarize.py`](../examples/python-sdk/.jaato/scripts/spawn_summarize.py)

**Side by side.** Both turn **external events into background agent runs**. Ona's `automations.yaml` is declarative and git/CI-native (it *is* a Gitpod-heritage CI surface). jaato's inbound edge is the **`webhook` plugin** (HMAC-verified GitHub/Slack routes, IP allowlists, mTLS), loaded in a long-running host session; it publishes an `external_event` on the daemon's bus that a **reactor** turns into a session — the same reactor shape as a cascade, so one event can spawn a session or chain a whole pipeline. (jaato has **no built-in scheduler**: for *external HTTP* use the webhook plugin as shown; for *cron/CI* either drive a client — the TS client over WS, or a local `IPCClient` → `createSession`/`sendMessage` — or have the scheduled job POST the webhook listener.)

## 6. Environment & isolation

**Ona** — each agent runs in a **devcontainer-defined cloud environment** (`devcontainer.json`), in Ona's cloud or **inside your VPC**, with prebuilt snapshots for fast startup and kernel-level isolation + enterprise governance (RBAC/SSO/OIDC/audit).

**jaato** — each session runs in its **own per-session subprocess** (a pre-warmed pool slot or cold spawn), **AppArmor-confinable** and **cgroup-boundable** (`memory.max`), scoped to a **workspace**, on infrastructure **you host** (any cloud, on-prem, local GPUs).

**Side by side.** Both isolate each agent run and support self-hosting (Ona-in-your-VPC / jaato-on-your-infra). Ona's unit is a **devcontainer** (full dev environment, git-native, managed + governed for you); jaato's is an **AppArmor-confined runner** under a profile (provider-agnostic, you own the governance). Ona optimizes startup with **prebuild snapshots**; jaato with a **pre-warm runner pool** (~7s warm vs ~30s cold).

---

## Coming from Ona

Not a scorecard — if you run agents on Ona, here's what actually changes when you self-host jaato, and what it buys you:

- **`StartAgent` REST → the daemon's WS protocol (plus a TS facade).** Where you `POST` to `gitpod.v1.AgentService/StartAgent` and get an `agentExecutionId` back, jaato hands you an open **JSON wire protocol** over `wss://` — the same launch-and-detach shape (`session.new` + `message.send`, close the socket, the run keeps going), callable raw with `curl`/`websocat`, **plus** a **TypeScript** facade (`JaatoClient.session({url:"wss://…"})`) over that exact wire. Ona has no SDK at all; jaato gives you both the raw frames *and* the convenience layer.
- **Managed cloud devcontainers → AppArmor/cgroup-isolated subprocesses on infra you host.** Ona provisions a **devcontainer** in its cloud (or your VPC) per run, with prebuild snapshots and kernel isolation it governs for you. jaato runs each session as its **own per-session subprocess** — **AppArmor-confinable**, **cgroup-boundable** (`memory.max`), scoped to a workspace, on any cloud / on-prem / **local GPUs** you own, warmed from a pre-warm pool (~7s warm vs ~30s cold). You trade managed-for-you for owned-by-you.
- **Codex/OpenAI-centric → provider- and runtime-agnostic.** Ona is built around **Codex/OpenAI models** (`codexSettings`, the cloud-execution backend for Codex since the June 2026 acquisition). jaato binds the model/provider to a **profile** — Anthropic, Google, OpenAI, local vLLM/Ollama, whatever — so the same orchestration outlives any one vendor.
- **`automations.yaml` on git events → reactor rules on the daemon bus.** Ona's git/CI-native **Automations** fire an agent on `pullRequestOpened`/schedule in a provisioned environment. jaato's `webhook` plugin turns inbound events into an `external_event` on the bus, which a **reactor** turns into a session — the same reactor shape that drives **cascades** (one event chaining a whole pipeline) and **server-enforced completion gates**, with status arriving as **live events** you re-attach to rather than a `phase` you poll for.

**What to keep in mind (honest trade-offs).**
- This is a **platform comparison**, compared at the **wire level** and on jaato's **remote (WebSocket)** transport — the apt analog to Ona's remote HTTPS, not an SDK-usage walkthrough. Ona's surface is a **gRPC-JSON REST API** (curl) with **no SDK**, still under the `gitpod.v1` / `app.gitpod.io` namespace from its Gitpod origins (verify endpoints against the current API reference). jaato's remote surface is the **WS protocol** (`curl`/`websocat` — used throughout) **plus** the **TypeScript** facade over `wss://` (shown once, Example 1) — a convenience layer over the same wire you can hit raw, not a different level. **Mind the transport split:** jaato's **Python** `IPCClient` is the **local** (Unix-socket / IPC) client and does **not** speak WS — the remote client is the **TS** SDK (or raw WS); don't read the Python examples in the SDK-comparison docs as the remote path. The WS and IPC surfaces are otherwise feature-par (same command/event protocol).
- **Ona's managed, OpenAI-centric cloud is a real advantage, not a deficit.** It runs **in Ona's cloud (or your VPC)** around **Codex/OpenAI models** (`codexSettings`) and gives you enterprise **RBAC/SSO/OIDC/audit**, git/PR-native automations, prebuilds, and **zero infra to run** — for free, out of the box. Self-hosting jaato is the opposite trade: it's **provider-agnostic** and **yours**, but you run, secure, and govern it yourself — more to operate in exchange for model-portability and control.
- **Different I/O & maturity.** Ona is poll-based (`GetAgentExecution`) and git/CI-shaped; jaato is event-based (the bus + reactors) and persona/profile/cascade-shaped. They overlap most on *background, isolated, recoverable, steerable* agents — and least on tool-authoring and typed output, which Ona doesn't expose as a build API.
