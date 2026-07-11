"""Seed config for gcal-ietf-interim-cancelled-sessions.

The exact IETF session corpus now lives in an env-owned gcal seed pack. This
task layers that pack onto the default workspace baseline so the task-specific
events live inside a richer calendar world, matching the gmail seeding model.
"""

GCAL_FILL_CONFIG = {
    "base_scenario": "default",
    "seed_packs": ["ietf_interim_cancelled_sessions"],
    "include_needles": True,
}
