"""Seed data for gdoc-edit-append-status task."""

DOC = "application/vnd.google-apps.document"

# Stable document IDs — opaque join keys between gdrive and gdoc
DOC_PROJECT_PHOENIX = "1pQ4rS5tU6vW7xY8zA9bC0dE1fG2hI3jK4lM5nO6pQ7r"
DOC_PROJECT_ATLAS = "1rS6tU7vW8xY9zA0bC1dE2fG3hI4jK5lM6nO7pQ8rS9t"
DOC_PROJECT_HORIZON = "1tU8vW9xY0zA1bC2dE3fG4hI5jK6lM7nO8pQ9rS0tU1v"
DOC_PROJECT_VELOCITY = "1vW0xY1zA2bC3dE4fG5hI6jK7lM8nO9pQ0rS1tU2vW3x"

PROJECT_DOC_IDS = [DOC_PROJECT_PHOENIX, DOC_PROJECT_ATLAS, DOC_PROJECT_HORIZON, DOC_PROJECT_VELOCITY]

# Expected phase/focus per doc — agent must extract this from the document content.
# Each value is a list of acceptable phrases (case-insensitive substring match).
EXPECTED_PHASES = {
    DOC_PROJECT_PHOENIX: ["data migration"],
    DOC_PROJECT_ATLAS: ["unified search", "search platform"],
    DOC_PROJECT_HORIZON: ["GDPR compliance", "European market", "EU expansion"],
    DOC_PROJECT_VELOCITY: ["authentication redesign", "user authentication"],
}

NEEDLES = [
    {
        "id": DOC_PROJECT_PHOENIX,
        "name": "Project Phoenix Overview",
        "mimeType": DOC,
        "content_text": """Project Phoenix Overview

Objective: Migrate legacy monolith to microservices architecture.

Timeline: Q1-Q2 2026
Team Lead: Marcus Johnson
Team Size: 8 engineers

Milestones:
- Phase 1: Service decomposition (complete)
- Phase 2: Data migration (in progress)
- Phase 3: Traffic cutover (planned for May)
""",
        "days_ago": 10,
    },
    {
        "id": DOC_PROJECT_ATLAS,
        "name": "Project Atlas Design Doc",
        "mimeType": DOC,
        "content_text": """Project Atlas Design Doc

Goal: Build a unified search platform for all company data sources.

Architecture:
- Elasticsearch cluster for full-text search
- Custom ranking algorithm using ML
- REST API with GraphQL gateway

Expected launch: June 2026
""",
        "days_ago": 15,
    },
    {
        "id": DOC_PROJECT_HORIZON,
        "name": "Project Horizon Proposal",
        "mimeType": DOC,
        "content_text": """Project Horizon Proposal

Proposed initiative to expand into the European market.

Key activities:
- GDPR compliance audit
- Localization of product for 5 languages
- Partnership with EU cloud providers

Budget request: $500,000
Expected timeline: 6 months
""",
        "days_ago": 22,
    },
    {
        "id": DOC_PROJECT_VELOCITY,
        "name": "Project Velocity Sprint Plan",
        "mimeType": DOC,
        "content_text": """Project Velocity Sprint Plan

Sprint 5 objectives:
- Complete user authentication redesign
- Implement rate limiting middleware
- Deploy canary release infrastructure

Sprint duration: March 10 - March 24, 2026
""",
        "days_ago": 8,
    },
]

# Decoy project docs — title starts with "Project" but content signals inactive.
# Agents should NOT append status updates to these.
# Mix of obvious (completed/cancelled) and subtle (on hold/paused) decoys.
DOC_PROJECT_TITAN = "1xA2bC3dE4fG5hI6jK7lM8nO9pQ0rS1tU2vW3xY4zA5b"
DOC_PROJECT_EMBER = "1yB3cD4eF5gH6iJ7kL8mN9oP0qR1sT2uV3wX4yZ5aB6c"
DOC_PROJECT_NEXUS = "1zC4dE5fG6hI7jK8lM9nO0pQ1rS2tU3vW4xY5zA6bC7d"
DOC_PROJECT_AURORA = "1aD5eF6gH7iJ8kL9mN0oP1qR2sT3uV4wX5yZ6aB7cD8e"
DOC_PROJECT_COBALT = "1bE6fG7hI8jK9lM0nO1pQ2rS3tU4vW5xY6zA7bC8dE9f"

DECOY_DOC_IDS = [DOC_PROJECT_TITAN, DOC_PROJECT_EMBER, DOC_PROJECT_NEXUS,
                 DOC_PROJECT_AURORA, DOC_PROJECT_COBALT]

DECOY_NEEDLES = [
    {
        "id": DOC_PROJECT_TITAN,
        "name": "Project Titan Postmortem",
        "mimeType": DOC,
        "content_text": """Project Titan Postmortem

Status: COMPLETED — Archived on January 15, 2026

Project Titan was our initiative to rebuild the payment processing pipeline.
The project launched successfully on December 20, 2025.

Final metrics:
- Transaction latency reduced by 40%
- Zero downtime during migration
- All KPIs exceeded targets

This document is archived. No further updates required.
""",
        "days_ago": 60,
    },
    {
        "id": DOC_PROJECT_EMBER,
        "name": "Project Ember Cancellation Notice",
        "mimeType": DOC,
        "content_text": """Project Ember Cancellation Notice

Status: CANCELLED — Archived on February 3, 2026

Project Ember (mobile app redesign) has been cancelled due to shifting
business priorities. All resources have been reallocated to Project Phoenix.

Reason: Market analysis showed insufficient ROI for the proposed redesign.
Budget returned to discretionary pool.

This project is no longer active. Document retained for record-keeping only.
""",
        "days_ago": 45,
    },
    {
        "id": DOC_PROJECT_NEXUS,
        "name": "Project Nexus Final Report",
        "mimeType": DOC,
        "content_text": """Project Nexus Final Report

Status: COMPLETED — Closed on November 30, 2025

Project Nexus successfully delivered the new data warehouse infrastructure.

Deliverables completed:
- Snowflake migration (100%)
- ETL pipeline modernization (100%)
- Dashboard migration to Looker (100%)

Project officially closed. All documentation archived.
""",
        "days_ago": 90,
    },
    {
        "id": DOC_PROJECT_AURORA,
        "name": "Project Aurora Roadmap",
        "mimeType": DOC,
        "content_text": """Project Aurora Roadmap

Objective: Build a real-time analytics dashboard for executive leadership.

Current status: ON HOLD pending budget approval for Q3.
The project was paused on February 28, 2026 after the mid-cycle review.
Engineering resources temporarily reassigned to Project Phoenix.

Milestones (if resumed):
- Phase 1: Data pipeline design
- Phase 2: Dashboard wireframes
- Phase 3: Beta launch

NOTE: Do not begin work until budget is confirmed. This project is paused.
""",
        "days_ago": 18,
    },
    {
        "id": DOC_PROJECT_COBALT,
        "name": "Project Cobalt Planning",
        "mimeType": DOC,
        "content_text": """Project Cobalt Planning

Goal: Redesign the internal developer portal.

Team: 4 engineers, 1 designer
Timeline: Q2-Q3 2026

Update (March 5, 2026): Project Cobalt has been placed on indefinite hold
following the org restructure. The team has been absorbed into Project Atlas.
No work should proceed until further notice from leadership.

Planned milestones (deferred):
- Portal UX research
- API documentation overhaul
- Self-service onboarding flow
""",
        "days_ago": 14,
    },
]

NORMAL_FILES = [
    {
        "name": "Team Retrospective Notes",
        "mimeType": DOC,
        "content_text": "Retro notes from last sprint. What went well: fast delivery. What to improve: test coverage.",
        "days_ago": 5,
    },
    {
        "name": "Interview Schedule - March",
        "mimeType": DOC,
        "content_text": "March interview schedule. 3 candidates for senior engineer, 2 for product manager.",
        "days_ago": 7,
    },
    {
        "name": "Quarterly All-Hands Agenda",
        "mimeType": DOC,
        "content_text": "All-hands meeting agenda. CEO update, product demos, Q&A session.",
        "days_ago": 12,
    },
]

STATUS_DATE = "March 19, 2026"
STATUS_LABEL = "Active"

FILL_CONFIG = {
    "target_count": 200,
}
