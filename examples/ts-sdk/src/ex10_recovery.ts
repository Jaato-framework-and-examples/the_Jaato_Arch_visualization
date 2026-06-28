// ex10 — Production: persistence, recovery, observability (recovery client).
//
// Appears in: mastra.md §10. In the TS SDK, recovery is a session option
// (`recovery: {}` + `onStatusChange`), not a separate client class.
//
// Doc snippet (verbatim shape):
//
//   await using s = await JaatoClient.session({
//     url, profile: {...},
//     recovery: {},                                   // auto-reconnect across daemon restarts
//     onStatusChange: (st) => console.log(st.state),  // reconnecting / connected / closed
//   });
//   console.log(await s.ask("Long task…"));
//
// Standing substitutions (see README): `...CONN`, `...AUTH`, the model literal,
// the `plugins` key.

import { JaatoClient } from "@jaato/sdk";
import { CONN, AUTH } from "./_config.js";

await using s = await JaatoClient.session({
  ...CONN,
  profile: { model: "google/gemini-2.5-flash", provider: "openrouter", plugins: [], ...AUTH },
  recovery: {}, // auto-reconnect across daemon restarts
  onStatusChange: (st) => console.log(st.state), // reconnecting / connected / closed
});
console.log(await s.ask("Long task…")); // survives a daemon bounce
