// ex02 — Streaming the reply.
//
// Appears in: mastra.md §2.
//
// Doc snippet (verbatim shape):
//
//   await using s = await JaatoClient.session({ url, profile: {...} });
//   for await (const chunk of s.stream("Tell me a short story.")) process.stdout.write(chunk);
//
// Standing substitutions (see README): `...CONN`, `...AUTH`, the model literal,
// the `plugins` key.

import { JaatoClient } from "@jaato/sdk";
import { CONN, AUTH } from "./_config.js";

await using s = await JaatoClient.session({
  ...CONN,
  profile: { model: "google/gemini-2.5-flash", provider: "openrouter", plugins: [], ...AUTH },
});
for await (const chunk of s.stream("Tell me a short story.")) process.stdout.write(chunk);
process.stdout.write("\n");
