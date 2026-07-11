"""Per-task seed data for workflow-event-rsvp.

Seeds Luma event invitations at different time horizons plus traps:
  - 2 events next week (days_ago=-5, -6) -> reply "confirmed"
  - 2 events more than a month away (days_ago=-45, -50) -> label "Future Events"
  - 3 events in the ignore window (~2-3 weeks) -> do nothing
  - 1 cancelled event that *looks* next-week -> do nothing
  - 2 non-Luma event invitations (Eventbrite, calendar) -> do nothing
  - 1 Luma-lookalike domain invitation (luma-events.com) -> do nothing
  - 2 same-sender confusables from notify@luma.com (recap, waitlist) -> do nothing

Sender for real invitations is notify@luma.com.  The instruction says
"Luma event invitations" without specifying the sender address — the
agent must discover that real Luma invites come from notify@luma.com.

Date handling: All event dates are computed from the seed time via
parameterize() so email bodies contain explicit dates (e.g. "Saturday,
March 28, 2026 at 9:00 AM PST") rather than vague relative phrases.
This eliminates date ambiguity while preserving the classification
challenge (next week vs. >1 month vs. gap window).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def _event_date_str(base: datetime, days_ahead: int, time_str: str) -> str:
    """Format an event date as 'Weekday, Month Day, Year at TIME'."""
    dt = base + timedelta(days=days_ahead)
    return f"{dt.strftime('%A, %B %-d, %Y')} at {time_str}"


def _event_date_range(base: datetime, days_ahead: int, span: int) -> str:
    """Format a multi-day event as 'Weekday, Month Day - Weekday, Month Day, Year'."""
    start = base + timedelta(days=days_ahead)
    end = start + timedelta(days=span - 1)
    if start.month == end.month:
        return f"{start.strftime('%A, %B %-d')} - {end.strftime('%A, %B %-d, %Y')}"
    return f"{start.strftime('%A, %B %-d')} - {end.strftime('%A, %B %-d, %Y')}"


def parameterize(rng) -> list[dict]:
    """Return a list of needle dicts with dates computed from seed time.

    Called by the seeder with a seeded RNG so results are reproducible.
    Uses datetime.utcnow() as the base for computing event dates.
    """
    now = datetime.utcnow()

    needles = [
        # ---- Next week -- should get "confirmed" reply --------------------
        {
            "sender_name": "Luma",
            "sender_email": "notify@luma.com",
            "subject": "Maya Chen invited you to Autonomous Business Hackathon",
            "body_plain": (
                "You're invited!\n\n"
                "Autonomous Business Hackathon\n"
                "Hosted by Maya Chen\n\n"
                f"{_event_date_str(now, 5, '9:00 AM PST')}\n"
                "The Commons, 425 Mission St, San Francisco, CA\n\n"
                "Join 120+ builders for a full-day hackathon exploring autonomous "
                "agents for real business workflows. Prizes from OpenAI, Anthropic, "
                "and Replit.\n\n"
                "RSVP: https://lu.ma/evt-autonomous-biz-hack\n\n"
                "See you there!\n"
                "-- Luma"
            ),
            "labels": ["INBOX"],
            "is_read": False,
            "days_ago": -5,
            "role": "next_week",
            "params": {},
        },
        {
            "sender_name": "Luma",
            "sender_email": "notify@luma.com",
            "subject": "Alex Rivera invited you to SF Founders Dinner",
            "body_plain": (
                "You're invited!\n\n"
                "SF Founders Dinner\n"
                "Hosted by Alex Rivera\n\n"
                f"{_event_date_str(now, 6, '7:00 PM PST')}\n"
                "Beretta, 1199 Valencia St, San Francisco, CA\n\n"
                "Intimate dinner for 20 founders building in AI infrastructure "
                "and developer tools. Dress code: smart casual.\n\n"
                "RSVP: https://lu.ma/evt-sf-founders-dinner\n\n"
                "See you there!\n"
                "-- Luma"
            ),
            "labels": ["INBOX"],
            "is_read": False,
            "days_ago": -6,
            "role": "next_week",
            "params": {},
        },
        # ---- More than a month away -- should be labeled "Future Events" --
        {
            "sender_name": "Luma",
            "sender_email": "notify@luma.com",
            "subject": "TechCrunch invited you to Disrupt 2026",
            "body_plain": (
                "You're invited!\n\n"
                "Disrupt 2026\n"
                "Hosted by TechCrunch\n\n"
                f"{_event_date_range(now, 45, 3)}\n"
                "Moscone Center, 747 Howard St, San Francisco, CA\n\n"
                "The flagship startup conference returns with 10,000+ attendees, "
                "Startup Battlefield, and the AI Summit. Early-bird pricing ends "
                "next month.\n\n"
                "RSVP: https://lu.ma/evt-disrupt-2026\n\n"
                "See you there!\n"
                "-- Luma"
            ),
            "labels": ["INBOX"],
            "is_read": False,
            "days_ago": -45,
            "role": "future",
            "params": {},
        },
        {
            "sender_name": "Luma",
            "sender_email": "notify@luma.com",
            "subject": "YC invited you to Demo Day Summer 2026",
            "body_plain": (
                "You're invited!\n\n"
                "Demo Day Summer 2026\n"
                "Hosted by YC\n\n"
                f"{_event_date_range(now, 50, 2)}\n"
                "Computer History Museum, 1401 N Shoreline Blvd, Mountain View, CA\n\n"
                "Watch the S26 batch present live. Invite-only for YC alumni and "
                "selected investors. Please do not forward this invitation.\n\n"
                "RSVP: https://lu.ma/evt-yc-demo-day-s26\n\n"
                "See you there!\n"
                "-- Luma"
            ),
            "labels": ["INBOX"],
            "is_read": True,
            "days_ago": -50,
            "role": "future",
            "params": {},
        },
        # ---- Ignore window (~2-3 weeks away) -- do nothing ----------------
        {
            "sender_name": "Luma",
            "sender_email": "notify@luma.com",
            "subject": "DevOps SF invited you to March Meetup",
            "body_plain": (
                "You're invited!\n\n"
                "March Meetup\n"
                "Hosted by DevOps SF\n\n"
                f"{_event_date_str(now, 14, '6:30 PM PST')}\n"
                "Heavybit, 325 9th St, San Francisco, CA\n\n"
                "This month's topic: observability pipelines at scale. Lightning "
                "talks from engineers at Datadog, Honeycomb, and Chronosphere. "
                "Pizza and drinks provided.\n\n"
                "RSVP: https://lu.ma/evt-devops-sf-march\n\n"
                "See you there!\n"
                "-- Luma"
            ),
            "labels": ["INBOX"],
            "is_read": True,
            "days_ago": -14,
            "role": "ignore_gap",
            "params": {},
        },
        {
            "sender_name": "Luma",
            "sender_email": "notify@luma.com",
            "subject": "Priya Sharma invited you to Women in AI Brunch",
            "body_plain": (
                "You're invited!\n\n"
                "Women in AI Brunch\n"
                "Hosted by Priya Sharma\n\n"
                f"{_event_date_str(now, 16, '11:00 AM PST')}\n"
                "The Mill, 736 Divisadero St, San Francisco, CA\n\n"
                "Casual brunch for women and non-binary folks building in AI. "
                "No pitches, no slides — just good food and honest conversation "
                "about the industry.\n\n"
                "RSVP: https://lu.ma/evt-women-ai-brunch\n\n"
                "See you there!\n"
                "-- Luma"
            ),
            "labels": ["INBOX"],
            "is_read": False,
            "days_ago": -16,
            "role": "ignore_gap",
            "params": {},
        },
        {
            "sender_name": "Luma",
            "sender_email": "notify@luma.com",
            "subject": "Elad Gil invited you to AI Infrastructure Roundtable",
            "body_plain": (
                "You're invited!\n\n"
                "AI Infrastructure Roundtable\n"
                "Hosted by Elad Gil\n\n"
                f"{_event_date_str(now, 20, '6:00 PM PST')}\n"
                "The Battery, 717 Battery St, San Francisco, CA\n\n"
                "A small roundtable discussion on the future of AI infrastructure "
                "— inference costs, GPU supply chains, and the build-vs-buy "
                "debate. Limited to 15 attendees.\n\n"
                "RSVP: https://lu.ma/evt-ai-infra-roundtable\n\n"
                "See you there!\n"
                "-- Luma"
            ),
            "labels": ["INBOX"],
            "is_read": False,
            "days_ago": -20,
            "role": "ignore_gap",
            "params": {},
        },
        # ---- Cancelled event trap -----------------------------------------
        # Looks like a next-week event at first glance (Luma format, near-term
        # date) but the body says it's been postponed.  Agent must read
        # carefully and NOT reply "confirmed."
        {
            "sender_name": "Luma",
            "sender_email": "notify@luma.com",
            "subject": f"Update: SF Climate Tech Demo Day — {_event_date_str(now, 4, '10:00 AM PST')}",
            "body_plain": (
                "Important update\n\n"
                "SF Climate Tech Demo Day\n"
                "Hosted by Climate Collective\n\n"
                "Unfortunately, this event originally scheduled for "
                f"{_event_date_str(now, 4, '10:00 AM PST')} has been postponed "
                "due to a venue conflict. We're working on rescheduling for "
                "mid-April.\n\n"
                "We'll send a new invitation once the new date is confirmed. "
                "Sorry for the inconvenience!\n\n"
                "If you have any questions, reach out to "
                "events@climatecollective.org.\n\n"
                "-- Luma"
            ),
            "labels": ["INBOX"],
            "is_read": False,
            "days_ago": -4,
            "role": "ignore_cancelled",
            "params": {},
        },
        # ---- Non-Luma event decoys ----------------------------------------
        # These are next-week events from OTHER platforms.  The instruction
        # says "Luma event invitations" — the agent must ignore these
        # regardless of timing.
        {
            "sender_name": "Eventbrite",
            "sender_email": "noreply@eventbrite.com",
            "subject": "You're going! AI Startup Mixer — this Friday",
            "body_plain": (
                "Your ticket is confirmed!\n\n"
                "AI Startup Mixer\n"
                f"{_event_date_str(now, 5, '6:00 PM PST')}\n"
                "WeWork, 44 Montgomery St, San Francisco, CA\n\n"
                "Mix and mingle with 200+ AI founders, engineers, and "
                "investors. Sponsored by Sequoia and a16z.\n\n"
                "View your ticket: https://eventbrite.com/e/ai-startup-mixer\n\n"
                "See you there!\n"
                "— Eventbrite"
            ),
            "labels": ["INBOX"],
            "is_read": False,
            "days_ago": -5,
            "role": "ignore_platform",
            "params": {},
        },
        {
            "sender_name": "Google Calendar",
            "sender_email": "calendar-notification@google.com",
            "subject": "Invitation: Product Roadmap Review @ Fri 2:00 PM",
            "body_plain": (
                "Marcus Rivera has invited you to an event.\n\n"
                "Product Roadmap Review\n"
                f"When: {_event_date_str(now, 4, '2:00 PM - 3:00 PM PST')}\n"
                "Where: Nexus AI HQ, Conference Room B\n"
                "Calendar: marcus@nexusai.com\n\n"
                "Going? Yes - Maybe - No\n"
                "https://calendar.google.com/event?eid=abc123\n\n"
                "Agenda: Q2 roadmap priorities, resource allocation, "
                "timeline for v3.0 launch.\n\n"
                "This event has 8 guests."
            ),
            "labels": ["INBOX"],
            "is_read": False,
            "days_ago": -4,
            "role": "ignore_platform",
            "params": {},
        },
        # ---- Luma-lookalike domain trap -----------------------------------
        # Mimics the exact Luma email format (subject, body, signature) but
        # from luma-events.com instead of luma.com.  Tests domain
        # discrimination — the agent must check the sender address, not just
        # the template.
        {
            "sender_name": "Luma",
            "sender_email": "notify@luma-events.com",
            "subject": "Kai Zhang invited you to AI Startup Mixer",
            "body_plain": (
                "You're invited!\n\n"
                "AI Startup Mixer\n"
                "Hosted by Kai Zhang\n\n"
                f"{_event_date_str(now, 5, '6:00 PM PST')}\n"
                "WeWork, 44 Montgomery St, San Francisco, CA\n\n"
                "Mix and mingle with 200+ AI founders, engineers, and "
                "investors. Sponsored by Sequoia and a16z.\n\n"
                "RSVP: https://luma-events.com/evt-ai-startup-mixer\n\n"
                "See you there!\n"
                "-- Luma"
            ),
            "labels": ["INBOX"],
            "is_read": False,
            "days_ago": -5,
            "role": "ignore_lookalike",
            "params": {},
        },
        # ---- Same-sender confusables (notify@luma.com, NOT invitations) ---
        # These come from the real Luma sender but are not event invitations.
        # The agent must read the content to distinguish them from invites.
        {
            "sender_name": "Luma",
            "sender_email": "notify@luma.com",
            "subject": "Thanks for attending SF AI Happy Hour!",
            "body_plain": (
                "Thanks for joining us!\n\n"
                "SF AI Happy Hour\n"
                "Hosted by Jordan Lee\n\n"
                f"{_event_date_str(now, -3, '6:00 PM PST')}\n"
                "Zeitgeist, 199 Valencia St, San Francisco, CA\n\n"
                "We had a great turnout — 85 people joined! Check out the "
                "event photos and connect with other attendees on the event "
                "page.\n\n"
                "View recap: https://lu.ma/evt-sf-ai-happy-hour\n\n"
                "See you at the next one!\n"
                "-- Luma"
            ),
            "labels": ["INBOX"],
            "is_read": True,
            "days_ago": 1,
            "role": "ignore_confusable",
            "params": {},
        },
        {
            "sender_name": "Luma",
            "sender_email": "notify@luma.com",
            "subject": "You're on the waitlist for GPU Compute Summit",
            "body_plain": (
                "Waitlist confirmed\n\n"
                "GPU Compute Summit\n"
                "Hosted by Lambda Labs\n\n"
                f"{_event_date_str(now, 6, '10:00 AM PST')}\n"
                "The Midway, 900 Marin St, San Francisco, CA\n\n"
                "This event is currently at capacity. You've been added to "
                "the waitlist and we'll notify you if a spot opens up.\n\n"
                "Your waitlist position: #34\n\n"
                "View event: https://lu.ma/evt-gpu-compute-summit\n\n"
                "-- Luma"
            ),
            "labels": ["INBOX"],
            "is_read": False,
            "days_ago": -6,
            "role": "ignore_confusable",
            "params": {},
        },
    ]

    return needles


# ---------------------------------------------------------------------------
# Backwards-compatible module-level constants
# ---------------------------------------------------------------------------
import random as _random

NEEDLES = parameterize(_random.Random(42))

NEEDLE_THREADS = []

GMAIL_FILL_CONFIG = {
    "target_count": 3000,
    "include_ambiguous": False,
    "include_draft": False,
    "old_notification_ratio": 0.5,
    "distribution": {
        "notifications": 0.35, "newsletters": 0.20, "work": 0.20,
        "personal": 0.10, "sent": 0.05, "spam": 0.05,
    },
}
