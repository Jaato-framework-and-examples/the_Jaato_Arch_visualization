# Platform comparison: **Ona** vs **jaato**

> A different genre from the [SDK comparisons](../sdk-comparisons/): those put jaato-sdk next to *libraries* you build an agent with. **Ona is a platform, not a library** — there's no `Agent(...)` to write; you call an API to launch agents that run in its cloud. So this compares the two as **platform peers** — managed cloud agent service vs self-hosted agent daemon — on their orchestration API and their architecture.

Of everything compared in this series, Ona is the **closest architectural peer** to jaato: in both, a thin client **launches isolated, long-running, recoverable agents that run server-side**, and you observe/steer them over an API. The split is *where the server is and how open it is*:

- **Ona** (formerly Gitpod; **acquired by OpenAI, June 2026**) is a **managed cloud platform** for background software-engineering agents. You `POST` to its API to start an agent that runs in a **devcontainer-based cloud environment** (Ona's cloud or your VPC), governed by enterprise controls (RBAC/SSO/OIDC/audit). It is **OpenAI/Codex-centric** (`codexSettings`), with **Automations** that fire agents on git/schedule events and ~10-minute checkpointing for long runs.
- **jaato** is a **self-hosted daemon**: you run it, and a thin client opens **sessions** that run as **isolated, AppArmor-confinable per-session subprocesses** with your own personas/profiles/plugins. It is **provider- and runtime-agnostic** (any model, local GPUs), with **reactor-driven cascades**, **server-enforced completion gates**, and out-of-band HITL.

So both are "launch agents server-side and drive them as a client." Ona gives you a managed, governed, OpenAI-powered cloud you call; jaato gives you a provider-agnostic engine you host and shape. Read it as a trade, not a scoreboard.

> **Setup.** Ona: a `GITPOD_API_KEY`; calls are **gRPC-JSON over HTTPS** at `https://app.gitpod.io/api/` (the `gitpod.v1` namespace persists from the Gitpod heritage) — **no first-party SDK**, so its examples are `curl`. jaato: a daemon you run with a **WebSocket** endpoint (`--web-socket :8089`) + a bearer token; its wire protocol is **JSON frames over WS**, callable with `curl`/`websocat`. To keep this honest at the wire level, Example 1 shows **both sides as raw protocol calls** (Ona REST ↔ jaato WS); the rest use jaato's **SDK** (`from jaato_sdk import IPCClient, ClientType, EventType`) — which is itself something Ona has no equivalent of — each mapping to the same WS frames.

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

**jaato** — *same wire level as Ona:* raw **WS frames** over the daemon's WebSocket endpoint (bearer token):
```bash
websocat "wss://localhost:8089/?token=$JAATO_WS_TOKEN"   # CLI clients may use an Authorization: Bearer header
# ← {"type":"connected","server_info":{...}}
→ {"type":"command.execute","command":"session.new","args":["--profile","backend"]}
→ {"type":"message.send","text":"Refactor the auth module and open a PR."}
# ← the daemon streams events back:  {"type":"agent.output","text":"…"}  …  {"type":"turn.completed", ...}
```
…or jaato's **SDK** (the convenience layer Ona lacks) over the *same* protocol — here fire-and-forget, leaving the run going:
```python
from jaato_sdk import IPCClient, ClientType
client = IPCClient("/tmp/jaato.sock", client_type=ClientType.API, env_file=".env", workspace_path=".")
await client.connect(timeout=120.0)
sid = await client.create_session(profile={"model": "gpt-4o", "provider": "openai"})
await client.send_message("Refactor the auth module and open a PR.")
await client.disconnect()                # disconnect does NOT cancel — the turn runs to completion daemon-side
print(sid)                               # state persists to disk; reattach by id later (reloads it) — see §2
```

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

**jaato** — reattach by id and consume the event stream:
```python
await client.connect(timeout=120.0)
await client.attach_session(sid)                       # re-attach WHILE the turn runs → live output
client.subscribe(EventType.AGENT_OUTPUT, lambda e: print(getattr(e, "text", ""), end=""))
client.subscribe_once(EventType.TURN_COMPLETED, lambda e: done.set())       # a plain turn ends here…
client.subscribe_once(EventType.SESSION_TERMINATED, lambda e: done.set())   # …or here if completion-gated
await done.wait()
```

**Side by side.** Ona is **poll-based** — you `GetAgentExecution` for a `phase` and links to the conversation/transcript (and token usage). jaato is **event-based** — you re-attach and consume `AGENT_OUTPUT`/lifecycle events live (no polling), with the run's transcript persisted server-side. Different I/O models for the same "watch a detached run" need.

## 3. Send follow-up input to a running agent

**Ona**
```bash
curl -X POST https://app.gitpod.io/api/gitpod.v1.AgentService/SendToAgentExecution \
  -H "Authorization: Bearer $GITPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{ "agentExecutionId": "uuid", "userInput": { "text": { "content": "Also add tests." } } }'
```

**jaato**
```python
await client.attach_session(sid)
await client.send_message("Also add tests.")           # continue the same running session
```

**Side by side.** Same capability — steer a long-running agent mid-flight. Ona's `WAITING_FOR_INPUT` phase + `SendToAgentExecution` mirrors jaato re-attaching and `send_message`-ing the session. (jaato can also push a non-blocking nudge via `inject_prompt`, and a *reactor* can do this server-side with no client — see the resilience doc.)

## 4. Stop / list runs

**Ona** — `StopAgentExecution` and `ListAgentExecutions` (filter by agent/project/environment/phase):
```bash
curl -X POST .../StopAgentExecution    -d '{ "agentExecutionId": "uuid" }'   # …auth headers…
curl -X POST .../ListAgentExecutions   -d '{ "projectIds": ["proj_123"] }'    # …auth headers…
```

**jaato**
```python
await client.stop()                                    # cancel the in-flight turn
await client.end_session()                             # or end_session/delete_session by id
await client.list_sessions()                           # enumerate sessions (→ event with the list)
```

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

**Side by side.** Both turn **external events into background agent runs**. Ona's `automations.yaml` is declarative and git/CI-native (it *is* a Gitpod-heritage CI surface). jaato's inbound edge is the **`webhook` plugin** (HMAC-verified GitHub/Slack routes, IP allowlists, mTLS), loaded in a long-running host session; it publishes an `external_event` on the daemon's bus that a **reactor** turns into a session — the same reactor shape as a cascade, so one event can spawn a session or chain a whole pipeline. (jaato has **no built-in scheduler**: for *external HTTP* use the webhook plugin as shown; for *cron/CI* either drive a client — `IPCClient` → `create_session` + `send_message` — or have the scheduled job POST the webhook listener.)

## 6. Environment & isolation

**Ona** — each agent runs in a **devcontainer-defined cloud environment** (`devcontainer.json`), in Ona's cloud or **inside your VPC**, with prebuilt snapshots for fast startup and kernel-level isolation + enterprise governance (RBAC/SSO/OIDC/audit).

**jaato** — each session runs in its **own per-session subprocess** (a pre-warmed pool slot or cold spawn), **AppArmor-confinable** and **cgroup-boundable** (`memory.max`), scoped to a **workspace**, on infrastructure **you host** (any cloud, on-prem, local GPUs).

**Side by side.** Both isolate each agent run and support self-hosting (Ona-in-your-VPC / jaato-on-your-infra). Ona's unit is a **devcontainer** (full dev environment, git-native, managed + governed for you); jaato's is an **AppArmor-confined runner** under a profile (provider-agnostic, you own the governance). Ona optimizes startup with **prebuild snapshots**; jaato with a **pre-warm runner pool** (~7s warm vs ~30s cold).

---

## When each shines

| You want… | Reach for |
|---|---|
| A **managed, governed cloud** for background software-engineering agents — devcontainer environments, git/PR-native automations, prebuilds, enterprise RBAC/SSO/audit, zero infra to run | **Ona** |
| OpenAI/Codex agents with long-running cloud execution + checkpointing, callable from CI/issue trackers | **Ona** |
| A **self-hosted, provider- and runtime-agnostic** agent engine (any model, **local GPUs**); your own personas/profiles/plugins; reactor-driven cascades; server-enforced typed completion gates; AppArmor-isolated, multi-tenant sessions; out-of-band HITL — all under your control | **jaato** |

**Honest caveats.**
- This is a **platform comparison**, compared at the **wire level**: Ona's surface is a **gRPC-JSON REST API** (curl) with **no SDK**, still under the `gitpod.v1` / `app.gitpod.io` namespace from its Gitpod origins (verify endpoints against the current API reference). jaato's wire surface is a **WebSocket protocol** (`curl`/`websocat`, Example 1) **plus** Python/TS SDKs — so the SDK examples below are jaato's *convenience layer over the same protocol you can hit raw*, not a different level.
- **Ona is managed + OpenAI-centric.** It runs **in Ona's cloud (or your VPC)** and is built around **Codex/OpenAI models** (`codexSettings`); since the June 2026 OpenAI acquisition it's the cloud-execution backend for Codex. jaato is **self-hosted** and **provider-agnostic** (Anthropic, Google, OpenAI, local vLLM/Ollama/…), which is the opposite trade: more to run, but yours and model-portable.
- **Different I/O & maturity.** Ona is poll-based (`GetAgentExecution`) and git/CI-shaped; jaato is event-based (the bus + reactors) and persona/profile/cascade-shaped. They overlap most on *background, isolated, recoverable, steerable* agents — and least on tool-authoring and typed output, which Ona doesn't expose as a build API.
