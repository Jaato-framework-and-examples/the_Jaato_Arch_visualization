# .jaato/scripts/spawn_summarize.py — runs INSIDE the daemon on that event.
#
# Doc snippet (langchain.md §9 / pydantic-ai.md §9) shape:
#
#   def execute(params, event, ctx):
#       facts = event.get("facts")
#       ctx.create_session(
#           agent="summarize", profile="summarize",
#           initial_prompt=f"Summarise these findings: {facts}",
#           cascade_driver_id=read_cascade_driver_id(ctx.workspace_path))
#
# FINDING: the doc's `read_cascade_driver_id(ctx.workspace_path)` is pseudocode
# AND its comment ("cid from the workspace cascade_state, not the event") is
# wrong on both counts. The originating session's cascade_driver_id is neither on
# the event nor in a workspace file — it lives on the daemon's managed-session
# record, read exactly the way the reactor engine itself reads it
# (engine.py:310-312). Threading it is only a warm-slot OPTIMIZATION; None gives a
# correct standalone stage-2 session.
#
# `event.get("facts")` is the correct typed-handoff pattern, and it needs TWO
# things: (1) a completion_payload_schema with a top-level `facts` field on the
# PRODUCER profile (extract.json — done), so signal_completion(facts="…") attaches
# a validated typed payload; and (2) server with jaato PR #414, which hoists that
# typed payload onto the bus event the reactor receives. Before #414 the payload
# sat one level too deep ("payload".facts) so event.get("facts") was None — a real
# core bug this example surfaced. Validated end-to-end on #414: summarize gets the
# real facts, not "None".


def execute(params, event, ctx):
    facts = event.get("facts")                         # prior stage's signal_completion payload, hoisted

    # Real cascade_driver_id read (replaces the doc's undefined helper): the cid
    # is an attribute of the originating managed session, same as engine.py does.
    managed = ctx.session_manager.get_session(ctx.session_id)
    cid = getattr(managed, "cascade_driver_id", None) if managed else None

    ctx.create_session(
        agent="summarize", profile="summarize",        # the next stage's persona (soul) + profile (runtime)
        initial_prompt=f"Summarise these findings: {facts}",   # its FIRST MESSAGE (task) — injected here; no human types it
        cascade_driver_id=cid)                          # warm-slot reuse; None = standalone (still correct)
