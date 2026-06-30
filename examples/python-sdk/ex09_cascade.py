"""ex09 — Multi-stage pipeline: a real cascade (event + reactor driven). ONE
example, two DAEMON transports:

    python ex09_cascade.py ipc
    python ex09_cascade.py ws

Each stage runs a persona (agent=) under a profile, and needs a first message
(its task): the client supplies STAGE 1's, and a daemon reactor injects every
later stage's from the prior stage's output. The client only triggers stage 1
and threads `cascade_driver_id`; the pipeline then runs DECOUPLED in the daemon
(it survives the client disconnecting). See .jaato/reactors/cascade.json +
.jaato/scripts/spawn_summarize.py.

The cascade runs SERVER-SIDE (the reactor spawns each next stage in the daemon),
so it is a DAEMON feature: ex09's two modes are the two daemon transports (ipc +
ws) — `jaato.session(mode=...)` threads cascade_driver_id identically over each.
There is no in_process variant: the cascade's value IS the daemon decoupling, and
the reactor engine is a daemon extension not wired to the embedded runtime.

Appears in: pydantic-ai.md §9, langchain.md §9, agno.md §9, claude-agent.md §9,
openai-agents.md §9, strands.md §9. (The .jaato/reactors/cascade.json +
spawn_summarize.py halves are byte-identical across all six Python docs.)

The runnable cascade is the full 3-stage chain the cascade docs (09/10) dissect:
  extract --(reactor on agent.completed)--> summarise --(reactor)--> verify
each stage completion-gated (completion_payload_schema: extract→`facts`,
summarise→`summary`, verify→`verdict`) so the next reactor fires and the typed
payload threads via `event.get(<field>)` (see spawn_summarize.py / spawn_verify.py).
The client triggers stage 1 (extract); watch the daemon log, or attach a
`s.client.cascade_events(cid, ...)` observer, for the rest.

Standing deviations (see README): the dedicated-daemon connection (ipc socket /
ws url+token+ca). Model/provider + plugins live in the profile JSONs.

Scaffold a comparable skeleton — this file then customizes it:
    jaato-scaffold new cascade --workspace . --provider openrouter --model google/gemini-2.5-flash --transport ipc
    jaato-scaffold new cascade --workspace . --provider openrouter --model google/gemini-2.5-flash --transport ws --url wss://localhost:8099 --ca ~/.jaato/certs/ca.crt
"""
import asyncio
import sys
import uuid

import jaato
from _config import CONN, WORKSPACE, WS_URL, WS_CA, ws_token

mode = sys.argv[1] if len(sys.argv) > 1 else "ipc"
# ipc connects over the local Unix socket; ws over the remote ws:// endpoint + a
# token + the daemon's self-signed dev CA. The cascade itself runs daemon-side
# either way — the transport only carries the stage-1 trigger.
conn = dict(CONN) if mode == "ipc" else {"url": WS_URL, "token": ws_token(), "ca": WS_CA}


async def main():
    cid = uuid.uuid4().hex
    async with jaato.session(mode=mode, workspace_path=WORKSPACE,
                             agent="extract", profile="extract",
                             cascade_driver_id=cid, **conn) as s:
        # Stage 1's first message (its task). A real document in place of the doc's "…".
        await s.complete(
            "Extract the facts from this doc: "
            "Tide pools form in the rocky intertidal zone. They host anemones, "
            "starfish, and crabs. They are exposed at low tide and submerged at high tide.")
    print(f"[{mode}] stage 1 (extract) done; cascade {cid} continues in the daemon (summarize stage)")


asyncio.run(main())
