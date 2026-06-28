// ex05 — A single client-provided ("host") tool.
//
// Appears in: mastra.md §5. The daemon's agent loop invokes the schema and calls
// back into your process for the handler.
//
// Doc snippet (verbatim shape):
//
//   await using s = await JaatoClient.session({
//     url, profile: {...},
//     clientTools: [{
//       name: "get_weather", description: "Return the weather for a city.",
//       parameters: { type: "object", properties: { city: { type: "string" } }, required: ["city"] },
//       handler: (args) => ({ weather: `${args.city}: sunny, 24C` }),
//     }],
//   });
//   console.log(await s.ask("Weather in Paris?"));
//
// Standing substitutions (see README): `...CONN`, `...AUTH`, the model literal,
// the `plugins` key.

import { JaatoClient } from "@jaato/sdk";
import { CONN, AUTH } from "./_config.js";

await using s = await JaatoClient.session({
  ...CONN,
  profile: { model: "google/gemini-2.5-flash", provider: "openrouter", plugins: [], ...AUTH },
  clientTools: [
    {
      name: "get_weather",
      description: "Return the weather for a city.",
      parameters: { type: "object", properties: { city: { type: "string" } }, required: ["city"] },
      handler: (args) => ({ weather: `${args.city as string}: sunny, 24C` }), // runs in YOUR process
    },
  ],
});
console.log(await s.ask("Weather in Paris?"));
