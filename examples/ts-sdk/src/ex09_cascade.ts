// ex09 — Multi-stage pipeline: a real cascade (event + reactor driven).
//
// Appears in: mastra.md §9 (the stage-1 client trigger; the .jaato/reactors +
// scripts halves are language-agnostic — the daemon runs them).
//
// Doc snippet (verbatim shape):
//
//   import { randomUUID } from "node:crypto";
//   const cid = randomUUID();
//   await using s = await JaatoClient.session({ url, agent: "extract", profile: "extract", cascadeDriverId: cid });
//   await s.complete("Extract the facts from this doc: …");   // stage 1's first message
//
// The client only triggers stage 1; the reactor chain runs decoupled in the
// daemon — extract → summarize → verify, each completion-gated, the typed payload
// threading via event.get(field). Identical .jaato/ assets to
// examples/python-sdk (the reactor scripts are daemon-side python). Real
// cross-stage data flow needs the typed-payload bus-hoist (jaato PR #414, on
// main). The reactor + scripts live in .jaato/, so this passes
// workspacePath + configRoot.
//
// Standing substitutions (see README): `...CONN`. (Model/provider + plugins live
// in the profile JSONs.)

import { randomUUID } from "node:crypto";
import { JaatoClient } from "@jaato/sdk";
import { CONN, WORKSPACE, CONFIG_ROOT } from "./_config.js";

const cid = randomUUID();
await using s = await JaatoClient.session({
  ...CONN,
  workspacePath: WORKSPACE,
  configRoot: CONFIG_ROOT,
  agent: "extract",
  profile: "extract",
  cascadeDriverId: cid,
});
await s.complete(
  "Extract the facts from this doc: Tide pools form in the rocky intertidal zone. " +
    "They host anemones, starfish, and crabs. They are exposed at low tide and submerged at high tide.",
);
console.log(`stage 1 (extract) done; cascade ${cid} continues in the daemon (summarize → verify)`);
