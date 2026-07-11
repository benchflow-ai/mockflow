"""Real-world task data for IETF Datatracker interim-session cancellations."""

from __future__ import annotations


TASK_NAME = "gcal-ietf-interim-cancelled-sessions"

SOURCES = {
    "cbor_cancelled_ics": "https://datatracker.ietf.org/meeting/interim-2024-cbor-16/sessions/cbor.ics",
    "cbor_cancelled_session": "https://datatracker.ietf.org/meeting/interim-2024-cbor-16/session/cbor",
    "cbor_confirmed_ics": "https://datatracker.ietf.org/meeting/interim-2024-cbor-17/sessions/cbor.ics",
    "cbor_confirmed_session": "https://datatracker.ietf.org/meeting/interim-2024-cbor-17/session/cbor",
    "moq_cancelled_ics": "https://datatracker.ietf.org/meeting/interim-2025-moq-05/sessions/moq.ics",
    "moq_cancelled_session": "https://datatracker.ietf.org/meeting/interim-2025-moq-05/session/moq",
    "moq_confirmed_ics": "https://datatracker.ietf.org/meeting/interim-2025-moq-06/sessions/moq.ics",
    "moq_confirmed_session": "https://datatracker.ietf.org/meeting/interim-2025-moq-06/session/moq",
    "idr_cancelled_ics": "https://datatracker.ietf.org/meeting/interim-2024-idr-05/sessions/idr.ics",
    "idr_cancelled_session": "https://datatracker.ietf.org/meeting/interim-2024-idr-05/session/idr",
    "idr_confirmed_ics": "https://datatracker.ietf.org/meeting/interim-2024-idr-08/sessions/idr.ics",
    "idr_confirmed_session": "https://datatracker.ietf.org/meeting/interim-2024-idr-08/session/idr",
    "core_cancelled_ics": "https://datatracker.ietf.org/meeting/interim-2026-core-04/sessions/core.ics",
    "core_cancelled_session": "https://datatracker.ietf.org/meeting/interim-2026-core-04/session/core",
    "core_confirmed_ics": "https://datatracker.ietf.org/meeting/interim-2026-core-03/sessions/core.ics",
    "core_confirmed_session": "https://datatracker.ietf.org/meeting/interim-2026-core-03/session/core",
}


SCENARIOS = [
    {
        "id": "delete_cbor_cancelled",
        "action": "delete",
        "seed_event": {
            "summary": "cbor - Concise Binary Object Representation Maintenance and Extensions",
            "start_iso": "2024-10-02T14:00:00Z",
            "end_iso": "2024-10-02T15:00:00Z",
            "location": "",
            "description": "https://datatracker.ietf.org/meeting/interim-2024-cbor-16/session/cbor",
            "calendar": "primary",
        },
        "source_urls": [SOURCES["cbor_cancelled_ics"], SOURCES["cbor_cancelled_session"]],
    },
    {
        "id": "delete_moq_cancelled",
        "action": "delete",
        "seed_event": {
            "summary": "moq - Media Over QUIC (We are not ready to build an agenda at this time.)",
            "start_iso": "2025-01-08T17:00:00Z",
            "end_iso": "2025-01-08T18:00:00Z",
            "location": "",
            "description": "https://datatracker.ietf.org/meeting/interim-2025-moq-05/session/moq",
            "calendar": "primary",
        },
        "source_urls": [SOURCES["moq_cancelled_ics"], SOURCES["moq_cancelled_session"]],
    },
    {
        "id": "delete_idr_cancelled",
        "action": "delete",
        "seed_event": {
            "summary": "idr - Inter-Domain Routing (Interim canceled due to lack of presentations.)",
            "start_iso": "2024-06-24T14:00:00Z",
            "end_iso": "2024-06-24T17:00:00Z",
            "location": "",
            "description": "https://datatracker.ietf.org/meeting/interim-2024-idr-05/session/idr",
            "calendar": "primary",
        },
        "source_urls": [SOURCES["idr_cancelled_ics"], SOURCES["idr_cancelled_session"]],
    },
    {
        "id": "delete_core_cancelled",
        "action": "delete",
        "seed_event": {
            "summary": "core - Constrained RESTful Environments",
            "start_iso": "2026-02-25T15:00:00Z",
            "end_iso": "2026-02-25T16:30:00Z",
            "location": "",
            "description": "https://datatracker.ietf.org/meeting/interim-2026-core-04/session/core",
            "calendar": "primary",
        },
        "source_urls": [SOURCES["core_cancelled_ics"], SOURCES["core_cancelled_session"]],
    },
    {
        "id": "trap_cbor_confirmed",
        "action": "trap",
        "seed_event": {
            "summary": "cbor - Concise Binary Object Representation Maintenance and Extensions",
            "start_iso": "2024-10-16T14:00:00Z",
            "end_iso": "2024-10-16T15:00:00Z",
            "location": "",
            "description": "https://datatracker.ietf.org/meeting/interim-2024-cbor-17/session/cbor",
            "calendar": "primary",
        },
        "source_urls": [SOURCES["cbor_confirmed_ics"], SOURCES["cbor_confirmed_session"]],
    },
    {
        "id": "trap_moq_confirmed",
        "action": "trap",
        "seed_event": {
            "summary": "moq - Media Over QUIC",
            "start_iso": "2025-01-22T17:00:00Z",
            "end_iso": "2025-01-22T18:00:00Z",
            "location": "",
            "description": "https://datatracker.ietf.org/meeting/interim-2025-moq-06/session/moq",
            "calendar": "primary",
        },
        "source_urls": [SOURCES["moq_confirmed_ics"], SOURCES["moq_confirmed_session"]],
    },
    {
        "id": "trap_idr_confirmed",
        "action": "trap",
        "seed_event": {
            "summary": "idr - Inter-Domain Routing (https://trac.ietf.org/trac/idr/wiki/)",
            "start_iso": "2024-06-03T14:00:00Z",
            "end_iso": "2024-06-03T15:30:00Z",
            "location": "",
            "description": "https://datatracker.ietf.org/meeting/interim-2024-idr-08/session/idr",
            "calendar": "primary",
        },
        "source_urls": [SOURCES["idr_confirmed_ics"], SOURCES["idr_confirmed_session"]],
    },
    {
        "id": "trap_core_confirmed",
        "action": "trap",
        "seed_event": {
            "summary": "core - Constrained RESTful Environments",
            "start_iso": "2026-02-11T15:00:00Z",
            "end_iso": "2026-02-11T16:30:00Z",
            "location": "",
            "description": "https://datatracker.ietf.org/meeting/interim-2026-core-03/session/core",
            "calendar": "primary",
        },
        "source_urls": [SOURCES["core_confirmed_ics"], SOURCES["core_confirmed_session"]],
    },
]
