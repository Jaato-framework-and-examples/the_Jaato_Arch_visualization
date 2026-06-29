// ex06 — Multi-tool agent loop (the daemon IS the loop).
//
// Appears in: mastra.md §6. You pick the server-side plugin set and send one
// message; the model → tool calls → results → model loop runs in the runner.
//
// Doc snippet (verbatim shape):
//
//   await using s = await JaatoClient.session({ url, profile: {
//     model: "gpt-4o", provider: "openai",
//     plugins: ["cli", "web_search", "file_edit", "todo"],
//   } });
//   console.log(await s.ask("Plan a trip to Paris and save it to trip.md"));
//
// Same daemon-side findings as examples/python-sdk/ex06 (see its header + the
// README): jaato gates file/cli tools (set a permissive policy); file_edit won't
// initialise on this build (PR-146), so file work goes via cli; and the vague
// "plan a trip and save it" is a flaky loop trigger (models ask for clarification
// — which errors headless — or just print the answer). So the live set is
// cli + web_search + todo and the task REQUIRES tool output (→ report.txt).
//
// Standing substitutions (see README): `...CONN`, `...AUTH`, the model literal,
// the permissive policy, the reduced plugin set + tool-requiring task.

import { JaatoClient } from "@jaato/sdk";
import { CONN, AUTH, WORKSPACE, CONFIG_ROOT } from "./_config.js";

await using s = await JaatoClient.session({
  ...CONN,
  workspacePath: WORKSPACE,
  configRoot: CONFIG_ROOT,
  profile: {
    model: "google/gemini-2.5-flash",
    provider: "openrouter",
    plugins: ["cli", "web_search", "todo"], // file_edit dropped — see header
    plugin_configs: { ...AUTH.plugin_configs, permission: { policy: { defaultPolicy: "allow" } } },
  },
});
console.log(
  await s.ask(
    "Using the shell, get the current date with `date` and the directory listing " +
      "with `ls`, then write both into a file called report.txt. Do not ask " +
      "questions; just do it.",
  ),
);
