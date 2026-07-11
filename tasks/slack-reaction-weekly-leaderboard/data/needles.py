"""Per-task seed data for slack-reaction-weekly-leaderboard.

Multi-channel reaction aggregation task with self-reaction exclusion.
The agent must aggregate total reactions received per user across ALL public
channels in the last 7 days, EXCLUDING reactions placed by the message author.

7-day window reaction totals (after self-reaction exclusion):
  - sarah (U04SARAHKIM):   #general (12) + #engineering (10) = 22 total → Rank 1 (>20 → also post to #random)
  - priya (U02PRIYAPATEL): #general (8)  + #product (7)      = 15 total → Rank 2
  - james (U07JAMESBROWN): #frontend (13, after excluding 4 self-reactions) = 13 → Rank 3
  - marcus (U03MARCUS):    #engineering (6) + #frontend (6)  = 12 total → Rank 4 (near-miss decoy)
  - dan   (U05DANLOPEZ):   #backend (9)                      =  9 total → Rank 5

Trap (self-reaction distractor):
  - james: #frontend message with 17 total reactions, but james reacted to his own
    message 4 times (once per emoji). Without self-exclusion: 17 (rank 2). With
    self-exclusion: 13 (rank 3, behind priya). Agents that skip the exclusion rule
    will report the wrong rank-2 and rank-3 users.

Trap (near-threshold self-reactions):
  - marcus: #engineering message with 9 total reactions, but 3 are self-reactions.
    Net = 6. Combined with #frontend (6) = 12 total. Very close to james (13).
    Agents that skip self-exclusion would give marcus 6+9=15 (tying priya, wrong).

Distractor (time-window):
  - tom: #general message 10 days ago with 30 reactions → outside 7-day window

Distractor (boundary time-window):
  - rachel: #product message exactly 8 days ago with 18 reactions → just outside
    7-day window. Agents using >= instead of > for boundary get wrong rank 2.
"""

WINNER_USER = "sarah"           # sarah.kim (U04SARAHKIM)
WINNER_USER_ID = "U04SARAHKIM"
WINNER_COUNT = 22

RANK2_USER = "priya"            # priya.patel (U02PRIYAPATEL)
RANK2_COUNT = 15

RANK3_USER = "james"            # james.brown (U07JAMESBROWN) — after self-exclusion
RANK3_COUNT = 13

DM_THRESHOLD = 20  # if rank-1 total > 20, also post to #random

SEED_CHANNELS = [
    {
        "name": "frontend",
        "is_private": False,
        "creator": "james",
        "topic": "Frontend development",
        "purpose": "Frontend team discussions and UI work",
        "members": ["james", "marcus", "tom", "rachel", "alex", "nina", "priya", "sarah", "dan", "lisa"],
    },
    {
        "name": "engineering",
        "is_private": False,
        "creator": "alex",
        "topic": "Engineering",
        "purpose": "Engineering team discussions",
        "members": ["alex", "sarah", "dan", "marcus", "tom", "rachel", "james", "priya", "nina", "lisa"],
    },
]
SEED_MESSAGES = {
    "general": [
        # Discoverable threshold: establishes the 20+ → #random cross-post convention
        {
            "sender": "alex",
            "days_ago": 6,
            "text": "Last week's reaction leaderboard was fun — tom hit 20+ reactions and we "
                    "cross-posted to #random. Anything above 20 is hall-of-fame worthy imo, "
                    "let's keep that tradition going. Oh and reminder — self-reactions don't "
                    "count, we're measuring love from the team not self-hype :sweat_smile:",
            "reactions": [
                {"emoji": "thumbsup", "users": ["nina", "lisa"]},   # 2
            ],
        },
        # sarah gets 12 reactions here (rank-1 partial)
        {
            "sender": "sarah",
            "days_ago": 2,
            "text": "nexus-v2.5 just landed in prod. MMLU +4.1%, HumanEval +5.2%, p99 latency down "
                    "another 12%. Huge thanks to the whole infra team for the serving optimisations "
                    "that made this possible.",
            "reactions": [
                {"emoji": "tada",   "users": ["marcus", "priya", "dan", "nina", "tom", "james"]},   # 6
                {"emoji": "rocket", "users": ["rachel", "alex", "lisa"]},                           # 3
                {"emoji": "fire",   "users": ["marcus", "dan"]},                                    # 2
                {"emoji": "heart",  "users": ["lisa"]},                                             # 1
            ],
        },
        # priya gets 8 reactions here (rank-2 partial)
        {
            "sender": "priya",
            "days_ago": 3,
            "text": "Enterprise tier is live! First paying enterprise customer just signed. "
                    "Big milestone for the team — thank you all for the insane push this quarter.",
            "reactions": [
                {"emoji": "eyes",     "users": ["sarah", "marcus", "dan", "nina"]},   # 4
                {"emoji": "clap",     "users": ["rachel", "james"]},                   # 2
                {"emoji": "thumbsup", "users": ["alex", "tom"]},                       # 2
            ],
        },
        # tom: distractor — 10 days ago (outside the 7-day window, must NOT count)
        {
            "sender": "tom",
            "days_ago": 10,
            "text": "Data warehouse migration complete. All dashboards green, no data loss. "
                    "Migration took 5h within the maintenance window.",
            "reactions": [
                {"emoji": "tada",   "users": ["alex", "priya", "marcus", "sarah", "dan", "nina", "james", "lisa", "rachel"]},  # 9
                {"emoji": "rocket", "users": ["alex", "priya", "marcus", "sarah", "dan", "nina", "james", "lisa", "rachel"]},  # 9
                {"emoji": "clap",   "users": ["alex", "priya", "marcus", "sarah", "dan", "nina", "james", "lisa", "rachel"]},  # 9
                {"emoji": "white_check_mark", "users": ["alex", "priya", "marcus"]},                                           # 3
            ],
        },
    ],
    "engineering": [
        # sarah gets 10 more reactions here (rank-1 total = 22)
        {
            "sender": "sarah",
            "days_ago": 4,
            "text": "RFC: switching the training job scheduler from cron to Temporal. "
                    "Gives us retry logic, visibility, and proper backpressure. Draft PR is up for review.",
            "reactions": [
                {"emoji": "thumbsup", "users": ["alex", "dan", "tom", "rachel"]},      # 4
                {"emoji": "brain",    "users": ["marcus", "james", "priya"]},           # 3
                {"emoji": "clap",     "users": ["nina", "rachel", "dan"]},              # 3
            ],
        },
        # marcus gets 6 net reactions here (9 total - 3 self = 6; near-miss decoy)
        {
            "sender": "marcus",
            "days_ago": 2,
            "text": "Benchmarked the new CUDA kernels — 2.3x throughput on A100s vs the old path. "
                    "Numbers in the sheet, happy to walk through at standup.",
            "reactions": [
                {"emoji": "rocket",   "users": ["marcus", "sarah", "dan", "alex"]},     # 4 (1 self)
                {"emoji": "fire",     "users": ["marcus", "james", "priya"]},            # 3 (1 self)
                {"emoji": "eyes",     "users": ["marcus", "tom"]},                       # 2 (1 self)
            ],
            # Total: 9. Self-reactions by marcus: 3. Net: 6.
        },
    ],
    "product": [
        # priya gets 7 more reactions here (rank-2 total = 15)
        {
            "sender": "priya",
            "days_ago": 5,
            "text": "Roadmap update: moving enterprise tier launch to Q2 based on customer feedback. "
                    "Full write-up in the PRD — link in thread.",
            "reactions": [
                {"emoji": "100",  "users": ["sarah", "marcus", "nina"]},   # 3
                {"emoji": "ship", "users": ["james", "rachel"]},            # 2
                {"emoji": "clap", "users": ["alex", "tom"]},                # 2
            ],
        },
        # rachel: boundary time-window trap — 8 days ago, just outside the 7-day window.
        # 18 reactions would place her at rank 2 if incorrectly included.
        {
            "sender": "rachel",
            "days_ago": 8,
            "text": "Customer interview synthesis is done — 14 interviews across 3 segments. "
                    "Key insight: teams want SSO before anything else. Summary deck in the drive.",
            "reactions": [
                {"emoji": "eyes",     "users": ["sarah", "marcus", "dan", "nina", "tom", "james"]},     # 6
                {"emoji": "clap",     "users": ["priya", "alex", "lisa", "sarah", "marcus"]},            # 5
                {"emoji": "100",      "users": ["dan", "tom", "james", "nina"]},                         # 4
                {"emoji": "thumbsup", "users": ["alex", "priya", "lisa"]},                               # 3
            ],
            # Total: 18. But 8 days ago → outside 7-day window. Must NOT count.
        },
    ],
    "backend": [
        # dan gets 9 reactions here (rank-4, after james takes rank-3)
        {
            "sender": "dan",
            "days_ago": 1,
            "text": "Postgres 16 upgrade is live. Connection pool tuning cut p99 by 22%. "
                    "Keeping watch for 24h before closing the incident.",
            "reactions": [
                {"emoji": "white_check_mark", "users": ["alex", "sarah", "tom", "rachel"]},   # 4
                {"emoji": "fire",              "users": ["marcus", "james", "priya"]},          # 3
                {"emoji": "thumbsup",          "users": ["nina", "alex"]},                      # 2
            ],
        },
    ],
    "frontend": [
        # james: 17 total reactions, but james reacted to his own message 4 times.
        # After self-exclusion: 17 - 4 = 13 net → rank 3.
        # Without self-exclusion: 17 total → rank 2 (wrong, displacing priya).
        {
            "sender": "james",
            "days_ago": 3,
            "text": "Just shipped the new dark mode! Three themes now — system/light/dark. "
                    "More polish incoming this sprint. Try it out and let me know what you think!",
            "reactions": [
                {"emoji": "heart",   "users": ["james", "tom", "nina", "rachel", "alex"]},          # 5 (1 self)
                {"emoji": "fire",    "users": ["james", "marcus", "priya", "sarah"]},                # 4 (1 self)
                {"emoji": "tada",    "users": ["james", "dan", "lisa"]},                             # 3 (1 self)
                {"emoji": "sparkles","users": ["james", "rachel", "tom", "nina", "priya"]},          # 5 (1 self)
            ],
            # Total: 17. Self-reactions by james: 4 (one per emoji). Net: 13.
        },
        # marcus gets 6 more reactions here (rank-4 combined total = 12, near-miss for rank-3)
        {
            "sender": "marcus",
            "days_ago": 5,
            "text": "Component library v3 is tagged. Breaking changes are in the migration guide — "
                    "mostly prop renames. Should be a quick update for most pages.",
            "reactions": [
                {"emoji": "thumbsup", "users": ["james", "rachel", "tom"]},         # 3
                {"emoji": "tada",     "users": ["nina", "sarah", "dan"]},            # 3
            ],
            # Total: 6. No self-reactions. Net: 6. Marcus combined: 6 + 6 = 12.
        },
    ],
}

FILL_CONFIG = {
    "base_scenario": "default",
    # Exclude these channels from the default scenario so only our controlled
    # messages exist there — prevents default reactions from polluting the leaderboard.
    "exclude_channels": ["general", "engineering", "product", "backend", "frontend",
                         "hr-announcements", "off-topic", "design", "random"],
}
