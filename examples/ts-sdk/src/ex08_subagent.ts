// ex08 — Multi-agent / subagent delegation (async, daemon-driven).
//
// Appears in: mastra.md §8. The lead persona delegates via the `subagent`
// plugin; delegation spans many turns, so this drops to the event API and waits
// for SESSION_TERMINATED (not turn.completed).
//
// Doc snippet (verbatim shape):
//
//   await using s = await JaatoClient.session({ url, agent: "lead",
//     profile: { model: "gpt-4o", provider: "openai", plugins: ["subagent"] } });
//   const out: string[] = [];
//   s.client.subscribe(EventTypeValue.AGENT_OUTPUT, (e) => { if (e.text) out.push(e.text); });
//   await new Promise<void>((resolve) => {
//     s.client.subscribeOnce(EventTypeValue.SESSION_TERMINATED, () => resolve());
//     void s.client.sendMessage("Research tide pools, then write a blurb from the findings.");
//   });
//   console.log(out.join(""));
//
// Same deviation as examples/python-sdk/ex08: the prose says the lead must be
// completion-gated, but the doc's inline profile omits the
// completion_payload_schema that exposes signal_completion. This adds the gate (a
// `blurb` schema). Subagent targets (researcher, writer) + the lead persona are
// declarative, so this passes workspacePath + configRoot.
//
// `max_turns` bounds the session so the event-API wait below ALWAYS resolves — a
// completion-gated lead that never calls signal_completion would otherwise hang
// forever. The delegation is fully wired, but whether the lead actually calls
// spawn_subagent is model-dependent; the example demonstrates the wiring either way.
//
// Standing substitutions (see README): `...CONN`, `...AUTH`, the model literal,
// the `plugins` key, + the completion gate.

import { JaatoClient, EventTypeValue } from "@jaato/sdk";
import { CONN, AUTH, WORKSPACE, CONFIG_ROOT } from "./_config.js";

await using s = await JaatoClient.session({
  ...CONN,
  workspacePath: WORKSPACE,
  configRoot: CONFIG_ROOT,
  agent: "lead",
  profile: {
    model: "google/gemini-2.5-flash",
    provider: "openrouter",
    plugins: ["subagent"],
    max_turns: 8,
    completion_payload_schema: {
      type: "object",
      additionalProperties: false,
      required: ["blurb"],
      properties: { blurb: { type: "string", description: "The final composed blurb." } },
    },
    ...AUTH,
  },
});
const out: string[] = [];
s.client.subscribe(EventTypeValue.AGENT_OUTPUT, (e: { text?: string }) => {
  if (e.text) out.push(e.text);
});
await new Promise<void>((resolve) => {
  s.client.subscribeOnce(EventTypeValue.SESSION_TERMINATED, () => resolve()); // NOT turn.completed
  void s.client.sendMessage("Research tide pools, then write a blurb from the findings.");
});
console.log(out.join(""));
