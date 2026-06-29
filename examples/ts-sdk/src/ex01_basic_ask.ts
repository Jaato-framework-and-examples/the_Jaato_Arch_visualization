// ex01 — Hello world: one prompt, one reply.
//
// Appears in: mastra.md §1 (the TypeScript jaato side; the Python docs' §1 maps
// to examples/python-sdk/ex01_basic_ask.py).
//
// Doc snippet (verbatim shape):
//
//   await using s = await JaatoClient.session({ url: "wss://localhost:8089", profile: {...} });
//   console.log(await s.ask("Who are you? One sentence."));
//   // …or the one-shot module helper:
//   console.log(await ask("Who are you? One sentence.", { url: "wss://…", profile: {...} }));
//
// Standing substitutions (see README): `...CONN` (dedicated daemon url + token),
// `...AUTH` (pass: cred knob), the OpenRouter model literal, and the `plugins`
// key the daemon requires on an inline spec.

import { JaatoClient, ask } from "@jaato/sdk";
import { CONN, AUTH } from "./_config.js";

// The session form — the shape mastra.md §1 uses.
await using s = await JaatoClient.session({
  ...CONN,
  profile: { model: "google/gemini-2.5-flash", provider: "openrouter", plugins: [], ...AUTH },
});
console.log(await s.ask("Who are you? One sentence."));

// …or the one-shot module helper, for a throwaway call.
console.log(
  await ask("Who are you? One sentence.", {
    ...CONN,
    profile: { model: "google/gemini-2.5-flash", provider: "openrouter", plugins: [], ...AUTH },
  }),
);
