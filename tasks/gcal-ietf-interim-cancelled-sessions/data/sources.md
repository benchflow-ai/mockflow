# Source Provenance

All task-relevant titles, UTC timestamps, and status decisions come from
official IETF Datatracker session `.ics` files and their corresponding session
pages.
The environment now layers those exact Datatracker-backed events onto the
shared workspace calendar baseline used by `gcal`, so ambient calendar
context may appear alongside the IETF session records.

## Primary sources

- CBOR cancelled session `.ics`:
  `https://datatracker.ietf.org/meeting/interim-2024-cbor-16/sessions/cbor.ics`
- CBOR confirmed trap `.ics`:
  `https://datatracker.ietf.org/meeting/interim-2024-cbor-17/sessions/cbor.ics`
- MOQ cancelled session `.ics`:
  `https://datatracker.ietf.org/meeting/interim-2025-moq-05/sessions/moq.ics`
- MOQ confirmed trap `.ics`:
  `https://datatracker.ietf.org/meeting/interim-2025-moq-06/sessions/moq.ics`
- IDR cancelled session `.ics`:
  `https://datatracker.ietf.org/meeting/interim-2024-idr-05/sessions/idr.ics`
- IDR confirmed trap `.ics`:
  `https://datatracker.ietf.org/meeting/interim-2024-idr-08/sessions/idr.ics`
- CoRE cancelled session `.ics`:
  `https://datatracker.ietf.org/meeting/interim-2026-core-04/sessions/core.ics`
- CoRE confirmed trap `.ics`:
  `https://datatracker.ietf.org/meeting/interim-2026-core-03/sessions/core.ics`

## Seeded / expected events

| Action | Summary | UTC time | Official status |
| --- | --- | --- | --- |
| delete | `cbor - Concise Binary Object Representation Maintenance and Extensions` | 2024-10-02 14:00-15:00 Z | `CANCELLED` |
| delete | `moq - Media Over QUIC (We are not ready to build an agenda at this time.)` | 2025-01-08 17:00-18:00 Z | `CANCELLED` |
| delete | `idr - Inter-Domain Routing (Interim canceled due to lack of presentations.)` | 2024-06-24 14:00-17:00 Z | `CANCELLED` |
| delete | `core - Constrained RESTful Environments` | 2026-02-25 15:00-16:30 Z | `CANCELLED` |
| keep | `cbor - Concise Binary Object Representation Maintenance and Extensions` | 2024-10-16 14:00-15:00 Z | `CONFIRMED` |
| keep | `moq - Media Over QUIC` | 2025-01-22 17:00-18:00 Z | `CONFIRMED` |
| keep | `idr - Inter-Domain Routing (https://trac.ietf.org/trac/idr/wiki/)` | 2024-06-03 14:00-15:30 Z | `CONFIRMED` |
| keep | `core - Constrained RESTful Environments` | 2026-02-11 15:00-16:30 Z | `CONFIRMED` |

## Evaluator checks

- All four `STATUS:CANCELLED` interim sessions must be removed or explicitly
  marked cancelled.
- All four `STATUS:CONFIRMED` trap sessions must remain present and unchanged.
