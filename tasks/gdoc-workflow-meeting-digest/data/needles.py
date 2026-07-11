"""Seed data for gdoc-workflow-meeting-digest task."""

import datetime

DOC = "application/vnd.google-apps.document"

# Parameterized digest title based on current date
_now = datetime.date.today()
DIGEST_TITLE = f"{_now.strftime('%B %Y')} Standup Digest"

# Stable document IDs — opaque join keys between gdrive and gdoc
DOC_STANDUP_WEEK1 = "1hI6jK7lM8nO9pQ0rS1tU2vW3xY4zA5bC6dE7fG8hI9j"
DOC_STANDUP_WEEK2 = "1jK8lM9nO0pQ1rS2tU3vW4xY5zA6bC7dE8fG9hI0jK1l"
DOC_STANDUP_WEEK3 = "1lM0nO1pQ2rS3tU4vW5xY6zA7bC8dE9fG0hI1jK2lM3n"
DOC_STANDUP_WEEK4 = "1nO2pQ3rS4tU5vW6xY7zA8bC9dE0fG1hI2jK3lM4nO5p"

STANDUP_DOC_IDS = [DOC_STANDUP_WEEK1, DOC_STANDUP_WEEK2, DOC_STANDUP_WEEK3, DOC_STANDUP_WEEK4]

NEEDLES = [
    {
        "id": DOC_STANDUP_WEEK1,
        "name": "Weekly Standup - March 3",
        "mimeType": DOC,
        "content_text": """Weekly Standup - March 3, 2026

Team Updates:

Alice: Completed authentication service refactor. All tests passing. Ready for code review.

Bob: Working on database migration scripts. Found an edge case with datetime conversion that needs investigation.

Carol: Deployed monitoring dashboard v1. Grafana alerts configured for all production services.

Highlights:
- Auth service refactor shipped ahead of schedule
- Monitoring dashboard live in production

Blockers:
- Database datetime conversion issue blocking migration timeline
""",
        "days_ago": 15,
    },
    {
        "id": DOC_STANDUP_WEEK2,
        "name": "Weekly Standup - March 10",
        "mimeType": DOC,
        "content_text": """Weekly Standup - March 10, 2026

Team Updates:

Alice: Started API rate limiting implementation. Evaluating token bucket vs sliding window algorithms.

Bob: Resolved datetime conversion bug. Migration scripts tested on staging environment successfully.

Carol: Added custom metrics to monitoring dashboard. Investigating memory leak in search service.

Highlights:
- Database migration scripts validated on staging
- Custom monitoring metrics operational

Blockers:
- Memory leak in search service causing intermittent OOM errors
""",
        "days_ago": 8,
    },
    {
        "id": DOC_STANDUP_WEEK3,
        "name": "Weekly Standup - March 17",
        "mimeType": DOC,
        "content_text": """Weekly Standup - March 17, 2026

Team Updates:

Alice: Rate limiter implemented with sliding window. Load testing shows it handles 10K req/s. PR open for review.

Bob: Database migration completed on staging. Production migration scheduled for March 22 maintenance window.

Carol: Memory leak identified in search service - caused by unclosed Elasticsearch connections. Fix deployed.

Highlights:
- Rate limiter ready for production
- Search service memory leak resolved
- Production DB migration scheduled

Blockers:
- Need ops team approval for March 22 maintenance window
""",
        "days_ago": 1,
    },
    {
        "id": DOC_STANDUP_WEEK4,
        "name": "Weekly Standup - March 24",
        "mimeType": DOC,
        "content_text": """Weekly Standup - March 24, 2026

Team Updates:

Alice: Rate limiter deployed to production. Monitoring shows 0.1% of requests being throttled as expected.

Bob: Production database migration completed successfully. Zero downtime achieved. Old tables archived.

Carol: Implemented automated alerting for resource utilization. On-call rotation updated.

Highlights:
- Rate limiter live in production with expected behavior
- Database migration complete with zero downtime
- Automated resource alerts active

Blockers:
- No blockers this week
""",
        "days_ago": 0,
    },
]

NORMAL_FILES = [
    {
        "name": "Sprint Planning - March",
        "mimeType": DOC,
        "content_text": "Sprint planning notes. Stories prioritized for March sprint cycle.",
        "days_ago": 16,
    },
    {
        "name": "Architecture Decision Record #15",
        "mimeType": DOC,
        "content_text": "ADR 15: Adopt event-driven architecture for notification system.",
        "days_ago": 12,
    },
    {
        "name": "Interview Feedback - Senior Engineer",
        "mimeType": DOC,
        "content_text": "Candidate showed strong system design skills. Recommend moving to final round.",
        "days_ago": 6,
    },
]

FILL_CONFIG = {
    "target_count": 300,
}
