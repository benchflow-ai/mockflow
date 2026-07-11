"""Per-task seed data for slack-extract-reaction-leaderboard.

Seeds the default scenario plus needle messages across channels.
The agent must find the top 3 most-reacted messages in #general only,
counting total individual reactions from *people* (not unique users,
not bot/app reactions), and post the leaderboard to #random with a
:trophy: on the #1 message.

A bot user ("nexusbot") reacts to the top-3 messages.  Its reactions
inflate the naive total but must be excluded.  The correct human-only
counts are:
  - Winner:  24  (james's GitHub stars post)    [naive w/ bot: 26]
  - Rank 2:  19  (sarah's maintenance notice)   [naive w/ bot: 21]
  - Rank 3:  16  (alex's welcome post)          [naive w/ bot: 18]

Near-threshold decoys in #general:
  - 14 reactions (marcus's project reminder)
  - 13 reactions (nina's design doc)

Cross-channel distractor in #random:
  - 30 reactions (priya's meme post) — must NOT appear in leaderboard
"""

WINNER_TEXT = (
    "\U0001f389 We just crossed 1,000 GitHub stars! "
    "Huge thanks to everyone who starred, contributed, and spread the word "
    "\u2014 this is a massive milestone for the NexusAI team!"
)
WINNER_REACTION_COUNT = 24

RANK2_TEXT = (
    "Heads up: planned maintenance Saturday Mar 28 02:00\u201304:00 UTC. "
    "API will be read-only during the window. Dashboards will stay live."
)
RANK2_REACTION_COUNT = 19

RANK3_TEXT = (
    "Welcome to the team, Lisa! \U0001f44f "
    "She\u2019s joining us as a Product Designer and will be working on the onboarding flow."
)
RANK3_REACTION_COUNT = 16

# Bot user whose reactions must be excluded from counts
SEED_USERS = [
    {
        "key": "nexusbot",
        "name": "nexusbot",
        "real_name": "Nexus Bot",
        "email": "",
        "title": "CI/CD Automation",
        "is_bot": True,
    },
]

SEED_CHANNELS = []
SEED_MESSAGES = {
    "general": [
        # --- Winner: 24 total reactions ---
        # Note: priya and marcus appear on multiple emoji → they contribute
        # multiple reactions. Naive unique-user counting would get 12, not 24.
        {
            "sender": "james",
            "text": WINNER_TEXT,
            "days_ago": 0,
            "reactions": [
                {"emoji": "tada",   "users": ["priya", "marcus", "sarah", "dan", "nina", "tom", "rachel", "lisa", "nexusbot"]},  # 8 human + 1 bot
                {"emoji": "rocket", "users": ["priya", "marcus", "sarah", "dan", "nina", "james", "nexusbot"]},                  # 6 human + 1 bot
                {"emoji": "heart",  "users": ["tom", "rachel", "lisa", "alex", "priya"]},                            # 5
                {"emoji": "fire",   "users": ["marcus", "dan", "nina", "alex", "james"]},                            # 5  → total 24 human, 26 w/ bot
            ],
        },
        # --- Rank 2: 19 total reactions ---
        {
            "sender": "sarah",
            "text": RANK2_TEXT,
            "days_ago": 1,
            "reactions": [
                {"emoji": "thumbsup", "users": ["priya", "marcus", "dan", "nina", "tom", "james", "rachel", "alex", "nexusbot"]},  # 8 human + 1 bot
                {"emoji": "eyes",     "users": ["lisa", "priya", "marcus", "dan", "nina", "james", "rachel", "nexusbot"]},          # 7 human + 1 bot
                {"emoji": "warning",  "users": ["sarah", "tom", "alex", "dan"]},                                        # 4  → total 19 human, 21 w/ bot
            ],
        },
        # --- Rank 3: 16 total reactions ---
        {
            "sender": "alex",
            "text": RANK3_TEXT,
            "days_ago": 2,
            "reactions": [
                {"emoji": "wave",  "users": ["priya", "marcus", "sarah", "dan", "nina", "tom", "james", "nexusbot"]},  # 7 human + 1 bot
                {"emoji": "clap",  "users": ["rachel", "lisa", "alex", "priya"]},                           # 4
                {"emoji": "heart", "users": ["marcus", "sarah", "dan", "nina", "tom", "nexusbot"]},                     # 5 human + 1 bot  → total 16 human, 18 w/ bot
            ],
        },
        # --- Decoy A: 14 total reactions (near threshold) ---
        {
            "sender": "marcus",
            "text": (
                "Quick reminder: please update your project status in the tracker "
                "by end of day Friday so we can prep the weekly sync."
            ),
            "days_ago": 1,
            "reactions": [
                {"emoji": "thumbsup", "users": ["priya", "sarah", "dan", "nina", "tom", "james", "rachel", "lisa", "alex"]},  # 9
                {"emoji": "white_check_mark", "users": ["priya", "marcus", "dan", "nina", "tom"]},                            # 5  → total 14
            ],
        },
        # --- Decoy B: 13 total reactions (near threshold) ---
        {
            "sender": "nina",
            "text": (
                "Just published the v2 design doc for the dashboard redesign. "
                "Would love everyone's eyes on it before Friday's review."
            ),
            "days_ago": 0,
            "reactions": [
                {"emoji": "eyes",     "users": ["priya", "marcus", "sarah", "dan", "tom", "james", "rachel"]},  # 7
                {"emoji": "art",      "users": ["lisa", "alex", "priya", "marcus"]},                             # 4
                {"emoji": "thumbsup", "users": ["dan", "nina"]},                                                 # 2  → total 13
            ],
        },
    ],
    # --- Cross-channel distractor: 30 reactions in #random ---
    # Agent must NOT include this in the leaderboard (instruction says #general)
    "random": [
        {
            "sender": "priya",
            "text": (
                "Found this absolute gem of a meme about microservices. "
                "I'm crying \U0001f602\U0001f602\U0001f602"
            ),
            "days_ago": 0,
            "reactions": [
                {"emoji": "joy",        "users": ["marcus", "sarah", "dan", "nina", "tom", "james", "rachel", "lisa", "alex"]},   # 9
                {"emoji": "rofl",       "users": ["marcus", "sarah", "dan", "nina", "tom", "james", "rachel", "lisa"]},            # 8
                {"emoji": "100",        "users": ["marcus", "sarah", "dan", "nina", "tom", "james", "rachel"]},                    # 7
                {"emoji": "fire",       "users": ["lisa", "alex", "priya", "marcus", "dan", "nina"]},                              # 6  → total 30
            ],
        },
    ],
}

FILL_CONFIG = {
    "base_scenario": "default",
}
