"""ex09 — Multi-stage pipeline: a real cascade (event + reactor driven).

Appears in: pydantic-ai.md §9, langchain.md §9, agno.md §9, claude-agent.md §9,
openai-agents.md §9, strands.md §9. (The .jaato/reactors/cascade.json +
spawn_summarize.py halves are byte-identical across all six Python docs.)

Each stage runs a persona (agent=) under a profile, and needs a first message
(its task): the client supplies STAGE 1's, and a daemon reactor injects every
later stage's from the prior stage's output. The client only triggers stage 1;
the pipeline then runs DECOUPLED in the daemon (it survives the client
disconnecting). See .jaato/reactors/cascade.json + .jaato/scripts/spawn_summarize.py.

Doc snippet (verbatim shape):

    import uuid
    cid = uuid.uuid4().hex
    async with IPCClient.session(agent="extract", profile="extract",
                                 cascade_driver_id=cid) as s:
        await s.complete("Extract the facts from this doc: …")          # stage 1's first message

The reactor + scripts live in .jaato/, so this passes `workspace_path=WORKSPACE`.
The client triggers stage 1 (extract); the rest runs DECOUPLED in the daemon —
watch the daemon log, or attach a `s.client.cascade_events(cid, ...)` observer.

The comparison docs (§9) show a 2-stage illustration (extract → summarise). The
runnable cascade here is the full 3-stage chain the cascade docs (09/10) dissect:
  extract --(reactor on agent.completed)--> summarise --(reactor)--> verify
each stage completion-gated (completion_payload_schema: extract→`facts`,
summarise→`summary`, verify→`verdict`) so the next reactor fires and the typed
payload threads via `event.get(<field>)` (see spawn_summarize.py / spawn_verify.py).

REAL typed data flow between stages needs server with jaato PR #414 (the
typed-payload bus-hoist this example surfaced). Validated end-to-end on #414:
summarise gets the real facts and verify the real summary (verdict "pass"). On an
older server the stages still spawn (structure works) but the payload reads None.

Standing deviations (see README): `**CONN`. (Model/provider + plugins live in the
profile JSONs.)
"""
import asyncio
import uuid
from jaato_sdk import IPCClient
from _config import CONN, WORKSPACE


async def main():
    cid = uuid.uuid4().hex
    async with IPCClient.session(**CONN, workspace_path=WORKSPACE,
                                 agent="extract", profile="extract",
                                 cascade_driver_id=cid) as s:
        # Stage 1's first message (its task). A real document in place of the doc's "…".
        await s.complete(
            "Extract the facts from this doc: "
            "Tide pools form in the rocky intertidal zone. They host anemones, "
            "starfish, and crabs. They are exposed at low tide and submerged at high tide.")
    print(f"stage 1 (extract) done; cascade {cid} continues in the daemon (summarize stage)")


asyncio.run(main())
