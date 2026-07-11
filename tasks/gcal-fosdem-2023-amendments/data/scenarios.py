"""Real-world task data for FOSDEM 2023 schedule amendments.

All titles, rooms, dates, and cancellation/amendment statuses come from the
official FOSDEM 2023 archive.
"""

from __future__ import annotations


TASK_NAME = "gcal-fosdem-2023-amendments"

SOURCES = {
    "amendments": "https://archive.fosdem.org/2023/schedule/amendments/",
    "llvm_cancelled": "https://archive.fosdem.org/2023/schedule/event/llvmglobalstate/",
    "llvm_replacement": "https://archive.fosdem.org/2023/schedule/event/llvmmeetups/",
    "grub_cancelled": "https://archive.fosdem.org/2023/schedule/event/grub_status_update/",
    "csi_cancelled": "https://archive.fosdem.org/2023/schedule/event/sds_csi_addons/",
    "ceph_cancelled": "https://archive.fosdem.org/2023/schedule/event/sds_monitoring_ceph/",
    "support_cancelled": "https://archive.fosdem.org/2023/schedule/event/sds_first_class_support/",
    "keda_trap": "https://archive.fosdem.org/2023/schedule/event/sds_keda_object_store/",
    "ceph_rgw_trap": "https://archive.fosdem.org/2023/schedule/event/sds_ceph_rgw_s3select/",
    # Trap: a "CANCELLED" event NOT on the official amendments list.
    # Agents that blindly delete everything with "CANCELLED" in the title will fail.
    "network_perf_trap": "https://archive.fosdem.org/2023/schedule/event/network_performance_in_kernel/",
}


SCENARIOS = [
    {
        "id": "delete_llvmglobalstate",
        "action": "delete",
        "seed_event": {
            "summary": "CANCELLED Eliminating ManagedStatic and llvm_shutdown",
            "start_iso": "2023-02-04T14:50:00Z",
            "end_iso": "2023-02-04T15:00:00Z",
            "location": "AW1.120",
            "description": SOURCES["llvm_cancelled"],
            "calendar": "primary",
        },
        "source_urls": [SOURCES["amendments"], SOURCES["llvm_cancelled"]],
    },
    {
        "id": "create_llvmmeetups",
        "action": "create",
        "target_event": {
            "summary": "AMENDMENT Interactive discussion on organizing LLVM socials/meetups",
            "start_iso": "2023-02-04T14:50:00Z",
            "end_iso": "2023-02-04T15:00:00Z",
            "location": "AW1.120",
            "description": SOURCES["llvm_replacement"],
            "calendar": "primary",
        },
        "source_urls": [SOURCES["amendments"], SOURCES["llvm_replacement"]],
    },
    {
        "id": "delete_grub_status_update",
        "action": "delete",
        "seed_event": {
            "summary": "CANCELLED GRUB - Project Status Update",
            "start_iso": "2023-02-05T08:10:00Z",
            "end_iso": "2023-02-05T08:35:00Z",
            "location": "K.4.201",
            "description": SOURCES["grub_cancelled"],
            "calendar": "primary",
        },
        "source_urls": [SOURCES["amendments"], SOURCES["grub_cancelled"]],
    },
    {
        "id": "delete_sds_csi_addons",
        "action": "delete",
        "seed_event": {
            "summary": "CANCELLED Container Storage Interface Addons",
            "start_iso": "2023-02-04T15:30:00Z",
            "end_iso": "2023-02-04T16:05:00Z",
            "location": "D.sds (online)",
            "description": SOURCES["csi_cancelled"],
            "calendar": "primary",
        },
        "source_urls": [SOURCES["amendments"], SOURCES["csi_cancelled"]],
    },
    {
        "id": "delete_sds_monitoring_ceph",
        "action": "delete",
        "seed_event": {
            "summary": "CANCELLED Monitoring and Centralized Logging in Ceph",
            "start_iso": "2023-02-04T16:05:00Z",
            "end_iso": "2023-02-04T16:40:00Z",
            "location": "D.sds (online)",
            "description": SOURCES["ceph_cancelled"],
            "calendar": "primary",
        },
        "source_urls": [SOURCES["amendments"], SOURCES["ceph_cancelled"]],
    },
    {
        "id": "delete_sds_first_class_support",
        "action": "delete",
        "seed_event": {
            "summary": "CANCELLED First class support in OSS",
            "start_iso": "2023-02-04T16:45:00Z",
            "end_iso": "2023-02-04T17:25:00Z",
            "location": "H.2214",
            "description": SOURCES["support_cancelled"],
            "calendar": "primary",
        },
        "source_urls": [SOURCES["amendments"], SOURCES["support_cancelled"]],
    },
    {
        "id": "trap_keda",
        "action": "trap",
        "seed_event": {
            "summary": "AMENDMENT Autoscaling with KEDA - Object Store Case Study",
            "start_iso": "2023-02-04T15:30:00Z",
            "end_iso": "2023-02-04T15:55:00Z",
            "location": "H.2214",
            "description": SOURCES["keda_trap"],
            "calendar": "primary",
        },
        "source_urls": [SOURCES["amendments"], SOURCES["keda_trap"]],
    },
    {
        "id": "trap_ceph_rgw",
        "action": "trap",
        "seed_event": {
            "summary": "Ceph RGW: S3 Select & Pushdown",
            "start_iso": "2023-02-04T14:30:00Z",
            "end_iso": "2023-02-04T15:05:00Z",
            "location": "D.sds (online)",
            "description": SOURCES["ceph_rgw_trap"],
            "calendar": "primary",
        },
        "source_urls": [SOURCES["ceph_rgw_trap"]],
    },
    {
        "id": "trap_network_perf_cancelled",
        "action": "trap",
        "seed_event": {
            "summary": "CANCELLED Network Performance in the Linux Kernel",
            "start_iso": "2023-02-04T13:00:00Z",
            "end_iso": "2023-02-04T13:50:00Z",
            "location": "H.1308 (Rolin)",
            "description": SOURCES["network_perf_trap"],
            "calendar": "primary",
        },
        "source_urls": [SOURCES["network_perf_trap"]],
    },
]
