"""Seed data for gdoc-workflow-changelog task."""

DOC = "application/vnd.google-apps.document"

# Stable document IDs — opaque join keys between gdrive and gdoc
DOC_API_USERS = "1zA8bC9dE0fG1hI2jK3lM4nO5pQ6rS7tU8vW9xY0zA1b"
DOC_API_PAYMENTS = "1bC0dE1fG2hI3jK4lM5nO6pQ7rS8tU9vW0xY1zA2bC3d"
DOC_API_AUTH = "1dE2fG3hI4jK5lM6nO7pQ8rS9tU0vW1xY2zA3bC4dE5f"
DOC_API_SEARCH = "1fG4hI5jK6lM7nO8pQ9rS0tU1vW2xY3zA4bC5dE6fG7h"

CHANGELOG_DOC_IDS = [DOC_API_USERS, DOC_API_PAYMENTS, DOC_API_AUTH, DOC_API_SEARCH]

NEEDLES = [
    {
        "id": DOC_API_USERS,
        "name": "Users API Documentation",
        "mimeType": DOC,
        "content_text": """Users API Documentation

Base URL: /api/v2/users

Endpoints:
- GET /users - List all users
- GET /users/:id - Get user by ID
- POST /users - Create user
- PUT /users/:id - Update user
- DELETE /users/:id - Delete user

Authentication: Bearer token required for all endpoints.

Changelog:
- 2026-03-15: Added pagination support to GET /users (limit, offset params)
- 2026-02-20: Added email verification endpoint POST /users/:id/verify
- 2026-01-10: Initial release of Users API v2
""",
        "days_ago": 3,
    },
    {
        "id": DOC_API_PAYMENTS,
        "name": "Payments API Documentation",
        "mimeType": DOC,
        "content_text": """Payments API Documentation

Base URL: /api/v2/payments

Endpoints:
- POST /payments - Create payment
- GET /payments/:id - Get payment status
- POST /payments/:id/refund - Refund payment
- GET /payments/history - Payment history

Security: PCI-DSS compliant. All requests must use HTTPS.

Changelog:
- 2026-03-10: Added support for recurring payments
- 2026-03-01: Implemented webhook notifications for payment status changes
- 2026-02-15: Added refund endpoint with partial refund support
""",
        "days_ago": 8,
    },
    {
        "id": DOC_API_AUTH,
        "name": "Auth API Documentation",
        "mimeType": DOC,
        "content_text": """Auth API Documentation

Base URL: /api/v2/auth

Endpoints:
- POST /auth/login - Authenticate user
- POST /auth/logout - End session
- POST /auth/refresh - Refresh access token
- POST /auth/forgot-password - Initiate password reset

Token format: JWT with 15-minute expiry.

Changelog:
- 2026-03-12: Added support for OAuth2 social login (Google, GitHub)
- 2026-02-28: Implemented multi-factor authentication (TOTP)
- 2026-02-01: Added refresh token rotation for security
""",
        "days_ago": 6,
    },
    {
        "id": DOC_API_SEARCH,
        "name": "Search API Documentation",
        "mimeType": DOC,
        "content_text": """Search API Documentation

Base URL: /api/v2/search

Endpoints:
- GET /search - Full-text search across all resources
- GET /search/suggest - Auto-complete suggestions
- POST /search/advanced - Advanced query with filters

Powered by Elasticsearch 8.x.

Changelog:
- 2026-03-18: Added fuzzy matching and typo tolerance
- 2026-03-05: Implemented search result highlighting
- 2026-02-10: Added faceted search with filter aggregations
- 2026-01-20: Initial release of Search API
""",
        "days_ago": 1,
    },
]

NORMAL_FILES = [
    {
        "name": "System Architecture Overview",
        "mimeType": DOC,
        "content_text": "High-level system architecture. Microservices connected via Kafka. PostgreSQL for primary storage.",
        "days_ago": 30,
    },
    {
        "name": "Deployment Runbook",
        "mimeType": DOC,
        "content_text": "Step-by-step deployment guide. Blue-green deployment strategy. Rollback procedures included.",
        "days_ago": 20,
    },
    {
        "name": "Team Onboarding Guide",
        "mimeType": DOC,
        "content_text": "New team member onboarding process. Setup instructions, access requests, mentorship program.",
        "days_ago": 45,
    },
]

FILL_CONFIG = {
    "target_count": 300,
}
