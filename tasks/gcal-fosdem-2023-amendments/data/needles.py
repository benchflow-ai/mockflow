"""Seed config for gcal-fosdem-2023-amendments.

The exact FOSDEM corpus now lives in an env-owned gcal seed pack. This task
layers that real-world pack onto the standard workspace calendar baseline so
the UI stays rich while the amendment events remain source-faithful.
"""

GCAL_FILL_CONFIG = {
    "base_scenario": "default",
    "seed_packs": ["fosdem_2023_amendments"],
    "include_needles": True,
}
