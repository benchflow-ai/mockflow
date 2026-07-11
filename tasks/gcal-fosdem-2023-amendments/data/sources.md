# Source Provenance

All task-relevant session titles, dates, times, rooms, and cancellation markers
come from the official FOSDEM 2023 archive.
The seeded calendar `description` fields store the exact official source URL for
each source-backed event so the task does not rely on paraphrased metadata.
The environment now layers those exact source-backed events onto the shared
workspace calendar baseline used by `gcal`, so ambient calendar context
may appear alongside the FOSDEM amendment records.

The seeded calendar stores timestamps in UTC. The official source pages use
Europe/Brussels time (`UTC+01:00`) for these sessions.

## Primary sources

- Amendments page:
  `https://archive.fosdem.org/2023/schedule/amendments/`
- `CANCELLED Eliminating ManagedStatic and llvm_shutdown`:
  `https://archive.fosdem.org/2023/schedule/event/llvmglobalstate/`
- `AMENDMENT Interactive discussion on organizing LLVM socials/meetups`:
  `https://archive.fosdem.org/2023/schedule/event/llvmmeetups/`
- `CANCELLED GRUB - Project Status Update`:
  `https://archive.fosdem.org/2023/schedule/event/grub_status_update/`
- `CANCELLED Container Storage Interface Addons`:
  `https://archive.fosdem.org/2023/schedule/event/sds_csi_addons/`
- `CANCELLED Monitoring and Centralized Logging in Ceph`:
  `https://archive.fosdem.org/2023/schedule/event/sds_monitoring_ceph/`
- `CANCELLED First class support in OSS`:
  `https://archive.fosdem.org/2023/schedule/event/sds_first_class_support/`
- Trap session `AMENDMENT Autoscaling with KEDA - Object Store Case Study`:
  `https://archive.fosdem.org/2023/schedule/event/sds_keda_object_store/`
- Trap session `Ceph RGW: S3 Select & Pushdown`:
  `https://archive.fosdem.org/2023/schedule/event/sds_ceph_rgw_s3select/`

## Seeded / expected events

| Action | Summary | Official time | Seeded UTC time | Room |
| --- | --- | --- | --- | --- |
| delete | `CANCELLED Eliminating ManagedStatic and llvm_shutdown` | 2023-02-04 15:50-16:00 +01:00 | 2023-02-04 14:50-15:00 Z | `AW1.120` |
| create | `AMENDMENT Interactive discussion on organizing LLVM socials/meetups` | 2023-02-04 15:50-16:00 +01:00 | 2023-02-04 14:50-15:00 Z | `AW1.120` |
| delete | `CANCELLED GRUB - Project Status Update` | 2023-02-05 09:10-09:35 +01:00 | 2023-02-05 08:10-08:35 Z | `K.4.201` |
| delete | `CANCELLED Container Storage Interface Addons` | 2023-02-04 16:30-17:05 +01:00 | 2023-02-04 15:30-16:05 Z | `D.sds (online)` |
| delete | `CANCELLED Monitoring and Centralized Logging in Ceph` | 2023-02-04 17:05-17:40 +01:00 | 2023-02-04 16:05-16:40 Z | `D.sds (online)` |
| delete | `CANCELLED First class support in OSS` | 2023-02-04 17:45-18:25 +01:00 | 2023-02-04 16:45-17:25 Z | `H.2214` |
| keep | `AMENDMENT Autoscaling with KEDA - Object Store Case Study` | 2023-02-04 16:30-16:55 +01:00 | 2023-02-04 15:30-15:55 Z | `H.2214` |
| keep | `Ceph RGW: S3 Select & Pushdown` | 2023-02-04 15:30-16:05 +01:00 | 2023-02-04 14:30-15:05 Z | `D.sds (online)` |

## Evaluator checks

- All five cancelled sessions must be removed or explicitly marked cancelled.
- The LLVM replacement discussion session must be created with the official
  time and room.
- The KEDA session must remain present and unchanged.
