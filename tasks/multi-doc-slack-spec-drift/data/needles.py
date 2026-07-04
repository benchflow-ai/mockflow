"""Multi-env seed data for multi-doc-slack-spec-drift.

gdrive reads:  NEEDLES, NORMAL_FILES, FILL_CONFIG
gdoc mirrors:  from gdrive (--from-gdrive)
slack reads:   SEED_USERS, SEED_CHANNELS, SEED_MESSAGES, FILL_CONFIG
"""

from __future__ import annotations

try:
    from mock_gdrive.seed.content import DOC
except ImportError:
    DOC = "application/vnd.google-apps.document"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DOC_SPEC = "1ApiRateLimitingPolicySpec000000000000000000"

DRIFT_DECISIONS = [
    {
        "id": "enterprise_limit",
        # Require BOTH "2500" and "enterprise" to avoid matching Carol's noise about free tier
        "keywords_all": ["2500", "enterprise"],
        "doc_section": "Rate Limits by Tier",
    },
    {
        "id": "retry_after_header",
        "keywords_any": ["retry-after"],
        "doc_section": "Response Headers",
    },
    {
        "id": "burst_window",
        "keywords_any": ["10 second", "10-second", "10s"],
        "doc_section": "Burst Policy",
    },
]

NOISE_COUNT = 22  # High noise volume to dilute drift signal

# ---------------------------------------------------------------------------
# GDrive needles (docs)
# ---------------------------------------------------------------------------

NEEDLES = [
    {
        "id": DOC_SPEC,
        "name": "API Rate Limiting Policy",
        "mimeType": DOC,
        "content_text": (
            "API Rate Limiting Policy\n"
            "========================\n\n"
            "Overview\n"
            "--------\n"
            "This document defines the rate limiting policy for all public API\n"
            "endpoints. Rate limits are enforced per API key and vary by tier.\n\n"
            "Rate Limits by Tier\n"
            "-------------------\n"
            "- Free: 100 requests/minute\n"
            "- Pro: 500 requests/minute\n"
            "- Enterprise: 1000 requests/minute\n\n"
            "Response Headers\n"
            "----------------\n"
            "All rate-limited responses include the following headers:\n"
            "- X-RateLimit-Limit: maximum requests per window\n"
            "- X-RateLimit-Remaining: requests remaining in current window\n"
            "- X-RateLimit-Reset: UTC epoch timestamp when the window resets\n\n"
            "Burst Policy\n"
            "------------\n"
            "Clients may temporarily exceed their per-minute limit within a\n"
            "60-second burst window. Burst capacity is 2x the tier limit.\n"
            "After the burst window expires, standard limits apply.\n\n"
            "Error Handling\n"
            "--------------\n"
            "When a client exceeds the rate limit, the API returns HTTP 429\n"
            "Too Many Requests with a JSON body:\n"
            '  {"error": "rate_limit_exceeded", "retry_after_seconds": <int>}\n\n'
            "Revision History\n"
            "----------------\n"
            "- 2026-01-15: Initial draft\n"
            "- 2026-02-10: Added burst policy section\n"
            "- 2026-03-01: Updated error response format\n"
        ),
        "days_ago": 0,
    },
]

NORMAL_FILES = [
    {
        "name": "API Authentication Guide",
        "mimeType": DOC,
        "content_text": (
            "API Authentication Guide\n\n"
            "All API requests require Bearer token authentication.\n"
            "Tokens can be generated from the developer dashboard."
        ),
        "days_ago": 14,
    },
    {
        "name": "Deployment Runbook v3",
        "mimeType": DOC,
        "content_text": (
            "Deployment Runbook v3\n\n"
            "Blue-green deployment with canary rollout.\n"
            "Rollback procedure: revert via ArgoCD within 5 minutes."
        ),
        "days_ago": 21,
    },
    {
        "name": "Q2 2026 Engineering OKRs",
        "mimeType": DOC,
        "content_text": (
            "Q2 2026 Engineering OKRs\n\n"
            "O1: Improve API reliability to 99.95% uptime\n"
            "O2: Reduce median latency to <50ms\n"
            "O3: Ship rate limiting v2 by end of quarter"
        ),
        "days_ago": 7,
    },
]

# ---------------------------------------------------------------------------
# Slack seed data
# ---------------------------------------------------------------------------

SEED_USERS: list[dict] = [
    {
        "key": "jordan",
        "name": "jordan",
        "real_name": "Jordan Lee",
        "email": "jordan.lee@nexusai.com",
        "title": "Senior Backend Engineer",
    },
    {
        "key": "alice",
        "name": "alice",
        "real_name": "Alice Chen",
        "email": "alice.chen@nexusai.com",
        "title": "Platform Engineer",
    },
    {
        "key": "derek",
        "name": "derek",
        "real_name": "Derek Owens",
        "email": "derek.owens@nexusai.com",
        "title": "Backend Engineer",
    },
    {
        "key": "bob",
        "name": "bob",
        "real_name": "Bob Martinez",
        "email": "bob.martinez@nexusai.com",
        "title": "Software Engineer",
    },
    {
        "key": "carol",
        "name": "carol",
        "real_name": "Carol Davis",
        "email": "carol.davis@nexusai.com",
        "title": "Software Engineer",
    },
    {
        "key": "elena",
        "name": "elena",
        "real_name": "Elena Petrov",
        "email": "elena.petrov@nexusai.com",
        "title": "SRE",
    },
]

SEED_CHANNELS: list[dict] = [
    {
        "name": "backend",
        "is_private": False,
        "topic": "Backend engineering discussion",
        "purpose": "All things backend: APIs, services, infra",
        "members": ["jordan", "alice", "derek", "bob", "carol", "elena"],
    },
]

SEED_MESSAGES: dict = {
    "backend": [
        # ════════════════════════════════════════════════════════════════
        # DRIFT DECISION 1: Enterprise tier 1000 → 2500 req/min
        # Buried in a thread about load testing — the decision is in a
        # reply, not the top-level message.
        # ════════════════════════════════════════════════════════════════
        {
            "sender": "jordan",
            "text": (
                "Load test results are in for the new inference cluster. "
                "Throughput is way better than expected — we've got headroom "
                "for at least 3x current peak on Enterprise."
            ),
            "days_ago": 10,
            "thread": [
                {
                    "sender": "carol",
                    "text": "Nice. So we could safely raise the Enterprise limit?",
                },
                {
                    "sender": "jordan",
                    "text": (
                        "Yeah, I went ahead and bumped Enterprise to 2500 req/min "
                        "in the gateway config. Our biggest customer was already "
                        "hitting 1800 on peak days so this was overdue."
                    ),
                },
                {
                    "sender": "alice",
                    "text": "Makes sense. I'll update the SDK docs to reflect 2500.",
                },
            ],
        },
        # ════════════════════════════════════════════════════════════════
        # DRIFT DECISION 2: X-RateLimit-Reset → Retry-After header
        # Subtle phrasing — no "Decision:" prefix, just a casual FYI
        # buried among other messages.
        # ════════════════════════════════════════════════════════════════
        {
            "sender": "alice",
            "text": (
                "btw I swapped out X-RateLimit-Reset for the standard Retry-After "
                "header in the middleware yesterday. Every HTTP client already supports "
                "it natively so this should be a net improvement. The other two "
                "rate limit headers stay as-is."
            ),
            "days_ago": 6,
        },
        # ════════════════════════════════════════════════════════════════
        # DRIFT DECISION 3: Burst window 60s → 10s
        # Top-level message but casual phrasing — no "Decision:" prefix.
        # Medium difficulty: visible but requires reading carefully.
        # ════════════════════════════════════════════════════════════════
        {
            "sender": "derek",
            "text": (
                "Pushed the burst window change to prod — went from 60 seconds "
                "down to 10 seconds. The abuse patterns Elena flagged last week "
                "drop off immediately with the shorter window. Staging metrics "
                "looked clean so I shipped it."
            ),
            "days_ago": 3,
        },
        # ════════════════════════════════════════════════════════════════
        # NOISE — high volume, mix of styles, some assertive
        # ════════════════════════════════════════════════════════════════
        # Reverted decision trap (proposed then withdrawn)
        {
            "sender": "bob",
            "text": (
                "I've been thinking — we should add per-endpoint rate limits on top "
                "of the global ones. Different endpoints have very different cost "
                "profiles. I'll draft a config format."
            ),
            "days_ago": 13,
        },
        {
            "sender": "bob",
            "text": (
                "Scratch the per-endpoint limits idea. After talking to the infra "
                "team, the config complexity isn't worth it for the marginal benefit. "
                "We're sticking with global limits."
            ),
            "days_ago": 12,
        },
        # Wrong-doc decision (auth, not rate limiting)
        {
            "sender": "derek",
            "text": (
                "Going forward we're requiring API keys on all endpoints, no more "
                "anonymous access. I'll update the auth guide this week."
            ),
            "days_ago": 8,
        },
        # Confirmatory decoys — assertive language, matches the spec (no drift)
        {
            "sender": "alice",
            "text": (
                "Verified the 429 response body. The JSON error shape with "
                "retry_after_seconds is correct per the spec. No changes needed."
            ),
            "days_ago": 5,
        },
        {
            "sender": "elena",
            "text": (
                "I've validated the sliding window algorithm — when a client hits "
                "exactly the limit, the 429 fires immediately. Enforcement logic "
                "matches the spec."
            ),
            "days_ago": 5,
        },
        # Speculative / tangential noise
        {
            "sender": "carol",
            "text": "I wonder if 2500 is too high for the free tier though. Seems generous.",
            "days_ago": 7,
        },
        {
            "sender": "jordan",
            "text": "Anyone tried the new Redis cluster? Seems faster for the token bucket counters.",
            "days_ago": 3,
        },
        {
            "sender": "bob",
            "text": "Should we maybe consider adding webhooks for rate limit events?",
            "days_ago": 2,
        },
        {
            "sender": "elena",
            "text": "Rate limiter deploy went smoothly. No alerts, latency unchanged.",
            "days_ago": 2,
        },
        {
            "sender": "derek",
            "text": (
                "Quick heads up: the Grafana dashboard for rate limiting is updated "
                "with the new burst metrics. Check it out if you want to see the "
                "before/after on abuse patterns."
            ),
            "days_ago": 1,
        },
        # More general backend chatter (non-rate-limiting)
        {
            "sender": "jordan",
            "text": "Migration to the new DB cluster is scheduled for next Tuesday. Will post a runbook.",
            "days_ago": 9,
        },
        {
            "sender": "carol",
            "text": (
                "The search indexer is falling behind again. We're seeing 20min "
                "lag on production. Anyone have bandwidth to look at it?"
            ),
            "days_ago": 8,
        },
        {
            "sender": "alice",
            "text": "PR #1847 is ready for review — refactors the auth middleware. Would appreciate eyes on it.",
            "days_ago": 7,
        },
        {
            "sender": "bob",
            "text": (
                "Just finished the caching layer for the recommendations endpoint. "
                "p99 went from 340ms to 45ms. Pretty happy with that."
            ),
            "days_ago": 6,
        },
        {
            "sender": "elena",
            "text": "On-call handoff: nothing major this week. Two minor alerts, both auto-resolved.",
            "days_ago": 5,
        },
        {
            "sender": "derek",
            "text": (
                "Reminder: deprecation deadline for v1 API is April 15. If your "
                "service still calls v1 endpoints, please migrate before then."
            ),
            "days_ago": 4,
        },
        {
            "sender": "jordan",
            "text": "Anyone going to the internal tech talk on Thursday? The topic is distributed tracing.",
            "days_ago": 3,
        },
        {
            "sender": "carol",
            "text": "Standup notes: I'm blocked on the payment service integration, waiting on the API key from Stripe.",
            "days_ago": 2,
        },
        {
            "sender": "alice",
            "text": (
                "Heads up — I'm rotating the staging TLS certs this afternoon. "
                "If your integration tests hit staging, they might blip."
            ),
            "days_ago": 1,
        },
        {
            "sender": "bob",
            "text": (
                "The load balancer health checks are too aggressive — we're seeing "
                "false positives during GC pauses. Going to widen the timeout to 5s."
            ),
            "days_ago": 1,
        },
    ],
}

# ---------------------------------------------------------------------------
# FILL_CONFIG — serves both gdrive and slack seeders.
# Each seeder reads only the fields it cares about.
# ---------------------------------------------------------------------------

FILL_CONFIG = {
    "target_count": 20,            # gdrive filler
    "base_scenario": "default",    # slack base scenario
    "exclude_channels": ["backend"],  # don't let default scenario pollute #backend
}
