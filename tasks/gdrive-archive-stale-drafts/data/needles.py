"""Seed data for gdrive-archive-stale-drafts."""

DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"

ARCHIVE_FOLDER = "Archive"
ARCHIVE_DRAFTS_FOLDER = "Archive/Drafts"

TASK_FOLDERS = [
    ARCHIVE_FOLDER,
    ARCHIVE_DRAFTS_FOLDER,
]

TARGET_DRAFT_Q3 = "1DraftArchiveTargetQ3PricingPlanAlpha000001"
TARGET_DRAFT_PARTNER = "1DraftArchiveTargetPartnerOnboardBeta0002"
TARGET_DRAFT_HIRING = "1DraftArchiveTargetHiringLoopGamma000003"

DECOY_SHARED_DRAFT = "1DraftArchiveDecoySharedRoadmapDelta000004"
DECOY_COMMENTED_DRAFT = "1DraftArchiveDecoyCommentedBoardEpsilon05"
DECOY_RECENT_DRAFT = "1DraftArchiveDecoyRecentSecurityZeta00006"
DECOY_FINAL_DOC = "1DraftArchiveDecoyFinalOKRDocEta000000007"
DECOY_BOUNDARY_DRAFT = "1DraftArchiveDecoyBoundaryAPITheta00008"

TARGET_IDS = [
    TARGET_DRAFT_Q3,
    TARGET_DRAFT_PARTNER,
    TARGET_DRAFT_HIRING,
]

PROTECTED_IDS = [
    DECOY_SHARED_DRAFT,
    DECOY_COMMENTED_DRAFT,
    DECOY_RECENT_DRAFT,
    DECOY_FINAL_DOC,
    DECOY_BOUNDARY_DRAFT,
]

NEEDLES = [
    {
        "id": TARGET_DRAFT_Q3,
        "name": "Q3 Pricing Page Draft",
        "mimeType": DOC,
        "folder": "Marketing/Campaigns",
        "days_ago": 160,
        "modified_days_ago": 132,
        "content_text": (
            "Q3 Pricing Page Draft\n\n"
            "Messaging ideas for packaging refresh.\n"
            "Still rough, but nobody is actively reviewing this version.\n"
        ),
    },
    {
        "id": TARGET_DRAFT_PARTNER,
        "name": "Partner Onboarding Draft v2",
        "mimeType": DOC,
        "folder": "Shared/Templates",
        "days_ago": 175,
        "modified_days_ago": 141,
        "content_text": (
            "Partner Onboarding Draft v2\n\n"
            "Draft checklist for implementation partners.\n"
            "This version has been abandoned in favor of a newer playbook.\n"
        ),
    },
    {
        "id": TARGET_DRAFT_HIRING,
        "name": "Hiring Panel Rubric Draft",
        "mimeType": SHEET,
        "folder": "HR/Hiring/Job Descriptions",
        "days_ago": 190,
        "modified_days_ago": 156,
        "content_text": (
            "Hiring Panel Rubric Draft\n\n"
            "Role\tSignal\nBackend\tSystem design depth\nPM\tStructured thinking\n"
        ),
    },
]

NORMAL_FILES = [
    {
        "id": DECOY_SHARED_DRAFT,
        "name": "Product Launch Draft Timeline",
        "mimeType": DOC,
        "folder": "Product/Roadmaps",
        "days_ago": 150,
        "modified_days_ago": 118,
        "shared_with": [
            {
                "type": "user",
                "role": "reader",
                "email": "jordan@nexusai.com",
                "display_name": "Jordan Kim",
            }
        ],
        "content_text": (
            "Product Launch Draft Timeline\n\n"
            "Shared with Jordan for sequencing feedback.\n"
        ),
    },
    {
        "id": DECOY_COMMENTED_DRAFT,
        "name": "Board Update Draft",
        "mimeType": DOC,
        "folder": "Finance",
        "days_ago": 145,
        "modified_days_ago": 120,
        "content_text": (
            "Board Update Draft\n\n"
            "Still under review. Waiting on final finance notes.\n"
        ),
    },
    {
        "id": DECOY_RECENT_DRAFT,
        "name": "Security Review Draft",
        "mimeType": DOC,
        "folder": "Engineering/Infrastructure/Monitoring",
        "days_ago": 40,
        "modified_days_ago": 9,
        "content_text": (
            "Security Review Draft\n\n"
            "Threat model for the new auth service.\n"
            "Open items: rate-limit bypass, token rotation interval, WAF rule gaps.\n"
        ),
    },
    {
        "id": DECOY_FINAL_DOC,
        "name": "OKR Draft - Board Review",
        "mimeType": DOC,
        "folder": "Shared/All Hands",
        "days_ago": 170,
        "modified_days_ago": 5,
        "content_text": (
            "OKR Draft - Board Review\n\n"
            "Company Objective 1: Expand enterprise pipeline by 40%.\n"
            "KR1: Close 12 net-new enterprise logos.\n"
            "KR2: Reduce average sales cycle to 45 days.\n"
        ),
    },
    {
        "id": DECOY_BOUNDARY_DRAFT,
        "name": "API Migration Draft",
        "mimeType": DOC,
        "folder": "Engineering/API",
        "days_ago": 120,
        "modified_days_ago": 89,
        "content_text": (
            "API Migration Draft\n\n"
            "Endpoint deprecation plan for v1 REST surface.\n"
            "Phase 1: sunset /users/legacy. Phase 2: migrate /billing to gRPC.\n"
        ),
    },
]

COMMENTS = [
    {
        "id": "1DraftArchiveCommentBoardReview000000000001",
        "file_id": DECOY_COMMENTED_DRAFT,
        "author": "priya@nexusai.com",
        "days_ago": 6,
        "content": "Still need the updated board metrics before this can be archived.",
    }
]

FILL_CONFIG = {
    "target_count": 200,
}
