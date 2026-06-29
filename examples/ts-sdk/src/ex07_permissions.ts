// ex07 — Human-in-the-loop tool approval (onPermission).
//
// Appears in: mastra.md §7.
//
// Doc snippet (verbatim shape):
//
//   await using s = await JaatoClient.session({
//     url, profile: { model: "gpt-4o", provider: "openai", plugins: ["cli"] },
//     onPermission: (ev) => (confirm(`allow ${ev.tool_name}?`) ? "y" : "n"),
//   });
//   console.log(await s.ask("Delete temp.log"));
//
// Same finding as examples/python-sdk/ex07: the doc's "Delete temp.log" is a
// flaky gate trigger (models refuse a destructive shell delete, or answer
// conversationally instead of calling the tool). The onPermission mechanism is
// identical for ANY gated tool, so we make the gate fire deterministically: ask
// for something only the shell can provide (the system `date`) with
// defaultPolicy "ask" so every cli call is gated → onPermission is asked.
//
// Standing substitutions (see README): `...CONN`, `...AUTH`, the model literal,
// the ask-policy + benign command.

import { JaatoClient } from "@jaato/sdk";
import { CONN, AUTH, WORKSPACE, CONFIG_ROOT } from "./_config.js";

function approve(toolName: string): boolean {
  // In a UI this would prompt; headless, we auto-approve and log the gate.
  console.log(`[permission] ${toolName} -> approve`);
  return true;
}

await using s = await JaatoClient.session({
  ...CONN,
  workspacePath: WORKSPACE,
  configRoot: CONFIG_ROOT,
  profile: {
    model: "google/gemini-2.5-flash",
    provider: "openrouter",
    plugins: ["cli"],
    plugin_configs: { ...AUTH.plugin_configs, permission: { policy: { defaultPolicy: "ask" } } },
  },
  onPermission: (ev) => (approve((ev as { tool_name: string }).tool_name) ? "y" : "n"),
});
console.log(
  await s.ask("What is the current date and time on this machine? Find out by running the `date` command in the shell."),
);
