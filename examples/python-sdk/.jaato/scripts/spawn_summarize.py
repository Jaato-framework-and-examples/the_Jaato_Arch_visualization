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
# The doc's `read_cascade_driver_id(ctx.workspace_path)` is pseudocode: the
# originating session's cascade_driver_id is neither on the event nor in a
# workspace file — it lives on the daemon's managed-session record, read the same
# way the reactor engine reads it (engine.py:310-312). Threading it is only a
# warm-slot OPTIMIZATION; None gives a correct standalone stage-2 session.
#
# `event.get("facts")` is the typed-handoff pattern, and it needs TWO things:
# (1) a completion_payload_schema with a top-level `facts` field on the PRODUCER
# profile (extract.json), so signal_completion(facts="…") attaches a validated
# typed payload; and (2) the server hoists that typed payload onto the bus event
# the reactor receives. Then summarize gets the real facts, not "None".


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
