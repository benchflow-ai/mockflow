"""Seed data for gdoc-edit-find-replace task."""

DOC = "application/vnd.google-apps.document"

# Stable document IDs — opaque join keys between gdrive and gdoc
DOC_VENDOR_AGREEMENT = "1xY2zA3bC4dE5fG6hI7jK8lM9nO0pQ1rS2tU3vW4xY5z"
DOC_ABOUT_COMPANY = "1zA4bC5dE6fG7hI8jK9lM0nO1pQ2rS3tU4vW5xY6zA7b"
DOC_PRODUCT_ROADMAP = "1bC6dE7fG8hI9jK0lM1nO2pQ3rS4tU5vW6xY7zA8bC9d"
DOC_ONBOARDING_GUIDE = "1dE8fG9hI0jK1lM2nO3pQ4rS5tU6vW7xY8zA9bC0dE1f"
DOC_PRESS_RELEASE = "1fG0hI1jK2lM3nO4pQ5rS6tU7vW8xY9zA0bC1dE2fG3h"

NEEDLE_DOC_IDS = [DOC_VENDOR_AGREEMENT, DOC_ABOUT_COMPANY, DOC_PRODUCT_ROADMAP, DOC_ONBOARDING_GUIDE, DOC_PRESS_RELEASE]

NEEDLES = [
    {
        "id": DOC_VENDOR_AGREEMENT,
        "name": "Vendor Services Agreement",
        "mimeType": DOC,
        "content_text": """Vendor Services Agreement

This agreement is between Nexus AI ("Company") and CloudPeak Solutions ("Vendor").

1. Scope of Services
CloudPeak Solutions shall provide cloud infrastructure services to Nexus AI for a period of 12 months beginning April 1, 2026.

2. Payment Terms
Nexus AI agrees to pay $15,000/month for the services described herein.

3. Confidentiality
Both Nexus AI and CloudPeak Solutions agree to maintain confidentiality of all shared proprietary information.

Signed: Legal Department, Nexus AI
""",
        "days_ago": 30,
    },
    {
        "id": DOC_ABOUT_COMPANY,
        "name": "About Our Company",
        "mimeType": DOC,
        "content_text": """About Our Company

Nexus AI is a leading artificial intelligence company founded in 2022. Our mission at Nexus AI is to make AI accessible to every business.

Team:
- CEO: Sarah Chen
- CTO: Marcus Johnson
- VP Engineering: Alex Thompson

Nexus AI is headquartered in San Francisco, California.

Contact: info@nexusai.com
""",
        "days_ago": 60,
    },
    {
        "id": DOC_PRODUCT_ROADMAP,
        "name": "Product Roadmap 2026",
        "mimeType": DOC,
        "content_text": """Product Roadmap 2026

Nexus AI Product Strategy

Q1 2026: Launch Nexus AI Assistant v2.0
Q2 2026: Enterprise API platform
Q3 2026: Nexus AI mobile app
Q4 2026: International expansion

All products will carry the Nexus AI brand and follow our design system.
""",
        "days_ago": 45,
    },
    {
        "id": DOC_ONBOARDING_GUIDE,
        "name": "New Employee Onboarding Guide",
        "mimeType": DOC,
        "content_text": """New Employee Onboarding Guide

Welcome to Nexus AI! We are excited to have you on board.

Your first week at Nexus AI:
Day 1: Orientation and meet your team
Day 2: Set up your Nexus AI email and tools
Day 3: Review Nexus AI coding standards
Day 4: Shadow a team member
Day 5: First team standup

Remember: Nexus AI core values are Innovation, Integrity, and Impact.
""",
        "days_ago": 20,
    },
    {
        "id": DOC_PRESS_RELEASE,
        "name": "Press Release - Series B",
        "mimeType": DOC,
        "content_text": """Press Release - Series B Funding

FOR IMMEDIATE RELEASE

Nexus AI Raises $50M in Series B Funding

San Francisco, CA - Nexus AI, a leading AI company, today announced the close of its $50 million Series B funding round led by Summit Ventures.

This funding will accelerate Nexus AI mission to democratize AI, said Sarah Chen, CEO of Nexus AI.

About Nexus AI:
Nexus AI builds enterprise AI solutions that help businesses automate complex workflows. Founded in 2022, Nexus AI serves over 200 enterprise customers.
""",
        "days_ago": 15,
    },
]

NORMAL_FILES = [
    {
        "name": "Meeting Notes - March 5",
        "mimeType": DOC,
        "content_text": "Weekly team sync. Discussed project timelines and resource allocation.",
        "days_ago": 14,
    },
    {
        "name": "Architecture Decision Record #12",
        "mimeType": DOC,
        "content_text": "ADR 12: Use PostgreSQL for primary data store. Decision made by engineering team.",
        "days_ago": 25,
    },
    {
        "name": "Q1 OKRs",
        "mimeType": DOC,
        "content_text": "Objective 1: Improve system reliability to 99.9 percent. Key results: reduce P1 incidents by 50 percent.",
        "days_ago": 35,
    },
]

FILL_CONFIG = {
    "target_count": 200,
}
