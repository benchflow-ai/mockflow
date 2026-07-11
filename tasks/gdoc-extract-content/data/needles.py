"""Seed data for gdoc-extract-content task."""

DOC = "application/vnd.google-apps.document"

# Stable document IDs — opaque join keys between gdrive and gdoc
DOC_AURORA_KICKOFF = "1nO6pQ7rS8tU9vW0xY1zA2bC3dE4fG5hI6jK7lM8nO9p"
DOC_AURORA_DESIGN = "1pQ8rS9tU0vW1xY2zA3bC4dE5fG6hI7jK8lM9nO0pQ1r"
DOC_AURORA_STANDUP = "1rS0tU1vW2xY3zA4bC5dE6fG7hI8jK9lM0nO1pQ2rS3t"
DOC_AURORA_RETRO = "1tU2vW3xY4zA5bC6dE7fG8hI9jK0lM1nO2pQ3rS4tU5v"
DOC_AURORA_BUDGET = "1vW4xY5zA6bC7dE8fG9hI0jK1lM2nO3pQ4rS5tU6vW7x"

AURORA_DOC_IDS = [DOC_AURORA_KICKOFF, DOC_AURORA_DESIGN, DOC_AURORA_STANDUP, DOC_AURORA_RETRO, DOC_AURORA_BUDGET]

NEEDLES = [
    {
        "id": DOC_AURORA_KICKOFF,
        "name": "Project Aurora Kickoff Notes",
        "mimeType": DOC,
        "content_text": """Project Aurora Kickoff Notes
February 15, 2026

Attendees: Sarah Chen, Marcus Johnson, Alex Thompson, Elena Rodriguez

Overview:
Project Aurora is our next-generation recommendation engine. It will replace
the current batch-based system with a real-time ML pipeline.

Key Decisions:
- Use PyTorch for model serving (not TensorFlow)
- Target 50ms p99 latency for inference
- Start with product recommendations, expand to content later

Deadlines:
- March 15: Data pipeline POC complete
- April 1: Model training infrastructure ready
- May 15: Beta launch with 5% of traffic
""",
        "days_ago": 31,
    },
    {
        "id": DOC_AURORA_DESIGN,
        "name": "Project Aurora Design Review",
        "mimeType": DOC,
        "content_text": """Project Aurora Design Review
February 28, 2026

Presenter: David Kim

Architecture discussed:
- Feature store using Redis for real-time features
- Kafka for event streaming
- Model registry with MLflow

Key Decisions:
- Adopt feature store pattern (approved by Alex)
- Use A/B testing framework for gradual rollout
- Hire one more ML engineer for the team

Deadlines:
- March 10: Feature store schema finalized
- March 20: Kafka topic design document
- April 10: First model checkpoint
""",
        "days_ago": 18,
    },
    {
        "id": DOC_AURORA_STANDUP,
        "name": "Aurora Weekly Standup - March 5",
        "mimeType": DOC,
        "content_text": """Aurora Weekly Standup - March 5, 2026

Updates:
- Data pipeline POC is 70% complete (David)
- Feature store Redis cluster provisioned (Marcus)
- Model architecture draft shared for review (Priya)

Key Decisions:
- Move standup from Wednesday to Monday
- Add monitoring dashboard before beta launch

Deadlines:
- March 12: Complete data pipeline POC (revised from March 15)
- March 18: Monitoring dashboard MVP
""",
        "days_ago": 13,
    },
    {
        "id": DOC_AURORA_RETRO,
        "name": "Project Aurora Sprint 1 Retro",
        "mimeType": DOC,
        "content_text": """Project Aurora Sprint 1 Retro
March 10, 2026

What went well:
- Data pipeline POC delivered early
- Team collaboration was excellent
- Redis feature store performing well in testing

What to improve:
- Documentation is falling behind
- Need clearer ownership of shared components

Key Decisions:
- Assign documentation owners for each component
- Create shared Slack channel for cross-team questions
- Weekly demo sessions starting next sprint

Deadlines:
- March 25: All Sprint 1 documentation complete
- April 5: Sprint 2 demo to stakeholders
""",
        "days_ago": 8,
    },
    {
        "id": DOC_AURORA_BUDGET,
        "name": "Project Aurora Budget Review",
        "mimeType": DOC,
        "content_text": """Project Aurora Budget Review
March 12, 2026

Current spend: $18,000/month
Projected at scale: $45,000/month

Key Decisions:
- Approved $45K/month budget ceiling
- Use spot instances for training workloads (40% cost reduction)
- Defer multi-region deployment to Q3

Deadlines:
- March 30: Cost optimization report
- April 15: Finalize Q2 budget allocation
""",
        "days_ago": 6,
    },
]

NORMAL_FILES = [
    {
        "name": "Project Orion Status Update",
        "mimeType": DOC,
        "content_text": "Project Orion is on track. Migration to new auth system 80% complete.",
        "days_ago": 10,
    },
    {
        "name": "Project Planning Template",
        "mimeType": DOC,
        "content_text": "Template for project kick-off documents. Fill in sections below.",
        "days_ago": 45,
    },
    {
        "name": "Q1 Project Portfolio Review",
        "mimeType": DOC,
        "content_text": "Reviewed all active projects. Orion and Nexus on track. Consider staffing for new initiative.",
        "days_ago": 20,
    },
]

FILL_CONFIG = {
    "target_count": 500,
}
