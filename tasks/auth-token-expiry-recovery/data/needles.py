"""Per-task seed data for auth-token-expiry-recovery.

Gmail side (gmail seeder):
  60 explicit inbox emails for user1 (alex@nexusai.com) — 30 from internal
  @nexusai.com senders, 30 from external senders.  The shared content-library
  fill is disabled (target_count == fixed count) so the mailbox sender domains
  are fully controlled by this file.  Ground truth for the evaluator is purely
  the sender domain: exactly "@nexusai.com" => Internal, anything else =>
  External.  Several external senders use NexusAI-lookalike domains
  (nexusai-consulting.com, nexus-ai.io, ...) and several internal senders look
  automated (noreply@, build-bot@) so neither content vibe nor sender-name
  heuristics work — only the domain does.

Auth side (auth seeder, AUTH_* needles):
  One confidential OAuth client "expiry-client" with a 90-second access-token
  TTL (per-client TTL feature), pre-consented (auto-consent) for user1 with
  scopes openid + gmail.modify + gmail.labels.  Confidential task clients get
  the generator's GENERIC secret, i.e. the literal secret "client-secret".
"""

from __future__ import annotations

INTERNAL_DOMAIN = "nexusai.com"

# ---------------------------------------------------------------------------
# Internal senders — every one of these is @nexusai.com => label "Internal".
# Mixed content styles on purpose: humans, bots, HR blasts, automated noreply.
# (sender_name, sender_local, subject, body)
# ---------------------------------------------------------------------------
_INTERNAL = [
    ("Devon Park", "devon",
     "API gateway deploy window Thursday",
     "Heads up — we're rolling the new gateway config Thursday 2-4pm PT.\n"
     "Expect a brief blip on staging. Prod should be untouched.\n\n— Devon"),
    ("Priya Sharma", "priya",
     "Q2 review packets ready for your pass",
     "I've uploaded the Q2 review packets for my three directs.\n"
     "Can you skim before our 1:1 on Friday?\n\nPriya"),
    ("Marcus Rivera", "marcus",
     "Board deck — two comments",
     "Two things on the board deck: slide 7 needs the updated ARR figure,\n"
     "and let's cut the appendix to five slides max.\n\nMarcus"),
    ("Lisa Park", "lisa",
     "Travel policy reminder for the offsite",
     "Reminder before the offsite: book refundable fares only and keep\n"
     "receipts for anything over $25. Finance will chase you otherwise.\n\nLisa"),
    ("Sam Okafor", "sam.okafor",
     "On-call swap next week?",
     "Any chance you could take my Tuesday on-call shift next week?\n"
     "I'll cover your Thursday in exchange.\n\nSam"),
    ("IT Helpdesk", "it-helpdesk",
     "Scheduled maintenance: VPN gateway Saturday",
     "The VPN gateway will be down Saturday 01:00-03:00 PT for patching.\n"
     "Use the backup profile if you must connect during the window."),
    ("NexusAI HR", "hr",
     "Open enrollment closes Friday",
     "Benefits open enrollment closes this Friday at 5pm PT.\n"
     "Log in to the portal to confirm your selections."),
    ("Facilities", "facilities",
     "HVAC work on floor 3 this weekend",
     "Contractors will be servicing the HVAC on floor 3 Saturday morning.\n"
     "Please clear desks of anything fragile by Friday evening."),
    ("Build Bot", "build-bot",
     "Nightly build #1424: PASSED",
     "Nightly build #1424 completed successfully in 41m12s.\n"
     "Artifacts: build/nightly/1424. Coverage: 81.3% (+0.2%)."),
    ("NexusAI Security", "security",
     "Quarterly phishing training due",
     "Your quarterly security awareness training is due by end of month.\n"
     "It takes about 15 minutes. Completion is tracked for compliance."),
    ("Finance Team", "finance",
     "Expense reports due EOM",
     "Friendly reminder: March expense reports are due by end of month.\n"
     "Late submissions roll into next quarter's budget."),
    ("Jordan Lee", "jordan.lee",
     "Notes from the Meridian customer call",
     "Quick notes from today's Meridian call: they want SSO before renewal\n"
     "and asked about usage-based pricing. Full notes in the CRM.\n\nJordan"),
    ("Dana Whitfield", "dana",
     "Design review moved to 3pm",
     "Moving today's design review from 2pm to 3pm — conflict with the\n"
     "candidate interview. Same room, same agenda.\n\nDana"),
    ("Eng Announce", "eng-all",
     "RFC 0042: retry semantics for the events pipeline",
     "RFC 0042 is open for comments until next Wednesday.\n"
     "It proposes idempotency keys plus bounded exponential backoff."),
    ("NexusAI Booking", "noreply",
     "Your conference room booking is confirmed",
     "Your booking for Shasta (floor 2) is confirmed for tomorrow 10:00-11:00.\n"
     "This is an automated message from the room booking system."),
    ("Ravi Patel", "ravi",
     "Postmortem draft for the Friday incident",
     "First draft of the Friday outage postmortem is in the shared folder.\n"
     "Please add your timeline notes before Wednesday's review.\n\nRavi"),
    ("Mei Tanaka", "mei",
     "Hiring loop feedback due today",
     "Reminder to submit your scorecard for yesterday's backend candidate\n"
     "by 5pm so we can debrief tomorrow morning.\n\nMei"),
    ("Workplace Team", "workplace",
     "Cafeteria menu — week of the 14th",
     "This week's menu: taco bar Monday, ramen Wednesday, pizza Friday.\n"
     "Vegan and gluten-free options available daily."),
    ("Carlos Mendez", "carlos",
     "Staging database refresh tonight",
     "I'm refreshing the staging database from the sanitized prod snapshot\n"
     "tonight at 9pm PT. Open transactions will be dropped.\n\nCarlos"),
    ("NexusAI Payroll", "payroll",
     "Your March payslip is available",
     "Your payslip for March is now available in the payroll portal.\n"
     "This is an automated notification — do not reply."),
    ("Aisha Bello", "aisha",
     "Customer advisory board invite list",
     "Draft invite list for the customer advisory board is ready.\n"
     "Flag anyone I missed by Thursday.\n\nAisha"),
    ("Tom Novak", "tom",
     "Re: GPU quota for the training cluster",
     "We got the extra A100 quota approved. I'll bump the training cluster\n"
     "pool tomorrow morning before standup.\n\nTom"),
    ("Legal Team", "legal",
     "Updated MSA template — use v7 from today",
     "The MSA template has been updated to v7 (new liability cap language).\n"
     "Please use only v7 for any new customer agreements."),
    ("Nina Petrova", "nina",
     "Offsite agenda — call for topics",
     "Collecting agenda topics for the team offsite. Add yours to the doc\n"
     "by Friday; we'll vote on the top five.\n\nNina"),
    ("Release Bot", "release-bot",
     "v2.18.0 deployed to production",
     "Release v2.18.0 was deployed to production at 14:02 PT.\n"
     "Changelog: 14 PRs, 2 migrations. Rollback window closes in 24h."),
    ("Omar Haddad", "omar",
     "Quick favor: review my conference abstract",
     "I'm submitting an abstract about our embeddings pipeline to KDD.\n"
     "Could you give it a five-minute sanity read?\n\nOmar"),
    ("People Ops", "people-ops",
     "New starter on your team Monday",
     "Reminder: a new backend engineer joins your team Monday.\n"
     "Their laptop and accounts are ready; buddy assignment is in the wiki."),
    ("Grace Kim", "grace",
     "Budget line for the data-quality contractor",
     "Approved — the data-quality contractor goes on cost center 4410.\n"
     "Send the SOW to finance when it's countersigned.\n\nGrace"),
    ("Infra Alerts", "infra-alerts",
     "Disk usage warning cleared on db-replica-2",
     "The disk usage warning on db-replica-2 cleared at 03:11 UTC after\n"
     "log rotation. No action needed. This is an automated message."),
    ("Helena Fischer", "helena",
     "Press inquiry — routing to you",
     "A reporter from TechWire asked about our new inference pricing.\n"
     "Routing to you as comms lead for the launch.\n\nHelena"),
]

# ---------------------------------------------------------------------------
# External senders — anything not @nexusai.com => label "External".
# Includes NexusAI-lookalike domains that must still be labeled External.
# (sender_name, sender_email, subject, body)
# ---------------------------------------------------------------------------
_EXTERNAL = [
    ("GitHub", "notifications@github.com",
     "[nexusai/platform] Review requested on PR #2841",
     "devon-park requested your review on pull request #2841:\n"
     "'Add idempotency keys to the events consumer'."),
    ("Stripe", "billing@stripe.com",
     "Your Stripe invoice for March is available",
     "Your invoice for March is now available.\n"
     "Amount due: $1,284.00. Payment is scheduled automatically."),
    ("Mercury", "notifications@mercury.com",
     "Weekly cash summary for Nexus AI Inc.",
     "Your weekly account summary is ready.\n"
     "View the full breakdown in your Mercury dashboard."),
    ("Zoom", "no-reply@zoom.us",
     "Cloud recording is now available",
     "Your cloud recording 'Customer sync' is now available.\n"
     "This recording will be deleted automatically in 30 days."),
    ("Datadog", "alerts@datadoghq.com",
     "[Triggered] CPU high on inference-gw-04",
     "Monitor 'CPU high' triggered for inference-gw-04 at 09:42 UTC.\n"
     "Value: 93% over the last 15 minutes."),
    ("PagerDuty", "no-reply@pagerduty.com",
     "You are now on call for Platform",
     "Your on-call shift for schedule 'Platform' started at 09:00 PT.\n"
     "Shift ends Friday 09:00 PT."),
    ("Figma", "news@figma.com",
     "What's new in Figma this month",
     "Variables collections, faster prototyping, and more — see the\n"
     "highlights from this month's release."),
    ("Notion", "team@makenotion.com",
     "Your workspace weekly digest",
     "12 pages were updated in your workspace last week.\n"
     "Top page: 'Platform roadmap'."),
    ("Jira", "jira@nexusai.atlassian.net",
     "[JIRA] PLAT-981 assigned to you",
     "PLAT-981 'Flaky retries in events consumer' was assigned to you\n"
     "by Jordan Lee. Priority: High."),
    ("LinkedIn", "notifications@linkedin.com",
     "You appeared in 9 searches this week",
     "You appeared in 9 searches this week.\n"
     "See who's been looking at your profile."),
    ("Calendly", "notifications@calendly.com",
     "New event scheduled: Intro call",
     "A new event has been scheduled.\n"
     "Invitee: Sarah Lin. Event: Intro call, Thursday 11:00 PT."),
    ("The Batch", "thebatch@deeplearning.ai",
     "The Batch: weights, agents, and evals",
     "This week in AI: new open-weight releases, agent benchmarks, and a\n"
     "deep dive on evaluation pitfalls."),
    ("AWS", "no-reply-aws@amazon.com",
     "Your AWS bill is ready",
     "Your AWS billing statement for March is ready.\n"
     "Total: $42,318.55. View details in the billing console."),
    ("Sarah Lin", "sarah@acmecorp.com",
     "Pilot kickoff agenda",
     "Looking forward to kicking off the pilot next week.\n"
     "Attaching our proposed agenda — let me know what to add.\n\nSarah"),
    ("Mike Donovan", "mike@vendorworks.com",
     "Renewal quote attached",
     "As discussed, here's the renewal quote for the next 12 months.\n"
     "Happy to walk through the line items on a call.\n\nMike"),
    ("Quantum Leap Recruiting", "recruiting@quantumleap.io",
     "Senior platform engineer opportunity",
     "Your background came up in our search for a senior platform engineer.\n"
     "Open to a 15-minute chat this week?"),
    ("Eventbrite", "noreply@eventbrite.com",
     "Reminder: SF MLOps Meetup is tomorrow",
     "Don't forget — SF MLOps Meetup happens tomorrow at 6pm.\n"
     "Your ticket is attached. Doors open 5:30pm."),
    ("Docker", "no-reply@docker.com",
     "Security advisory for Docker Desktop",
     "A security update is available for Docker Desktop.\n"
     "We recommend updating to the latest version."),
    ("Substack", "no-reply@substack.com",
     "New post from Infra Weekly",
     "Infra Weekly just published: 'Postgres at scale — five hard lessons'.\n"
     "Read it online or in the app."),
    ("Twilio", "marketing@twilio.com",
     "Build smarter notifications",
     "Learn how teams use programmable messaging to cut support load.\n"
     "Join our webinar next Tuesday."),
    # --- NexusAI-lookalike domains: external despite the name ---
    ("NexusAI Consulting", "hr@nexusai-consulting.com",
     "Updated W-9 needed for your contractor file",
     "We're refreshing vendor records and need an updated W-9 on file.\n"
     "Please reply with the signed form this week."),
    ("Nexus AI Community", "team@nexus-ai.io",
     "Nexus AI community meetup — you're invited",
     "Join builders from the Nexus AI community for demos and lightning\n"
     "talks next Thursday. RSVP link inside."),
    ("NexusAI Talent", "careers@nexusai-talent.com",
     "Candidates matching your open roles",
     "We've shortlisted four candidates matching your platform-engineer\n"
     "openings. Book a slot to review profiles."),
    ("NexusAI Insider", "newsletter@nexusai.io",
     "NexusAI Insider #112",
     "Your weekly unofficial digest of NexusAI ecosystem news, jobs,\n"
     "and community projects."),
    ("NexusAI Partners", "partners@nexusai-partners.com",
     "Co-marketing opportunity for Q2",
     "We'd love to feature your team in our Q2 partner spotlight.\n"
     "Interested? Reply and we'll send the brief."),
    ("Plaid", "no-reply@plaid.com",
     "Action required: API key rotation",
     "We are deprecating legacy API keys next month.\n"
     "Rotate your keys in the dashboard to avoid interruption."),
    ("Carta", "support@carta.com",
     "Your equity statement is ready",
     "Your quarterly equity statement is now available.\n"
     "Log in to view vesting progress and documents."),
    ("Lever", "no-reply@hire.lever.co",
     "Interview confirmed: Staff Engineer candidate",
     "Your interview with the Staff Engineer candidate is confirmed for\n"
     "Wednesday 13:00 PT. Scorecard link inside."),
    ("Gong", "notifications@gong.io",
     "3 new call recordings for your review",
     "Three customer calls from your team were recorded this week.\n"
     "Highlights and trackers are ready for review."),
    ("Snowflake", "events@snowflake.com",
     "Your summit pass: early-bird pricing ends soon",
     "Early-bird pricing for the data summit ends Friday.\n"
     "Register now to lock in the discount."),
]


def _build_needles() -> list[dict]:
    needles: list[dict] = []
    for i, (name, local, subject, body) in enumerate(_INTERNAL):
        needles.append({
            "sender_name": name,
            "sender_email": f"{local}@{INTERNAL_DOMAIN}",
            "subject": subject,
            "body_plain": body,
            "labels": ["INBOX"],
            "is_read": (i % 3 == 0),
            "days_ago": 1 + (i % 20),
            "role": "internal",
            "params": {"expected_label": "Internal"},
        })
    for i, (name, email, subject, body) in enumerate(_EXTERNAL):
        needles.append({
            "sender_name": name,
            "sender_email": email,
            "subject": subject,
            "body_plain": body,
            "labels": ["INBOX"],
            "is_read": (i % 4 == 0),
            "days_ago": 1 + ((i + 7) % 20),
            "role": "external",
            "params": {"expected_label": "External"},
        })
    return needles


NEEDLES = _build_needles()
NEEDLE_THREADS: list[dict] = []

# target_count == len(NEEDLES) => zero content-library filler; ambiguous/draft
# extras disabled so the evaluator's sender-domain ground truth covers the
# whole mailbox.
GMAIL_FILL_CONFIG = {
    "target_count": len(NEEDLES),
    "include_ambiguous": False,
    "include_draft": False,
    "old_notification_ratio": 0.0,
    "distribution": {
        "notifications": 0.0,
        "newsletters": 0.0,
        "work": 0.0,
        "personal": 0.0,
        "sent": 0.0,
        "spam": 0.0,
    },
}

# ---------------------------------------------------------------------------
# auth needles (read by mock_auth.seed.generator.seed_task_scenario).
# user1 (alex@nexusai.com) and user2 already exist in the base seed.
# Confidential task clients are seeded with the generator's generic secret —
# the literal client secret is "client-secret" (given in task.md).
# ---------------------------------------------------------------------------
AUTH_USERS: list[dict] = []

AUTH_CLIENTS = [
    {
        "client_id": "expiry-client",
        "client_name": "Inbox Triage Bot",
        "client_type": "confidential",
        "redirect_uris": ["http://localhost:8765/callback"],
        "allowed_scopes": ["openid", "gmail.modify", "gmail.labels"],
        "grant_types": ["authorization_code", "refresh_token"],
        # Per-client access-token TTL (seconds): tokens die after 90s, forcing
        # the agent to recover via the refresh_token grant mid-task.
        "access_token_ttl": 90,
    },
]

AUTH_CONSENTS = [
    {
        "user_id": "user1",
        "client_id": "expiry-client",
        "scopes": ["openid", "gmail.modify", "gmail.labels"],
    },
]
