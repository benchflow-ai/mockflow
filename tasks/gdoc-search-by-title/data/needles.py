"""Seed data for gdoc-search-by-title task."""

DOC = "application/vnd.google-apps.document"

# Stable document IDs — opaque join keys between gdrive and gdoc
DOC_SPRINT_PLANNING = "1xY6zA7bC8dE9fG0hI1jK2lM3nO4pQ5rS6tU7vW8xY9z"
DOC_SPRINT_FOLLOWUP = "2aB3cD4eF5gH6iJ7kL8mN9oP0qR1sT2uV3wX4yZ5aB6c"

NEEDLES = [
    {
        "id": DOC_SPRINT_PLANNING,
        "name": "Q1 Sprint Planning Notes",
        "mimeType": DOC,
        "content_text": """Q1 Sprint Planning Notes
March 3, 2026

Attendees: Sarah Chen, Marcus Johnson, Priya Patel, Alex Thompson

Key Decisions:
- Moving to two-week sprints (was three-week)
- Alex to own the API v2 migration
- Marcus takes lead on performance optimization

Action Items:
- [ ] Alex: Draft API v2 migration plan by March 10
- [ ] Marcus: Set up performance benchmarks by March 7
- [ ] Priya: Review auth middleware RFC by March 5
- [ ] Sarah: Update roadmap in Notion by March 6

Next meeting: March 17, 2026
""",
        "days_ago": 15,
    },
    {
        "id": DOC_SPRINT_FOLLOWUP,
        "name": "Q1 Sprint Planning — Async Follow-ups",
        "mimeType": DOC,
        "content_text": """Q1 Sprint Planning — Async Follow-ups
March 5, 2026

Some items came up in Slack after the planning session:

Action Items (addendum):
- [ ] Alex: Set up staging environment for API v2 testing by March 12
- [ ] Priya: Write integration tests for new auth flow by March 14
- [ ] Marcus: Document current p95 latency baselines by March 8

These should be tracked alongside the original planning action items.
""",
        "days_ago": 13,
    },
]

NORMAL_FILES = [
    # --- Highly confusable decoys ---

    # Decoy 1: Outdated draft with tentative items (pre-session)
    {
        "name": "Q1 Sprint Planning Draft",
        "mimeType": DOC,
        "content_text": """Q1 Sprint Planning Draft
February 25, 2026

Agenda prep for upcoming planning session.

Topics:
- Sprint cadence discussion
- API migration timeline

Proposed Items:
- [ ] Alex: Investigate API v2 feasibility
- [ ] Marcus: Benchmark candidate tools
- [ ] Sarah: Gather team velocity data
""",
        "days_ago": 20,
    },

    # Decoy 2: Archive from previous Q1 cycle (different year)
    {
        "name": "Q1 Sprint Planning Notes - Archive",
        "mimeType": DOC,
        "content_text": """Q1 Sprint Planning Notes - Archive
December 15, 2025

This is an older sprint planning doc from Q1 of the previous cycle.

Action Items (completed):
- [x] Jamie: Ship login page redesign
- [x] Sarah: Close out Q4 OKRs
- [x] Marcus: Migrate CI to GitHub Actions
""",
        "days_ago": 60,
    },

    # Decoy 3: Template
    {
        "name": "Sprint Planning Template",
        "mimeType": DOC,
        "content_text": """Sprint Planning Template

Use this template for sprint planning meetings.

Sections:
1. Attendees
2. Key Decisions
3. Action Items
4. Follow-up Date

Action Items:
- [ ] [Name]: [Task] by [Date]
- [ ] [Name]: [Task] by [Date]
""",
        "days_ago": 90,
    },

    # Decoy 4: Org-level planning (not sprint)
    {
        "name": "Q1 Planning Recap & Action Items",
        "mimeType": DOC,
        "content_text": """Q1 Planning Recap & Action Items
January 10, 2026

Quarterly planning recap — cross-functional alignment session.

Action Items:
- [ ] VP Eng: Finalize headcount plan
- [ ] Sarah: Submit budget proposal for new tooling
- [ ] Director: Schedule Q1 all-hands

Next quarterly sync: April 8, 2026
""",
        "days_ago": 50,
    },

    # Decoy 5: Wrong sprint's items
    {
        "name": "Sprint Action Items - Sprint 16",
        "mimeType": DOC,
        "content_text": """Sprint Action Items - Sprint 16
February 10, 2026

Carried over from sprint 16 retro:
- [ ] Fix flaky e2e tests in CI
- [ ] Update deployment runbook
- [ ] Add monitoring for payment service latency
""",
        "days_ago": 30,
    },

    # Decoy 6 (NEW): Very similar date, same people, different meeting (retro, not planning)
    {
        "name": "Q1 Sprint Retro — Action Items",
        "mimeType": DOC,
        "content_text": """Q1 Sprint Retro — Action Items
March 4, 2026

Retro from the sprint that ended March 3. Attendees: Sarah Chen, Marcus Johnson, Priya Patel, Alex Thompson

What went well: shipped auth middleware ahead of schedule.
What to improve: PR review turnaround, flaky tests.

Action Items:
- [ ] Alex: Add retry logic to flaky integration tests by March 11
- [ ] Sarah: Create PR review SLA document by March 7
- [ ] Marcus: Set up automated test failure alerts by March 10
- [ ] Priya: Audit and close stale PRs by March 6

Next retro: March 18, 2026
""",
        "days_ago": 14,
    },

    # Decoy 7 (NEW): Platform team's planning from same week — different team, similar format
    {
        "name": "Q1 Sprint Planning Notes — Platform Team",
        "mimeType": DOC,
        "content_text": """Q1 Sprint Planning Notes — Platform Team
March 3, 2026

Attendees: Rachel Kim, David Park, Lin Wei, Jordan Brooks

Key Decisions:
- Prioritize Kubernetes upgrade this sprint
- David to lead observability rollout

Action Items:
- [ ] David: Draft Kubernetes upgrade runbook by March 10
- [ ] Rachel: Review Terraform modules for staging by March 7
- [ ] Lin: Configure Datadog dashboards for new services by March 12
- [ ] Jordan: Write load testing scripts for API gateway by March 8

Next meeting: March 17, 2026
""",
        "days_ago": 15,
    },

    # Decoy 8 (NEW): Mid-sprint checkpoint with overlapping item descriptions
    {
        "name": "Sprint Planning Mid-Cycle Check-in",
        "mimeType": DOC,
        "content_text": """Sprint Planning Mid-Cycle Check-in
March 12, 2026

Quick sync on sprint progress. Some items are being re-scoped:

Updated Action Items:
- [ ] Alex: Revise API v2 migration plan to include rollback strategy
- [ ] Marcus: Extend performance benchmarks to cover write path
- [ ] Priya: Add edge cases to auth middleware test suite

Status review scheduled for March 17.
""",
        "days_ago": 8,
    },

    # Filler (non-confusable)
    {
        "name": "Q2 Sprint Planning Draft",
        "mimeType": DOC,
        "content_text": "Placeholder for Q2 planning. Topics TBD.",
        "days_ago": 2,
    },
    {
        "name": "Sprint Review Notes - Sprint 18",
        "mimeType": DOC,
        "content_text": "Sprint 18 review. All stories completed. Demo went well.",
        "days_ago": 8,
    },
    {
        "name": "Sprint Retrospective - Sprint 17",
        "mimeType": DOC,
        "content_text": "What went well: shipping on time. What to improve: code review turnaround.",
        "days_ago": 22,
    },
]

FILL_CONFIG = {
    "target_count": 200,
}
