import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
// Dedicated daemon WS endpoint (same daemon python-sdk/daemon.sh runs).
export const URL = "wss://localhost:8099";
export const TOKEN = readFileSync(join(homedir(), ".jaato", "ws.token"), "utf8").trim();
// Inline session spec (the docs show `--profile backend`; we use an inline spec so
// it runs against a fresh daemon with no pre-installed profile). pass: cred knob.
export const SPEC = {
  model: "google/gemini-2.5-flash", provider: "openrouter", plugins: [],
  plugin_configs: { openrouter: { api_key: "pass://jaato/openrouter/api-key" } },
};
