"""Seed data for gdoc-organize-cleanup task."""

DOC = "application/vnd.google-apps.document"

# Stable document IDs — opaque join keys between gdrive and gdoc
DOC_UNTITLED_EMPTY = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
DOC_OLD_MEETING_DRAFT = "1kR3x7mZvN9qW2pL8jY5tH4cF6bA0sDfEgUiOlKnMwXy"
DOC_COPY_PROJECT_PLAN = "1xC5vB8nM1wQ4eR7tY0uI3oP6lK9jH2gF5dS8aZ1mN4b"
DOC_UNTITLED_PLACEHOLDER = "1pQ9rS2tU3vW4xY5zA6bC7dE8fG0hI1jK2lM3nO4pQ5r"
DOC_DRAFT_BRAINSTORM = "1rT8sU7vW6xY5zA4bC3dE2fG1hI0jK9lM8nO7pQ6rS5t"
DOC_API_MIGRATION = "1aB2cD3eF4gH5iJ6kL7mN8oP9qR0sT1uV2wX3yZ4aB5c"
DOC_Q4_FINANCIAL = "1dE6fG7hI8jK9lM0nO1pQ2rS3tU4vW5xY6zA7bC8dE9f"
DOC_UNTITLED_NOTES = "1zZ9yY8xX7wW6vV5uU4tT3sS2rR1qQ0pP9oO8nN7mM6l"

# Delete targets (5 now)
DELETE_IDS = [
    DOC_UNTITLED_EMPTY,
    DOC_OLD_MEETING_DRAFT,
    DOC_COPY_PROJECT_PLAN,
    DOC_UNTITLED_PLACEHOLDER,
    DOC_DRAFT_BRAINSTORM,
]
# Keep targets (trap docs — 3 now, including boundary decoy)
KEEP_IDS = [DOC_API_MIGRATION, DOC_Q4_FINANCIAL, DOC_UNTITLED_NOTES]

NEEDLES = [
    # === DELETE TARGETS (should be deleted) ===
    {
        "id": DOC_UNTITLED_EMPTY,
        "name": "Untitled document",
        "mimeType": DOC,
        "content_text": "",
        "days_ago": 30,
    },
    {
        "id": DOC_OLD_MEETING_DRAFT,
        "name": "Draft - old meeting notes",
        "mimeType": DOC,
        "content_text": "TBD",
        "days_ago": 45,
    },
    {
        "id": DOC_COPY_PROJECT_PLAN,
        "name": "Copy of Project Plan",
        "mimeType": DOC,
        "content_text": "(empty copy)",
        "days_ago": 20,
    },
    {
        "id": DOC_UNTITLED_PLACEHOLDER,
        "name": "Untitled document 2",
        "mimeType": DOC,
        "content_text": "placeholder text here",
        "days_ago": 60,
    },
    {
        # New delete target: has a sentence fragment but no real content
        "id": DOC_DRAFT_BRAINSTORM,
        "name": "Draft - old brainstorm",
        "mimeType": DOC,
        "content_text": "ideas go here — need to fill in later",
        "days_ago": 50,
    },

    # === TRAP DOCS (must NOT be deleted — contain real content) ===
    {
        # Trap 1: "Draft" in title, but has 2 real sentences of migration info.
        # Shortened from the original to sit right at the content boundary.
        "id": DOC_API_MIGRATION,
        "name": "Draft - API Migration Plan",
        "mimeType": DOC,
        "content_text": "Migrating from REST v1 to v2 with GraphQL support by June. Marcus is leading the backend work with three engineers on the resolver layer.",
        "days_ago": 5,
    },
    {
        # Trap 2: "Copy of" in title, but has 2 real sentences of financial data.
        # Shortened from the original to sit right at the content boundary.
        "id": DOC_Q4_FINANCIAL,
        "name": "Copy of Q4 Financial Report",
        "mimeType": DOC,
        "content_text": "Q4 total revenue was $12.4M, up 23% year-over-year. Net income hit $3.8M at a 30.6% margin with engineering at 26% of spend.",
        "days_ago": 10,
    },
    {
        # Trap 3 (boundary decoy): "Untitled" title — looks like a classic
        # delete target, but has 2 real sentences of useful meeting notes.
        "id": DOC_UNTITLED_NOTES,
        "name": "Untitled document 3",
        "mimeType": DOC,
        "content_text": "Sync with platform team confirmed the OAuth scopes need updating before the v2 launch. Sarah will file the security review by end of week.",
        "days_ago": 8,
    },
]

NORMAL_FILES = [
    {
        "name": "Team Standup Notes",
        "mimeType": DOC,
        "content_text": "Regular standup updates.",
        "days_ago": 3,
    },
    {
        "name": "Product Requirements",
        "mimeType": DOC,
        "content_text": "Feature specifications for v3.0.",
        "days_ago": 7,
    },
    {
        "name": "Architecture Overview",
        "mimeType": DOC,
        "content_text": "System architecture diagram descriptions.",
        "days_ago": 15,
    },
]

FILL_CONFIG = {
    "target_count": 200,
}
