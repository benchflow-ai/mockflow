"""Filler document generation for the long_context stress-test scenario.

The curated library in ``content.py`` ships 16 handwritten documents. To reach
the volume the long_context scenario is meant to provide (search / pagination /
large-state stress-testing), this module cycles through a set of realistic
document archetypes — standups, sprint planning, postmortems, design docs, and
so on — filling their titles and bodies with parameterized variation (dates,
teams, projects, people). Every archetype repeats its title inside the body so
full-text queries over document content have something meaningful to match.

Generation is driven entirely by the caller-provided seeded ``rng`` and ``fake``
instances, so document count and content are reproducible for a fixed seed
(document IDs use ``uuid4`` and vary per build, matching the rest of the seeder).
"""

from __future__ import annotations

import random
from collections.abc import Iterator

from faker import Faker

from mock_gdoc.seed.content import PERSONAS

# --- Parameter pools -------------------------------------------------------

_PEOPLE = [persona["name"] for persona in PERSONAS.values()]

_TEAMS = [
    "Engineering", "Product", "Design", "Data", "Platform", "Infrastructure",
    "Growth", "Security", "Mobile", "Frontend", "Backend", "ML", "DevOps", "QA",
]

_PROJECTS = [
    "API v2 Migration", "Dashboard Redesign", "Streaming Data Pipeline",
    "Auth Service Rewrite", "Billing Integration", "Search Relevance",
    "Onboarding Revamp", "Mobile App v3", "Realtime Collaboration",
    "Cost Optimization", "Multi-region Rollout", "Feature Flags Platform",
    "Observability Stack", "Model Serving", "Vector Index", "Notification Center",
]

_SYSTEMS = [
    "inference API", "auth service", "data pipeline", "billing system",
    "notification service", "search index", "API gateway", "webhook dispatcher",
    "job scheduler", "cache layer", "rate limiter", "event bus", "read replica",
    "object store",
]

_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

_YEARS = [2024, 2025, 2026]

_SEVERITIES = ["P1", "P2", "P3"]


def _date_str(rng: random.Random) -> str:
    """A realistic 'Month D, YYYY' date string."""
    return f"{rng.choice(_MONTHS)} {rng.randint(1, 28)}, {rng.choice(_YEARS)}"


def _people(rng: random.Random, k: int) -> list[str]:
    return rng.sample(_PEOPLE, k=min(k, len(_PEOPLE)))


# --- Archetypes ------------------------------------------------------------
#
# Each archetype returns a (title, body) pair. The body repeats the title on
# its first line, mirroring the handwritten library in content.py.


def _standup(rng: random.Random, fake: Faker, i: int) -> tuple[str, str]:
    team = rng.choice(_TEAMS)
    date = _date_str(rng)
    title = f"{team} Standup - {date}"
    lines = [title, "", "Updates:"]
    for person in _people(rng, 4):
        lines.append(
            f"- {person}: made progress on {rng.choice(_PROJECTS)}; "
            f"looking into an issue with the {rng.choice(_SYSTEMS)}."
        )
    lines += [
        "",
        "Blockers:",
        f"- Waiting on review for the {rng.choice(_PROJECTS)} change.",
        f"- {rng.choice(_SYSTEMS)} deploy blocked on infra approval.",
    ]
    return title, "\n".join(lines)


def _sprint_planning(rng: random.Random, fake: Faker, i: int) -> tuple[str, str]:
    sprint_n = 10 + (i % 60)
    team = rng.choice(_TEAMS)
    title = f"Sprint {sprint_n} Planning - {team}"
    owners = _people(rng, 3)
    lines = [
        title,
        _date_str(rng),
        "",
        f"Attendees: {', '.join(_people(rng, 4))}",
        "",
        "Committed work:",
    ]
    for owner in owners:
        lines.append(f"- {owner} owns {rng.choice(_PROJECTS)} ({rng.randint(3, 13)} points)")
    lines += [
        "",
        "Capacity:",
        f"- Team velocity last sprint: {rng.randint(28, 64)} points",
        f"- On-call rotation: {rng.choice(_PEOPLE)}",
    ]
    return title, "\n".join(lines)


def _one_on_one(rng: random.Random, fake: Faker, i: int) -> tuple[str, str]:
    person = rng.choice(_PEOPLE)
    date = _date_str(rng)
    title = f"1:1 Notes - {person} ({date})"
    lines = [
        title,
        "",
        "Topics discussed:",
        f"- Progress on {rng.choice(_PROJECTS)}",
        f"- Feedback on the {rng.choice(_SYSTEMS)} redesign",
        "- Career growth and goals for the quarter",
        "",
        "Action items:",
        f"- Follow up on {rng.choice(_PROJECTS)} by next week",
        "- Schedule a skip-level with the wider team",
    ]
    return title, "\n".join(lines)


def _postmortem(rng: random.Random, fake: Faker, i: int) -> tuple[str, str]:
    service = rng.choice(_SYSTEMS)
    date = _date_str(rng)
    sev = rng.choice(_SEVERITIES)
    title = f"Incident Postmortem - {service} ({date})"
    minutes = rng.randint(12, 180)
    lines = [
        title,
        "",
        f"Severity: {sev}",
        f"Duration: {minutes} minutes",
        f"Impact: elevated error rate on the {service} affecting "
        f"{rng.randint(2, 40)}% of requests",
        "",
        "Root cause:",
        f"A change to the {rng.choice(_SYSTEMS)} exhausted connections on the "
        f"{rng.choice(_SYSTEMS)}, cascading into timeouts.",
        "",
        "Action items:",
        f"- {rng.choice(_PEOPLE)}: add monitoring for the {service}",
        f"- {rng.choice(_PEOPLE)}: add a circuit breaker and backoff",
    ]
    return title, "\n".join(lines)


def _design_doc(rng: random.Random, fake: Faker, i: int) -> tuple[str, str]:
    project = rng.choice(_PROJECTS)
    title = f"Design Doc - {project}"
    lines = [
        title,
        f"Author: {rng.choice(_PEOPLE)}",
        f"Last updated: {_date_str(rng)}",
        "",
        "Overview:",
        f"This document describes the design for {project} and its impact on the "
        f"{rng.choice(_SYSTEMS)}.",
        "",
        "Goals:",
        f"- Improve reliability of the {rng.choice(_SYSTEMS)}",
        f"- Reduce latency on the {rng.choice(_SYSTEMS)} read path",
        "",
        "Non-goals:",
        f"- Rewriting the {rng.choice(_SYSTEMS)}",
        "",
        "Rollout plan:",
        "- Phase 1: shadow traffic behind a feature flag",
        f"- Phase 2: {rng.randint(5, 50)}% rollout with monitoring",
        "- Phase 3: full rollout and cleanup",
    ]
    return title, "\n".join(lines)


def _weekly_report(rng: random.Random, fake: Faker, i: int) -> tuple[str, str]:
    team = rng.choice(_TEAMS)
    week = 1 + (i % 52)
    title = f"{team} Weekly Report - Week {week}"
    lines = [
        title,
        _date_str(rng),
        "",
        "Highlights:",
        f"- Shipped an update to {rng.choice(_PROJECTS)}",
        f"- Cut {rng.choice(_SYSTEMS)} latency by {rng.randint(5, 45)}%",
        "",
        "Metrics:",
        f"- Uptime: {rng.randint(97, 100)}.{rng.randint(0, 99):02d}%",
        f"- Open incidents: {rng.randint(0, 5)}",
        "",
        "Next week:",
        f"- Continue work on {rng.choice(_PROJECTS)}",
    ]
    return title, "\n".join(lines)


def _project_update(rng: random.Random, fake: Faker, i: int) -> tuple[str, str]:
    project = rng.choice(_PROJECTS)
    status = rng.choice(["On track", "At risk", "Blocked", "Ahead of schedule"])
    title = f"{project} - Status Update"
    lines = [
        title,
        f"Status: {status}",
        f"Owner: {rng.choice(_PEOPLE)}",
        f"Updated: {_date_str(rng)}",
        "",
        "Summary:",
        f"{project} is currently {status.lower()}. The team is focused on the "
        f"{rng.choice(_SYSTEMS)} integration.",
        "",
        "Risks:",
        f"- Dependency on the {rng.choice(_SYSTEMS)} migration",
        f"- Limited review bandwidth from {rng.choice(_PEOPLE)}",
    ]
    return title, "\n".join(lines)


def _retro(rng: random.Random, fake: Faker, i: int) -> tuple[str, str]:
    sprint_n = 10 + (i % 60)
    team = rng.choice(_TEAMS)
    title = f"Sprint {sprint_n} Retro - {team}"
    lines = [
        title,
        _date_str(rng),
        "",
        "What went well:",
        f"- {rng.choice(_PROJECTS)} shipped on time",
        f"- Good collaboration between {rng.choice(_TEAMS)} and {rng.choice(_TEAMS)}",
        "",
        "What didn't:",
        f"- Flaky tests slowed down the {rng.choice(_SYSTEMS)} rollout",
        "",
        "Action items:",
        f"- {rng.choice(_PEOPLE)}: stabilize the integration test suite",
    ]
    return title, "\n".join(lines)


def _rfc(rng: random.Random, fake: Faker, i: int) -> tuple[str, str]:
    system = rng.choice(_SYSTEMS)
    title = f"RFC: Rework the {system}"
    lines = [
        title,
        f"Author: {rng.choice(_PEOPLE)}",
        f"Status: {rng.choice(['Draft', 'Under review', 'Accepted', 'Rejected'])}",
        "",
        "Motivation:",
        f"The current {system} does not scale past current load and complicates "
        f"the {rng.choice(_PROJECTS)} work.",
        "",
        "Proposal:",
        f"Introduce a new {system} layer with clearer ownership boundaries.",
        "",
        "Alternatives considered:",
        f"- Keep the {system} as-is and add caching",
        f"- Outsource the {system} to a managed service",
    ]
    return title, "\n".join(lines)


def _sync_notes(rng: random.Random, fake: Faker, i: int) -> tuple[str, str]:
    team_a = rng.choice(_TEAMS)
    team_b = rng.choice(_TEAMS)
    date = _date_str(rng)
    title = f"{team_a} / {team_b} Sync - {date}"
    lines = [
        title,
        "",
        f"Attendees: {', '.join(_people(rng, 4))}",
        "",
        "Discussion:",
        f"- Alignment on {rng.choice(_PROJECTS)} timelines",
        f"- Ownership of the {rng.choice(_SYSTEMS)} going forward",
        "",
        "Decisions:",
        f"- {rng.choice(_PEOPLE)} to drive the {rng.choice(_PROJECTS)} handoff",
    ]
    return title, "\n".join(lines)


_ARCHETYPES = [
    _standup,
    _sprint_planning,
    _one_on_one,
    _postmortem,
    _design_doc,
    _weekly_report,
    _project_update,
    _retro,
    _rfc,
    _sync_notes,
]


def generate_filler_documents(
    count: int,
    rng: random.Random,
    fake: Faker,
) -> Iterator[dict]:
    """Yield ``count`` realistic filler documents.

    Each yielded dict has ``title``, ``body``, and ``days_ago`` keys, matching
    the shape ``_create_document`` consumes. Archetypes are cycled round-robin
    so the mix stays balanced regardless of ``count``.
    """
    for i in range(count):
        archetype = _ARCHETYPES[i % len(_ARCHETYPES)]
        title, body = archetype(rng, fake, i)
        yield {
            "title": title,
            "body": body,
            "days_ago": rng.randint(1, 730),
        }
