import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
// Dedicated daemon WS endpoint (same daemon python-sdk/daemon.sh runs).
export const URL = "wss://localhost:8099";
export const TOKEN = readFileSync(join(homedir(), ".jaato", "ws.token"), "utf8").trim();
// Inline session spec (the docs show `--profile backend`; we use an inline spec so
// it runs against a fresh daemon with no pre-installed profile). The api_key knob
// uses ${ENV_VAR} interpolation, expanded by the daemon against ITS process
// environment (no env_file over WS) — export JAATO_OPENROUTER_API_KEY before
// starting the shared daemon (daemon.sh). This used to be a "pass://" secret URI,
// whose resolver ships only in the private jaato-premium package (on a public
// checkout it does not resolve — the literal URI reaches the provider as the key).
export const SPEC = {
  model: "google/gemini-2.5-flash", provider: "openrouter", plugins: [],
  plugin_configs: { openrouter: { api_key: "${JAATO_OPENROUTER_API_KEY}" } },
};
