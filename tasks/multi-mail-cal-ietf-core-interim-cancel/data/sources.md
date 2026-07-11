# Source Provenance

This task only uses official IETF sources.

## Primary sources

- Reminder email: `https://mailarchive.ietf.org/arch/msg/core/w6PNrW9y6KvgIXJ3bavssCADNjI/`
- Cancellation email: `https://mailarchive.ietf.org/arch/msg/core/b9ED0y5TFrWROI3fLfLD_lNix7Y/`
- Datatracker session page: `https://datatracker.ietf.org/meeting/interim-2026-core-04/session/core`
- CoRE WG meetings page: `https://datatracker.ietf.org/wg/core/meetings/`

## Seeded Gmail fields

| Field | Value | Source |
| --- | --- | --- |
| `subject` | `[core] CoRE WG Virtual Interim 2026-02-25` | Reminder email subject |
| `sender_name` | `Marco Tiloca` | Reminder email From |
| `sender_email` | `marco.tiloca@ri.se` | Reminder email From |
| `received_at` | `2026-02-19T12:21:55+00:00` | Reminder email Date |
| `body_plain` | Reminder body from `Dear all,` through the three meeting links | Reminder email body |
| `subject` | `[core] Constrained RESTful Environments (core) WG Interim Meeting Cancelled (was 2026-02-25)` | Cancellation email subject |
| `sender_name` | `IESG Secretary` | Cancellation email From |
| `sender_email` | `iesg-secretary@ietf.org` | Cancellation email From |
| `received_at` | `2026-02-24T20:52:50+00:00` | Cancellation email Date |
| `body_plain` | `The Constrained RESTful Environments (core) virtual interim meeting ... has been cancelled.` | Cancellation email body |

## Seeded GCal fields

| Field | Value | Source |
| --- | --- | --- |
| `summary` | `[core] CoRE WG Virtual Interim 2026-02-25` | Reminder email subject |
| `start_date` | `2026-02-25` | Reminder email body; Datatracker session page |
| `start_hour` | `15` | Reminder email body; Datatracker session page (`2026-02-25 15:00`) |
| `duration_hours` | `1.5` | Reminder email body (`15:00-16:30 UTC`); Datatracker session page |
| `description` | Exact reminder body | Reminder email body |
| `location` | empty | No explicit location was provided; meeting is remote |

## Evaluator checks

- The seeded CoRE interim event must be removed, or its status must be changed to `cancelled`.
- No new active event matching the same meeting may remain on the calendar.
