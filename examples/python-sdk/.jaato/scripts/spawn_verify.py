# .jaato/scripts/spawn_verify.py — cascade stage 3 spawner.
#
# Fires from a reactor rule matching agent.completed where source_agent ==
# 'summarize'. Same shape as spawn_summarize.py: the prior stage's typed
# signal_completion payload is hoisted onto the event, so the summarize
# profile's `summary` field is reachable as event.get("summary"). (Requires the
# typed-payload hoist — server with jaato PR #414 — otherwise the payload sits
# one level too deep and event.get("summary") is None.)


def execute(params, event, ctx):
    summary = event.get("summary")                     # prior stage's signal_completion payload, hoisted

    managed = ctx.session_manager.get_session(ctx.session_id)
    cid = getattr(managed, "cascade_driver_id", None) if managed else None

    ctx.create_session(
        agent="verify", profile="verify",
        initial_prompt=f"Verify this summary is accurate and complete: {summary}",
        cascade_driver_id=cid)
