// ex03 — System prompt + multi-turn memory (persona + session-as-memory).
//
// Appears in: mastra.md §3. The system prompt is a persona file
// (.jaato/agents/pirate.md); the daemon session IS the memory — two s.ask calls
// in one session continue the conversation.
//
// Doc snippet (verbatim shape):
//
//   await using s = await JaatoClient.session({ url, agent: "pirate", profile: {...} });
//   await s.ask("Hello");
//   console.log(await s.ask("And your name?"));        // same session → it remembers
//
// `agent: "pirate"` resolves from <workspace>/.jaato/agents/pirate.md, so this
// passes `workspacePath: WORKSPACE`. Standing substitutions (see README):
// `...CONN`, `...AUTH`, the model literal, the `plugins` key.

import { JaatoClient } from "@jaato/sdk";
import { CONN, AUTH, WORKSPACE, CONFIG_ROOT } from "./_config.js";

await using s = await JaatoClient.session({
  ...CONN,
  workspacePath: WORKSPACE,
  configRoot: CONFIG_ROOT,
  agent: "pirate",
  profile: { model: "google/gemini-2.5-flash", provider: "openrouter", plugins: [], ...AUTH },
});
await s.ask("Hello");
console.log(await s.ask("And your name?")); // same session → it remembers
