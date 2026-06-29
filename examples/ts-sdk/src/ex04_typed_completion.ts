// ex04 — Structured / typed output (server-enforced completion gate).
//
// Appears in: mastra.md §4. The "person-extractor" profile declares a
// completion_payload_schema; the daemon forces signal_completion(payload),
// validates it, and s.complete() returns the validated object (or null).
//
// Doc snippet (verbatim shape):
//
//   await using s = await JaatoClient.session({ url, profile: "person-extractor" });
//   const person = await s.complete("Alice is 30.");
//   console.log(person?.name, person?.age);
//
// `profile` is a named declarative asset (.jaato/profiles/person-extractor.json
// embeds the schema), so this passes `workspacePath: WORKSPACE`.
// Standing substitutions (see README): `...CONN`. (Model/provider + plugins live
// in the profile JSON.)

import { JaatoClient } from "@jaato/sdk";
import { CONN, WORKSPACE, CONFIG_ROOT } from "./_config.js";

await using s = await JaatoClient.session({
  ...CONN,
  workspacePath: WORKSPACE,
  configRoot: CONFIG_ROOT,
  profile: "person-extractor",
});
const person = await s.complete("Alice is 30."); // object | null (server-validated payload)
console.log(person?.name, person?.age);
