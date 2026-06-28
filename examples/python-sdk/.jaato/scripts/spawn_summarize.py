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
# correct standalone stage-2 session. The `facts` hoist is real:
# matcher.build_merged_view lifts the prior stage's signal_completion payload
# fields to the event's top level, so `event.get("facts")` is the extract
# profile's completion_payload_schema `facts` field.


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
