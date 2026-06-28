// Harness wiring for the ts-sdk examples — NOT part of the SDK surface.
//
// The comparison doc (sdk-comparisons/mastra.md) shows each example connecting
// with `JaatoClient.session({ url: "wss://localhost:8089", profile: {...} })`.
// To run end-to-end against a real model, every example connects to the
// dedicated daemon's WebSocket endpoint with a bearer token, and substitutes a
// locally-reachable OpenRouter model. Those harness bits are centralised here so
// the SDK call shape inside each example stays verbatim-to-doc.
//
// The daemon's WS is `wss` (TLS) with a self-signed Jaato Dev CA. Node trusts it
// via NODE_EXTRA_CA_CERTS=$HOME/.jaato/certs/ca.crt — set by run.sh (so the
// example files don't carry TLS plumbing). The bearer token is read from the
// daemon's ~/.jaato/ws.token (no secret committed).

import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

// Dedicated daemon's WS endpoint — the same daemon python-sdk/daemon.sh runs
// (it serves both the IPC socket and this WS port).
const URL = "wss://localhost:8099";
const TOKEN = readFileSync(join(homedir(), ".jaato", "ws.token"), "utf8").trim();

// Connection knobs spread into JaatoClient.session({...}) — `...CONN` is the
// harness prefix; everything after it is the doc's verbatim shape.
export const CONN = { url: URL, token: TOKEN };

// Provider credential as a `pass:` resolver knob of the provider plugin (never an
// env var / committed secret). Spread into inline profiles as `...AUTH`;
// declarative profiles carry the same knob in their JSON.
export const AUTH = {
  plugin_configs: { openrouter: { api_key: "pass://jaato/openrouter/api-key" } },
};

// The docs write the inline profile as {model:"gpt-4o", provider:"openai"}; the
// examples substitute a cheap OpenRouter model with reliable tool-calling.
export const MODEL = "google/gemini-2.5-flash";
export const PROVIDER = "openrouter";
