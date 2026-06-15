# Component Doc Template & Style Spec

Every file in `components/` follows this exact structure. Each doc is **standalone** — it can be
handed to an illustration agent on its own, with no other doc as context. Re-introduce the minimum
context needed (one line on where the piece sits) rather than relying on sibling docs.

Audience: a technical reader who knows what an LLM agent is, but does **not** know jaato internals.
Tone: explanatory, concrete, grounded in the real code. Prefer real names/fields/paths over invented ones.

---

## Required sections (in this order)

```markdown
# <Component Name>

> **One-sentence definition.**
> **Layer (bottom→top):** <where it sits> · **Lives in:** <repo>/<paths>

## What it is
2–4 short paragraphs in plain language. Lead with the problem it solves.

## Where it sits in the stack
One paragraph naming the component directly *below* it, directly *above* it, and what it talks to
sideways. This is the "you are here" anchor that makes the doc standalone.

## Responsibilities
- Bulleted list of what it owns / is accountable for.

## Key concepts & structure
Subsections (`###`) for the important sub-parts, classes, files, or fields — using the **real**
identifiers from the source.

## Lifecycle / flow
Numbered steps of how it is created → used → torn down (or request→response).

## Configuration / authoring  *(omit if not user-configurable)*
Real config keys, file locations (`.jaato/...`), and a short real example block.

## Relationship to neighboring components
Short prose linking it to the pieces below/above by name (Daemon, Runner, Persona, Cascade, …).

## Example
One concrete end-to-end example: a config snippet, a code path, or a narrated scenario.

## Diagram brief (for illustration)
A precise, self-contained description of the visual to generate for the PPT/HTML slide.
Write it so an image model needs nothing else. Include:
- **Layout:** overall shape (layered stack / flow left-to-right / hub-and-spoke / sequence).
- **Boxes:** every node to draw, with its label.
- **Arrows:** every connection, with direction + a short edge label.
- **Emphasis:** what to highlight (the component this doc is about).
- **Caption:** a one-line caption for the slide.

## Source references
- `path:line` — what's there. (3–8 anchors.)
```

---

## Rules
- **Standalone:** never write "as described in the cascades doc"; restate the one fact you need.
- **Grounded:** read the cited source before writing. If a detail isn't in the code/docs, say
  "not specified in source" rather than inventing it.
- **Real identifiers:** class names, function names, env vars, `.jaato/` paths, schema keys — exact.
- **Length:** ~250–600 words of prose + the diagram brief. Dense, not padded.
- **Diagram brief is mandatory** — it is the whole point (these docs feed an image-generation agent).
