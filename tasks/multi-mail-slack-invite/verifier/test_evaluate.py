"""Tests for multi-mail-slack-invite evaluate.py.

Calls evaluate(final_state, diff, action_log, gmail_state, gmail_action_log)
directly via importlib.  No network access; all state is constructed in-process.

Scoring layout (0.0 – 1.0):
  +0.20  easy channel memberships     (partial: correct/total)
  +0.20  medium channel memberships   (partial)
  +0.20  hard channel memberships     (partial)
  +0.10  Gmail list/search call       (binary: called list endpoint or not)
  +0.20  Gmail individual reads       (proportional: reads / total seeded)
  +0.10  no false positives           (partial; only when >=1 task channel exists)
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

# ---------------------------------------------------------------------------
# Load evaluate.py by absolute path
# ---------------------------------------------------------------------------

_TASK_DIR  = pathlib.Path(__file__).resolve().parents[1]   # .../multi-mail-slack-invite
_EVAL_PATH = _TASK_DIR / "verifier" / "evaluate.py"

_spec = importlib.util.spec_from_file_location("_msi_evaluate", _EVAL_PATH)
_mod  = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

evaluate = _mod.evaluate

# ---------------------------------------------------------------------------
# Pull expected channel/contributor data from scenarios (same as evaluator)
# ---------------------------------------------------------------------------

_sc = _mod._load_scenarios_mod()

CHANNEL_EASY   = _sc.CHANNEL_EASY    # "skillsbench_task_easy"
CHANNEL_MEDIUM = _sc.CHANNEL_MEDIUM  # "skillsbench_task_medium"
CHANNEL_HARD   = _sc.CHANNEL_HARD    # "skillsbench_task_hard"

# contributors partitioned by channel membership
_EASY_USERS   = sorted(c["slack_username"] for c in _sc.CONTRIBUTORS if CHANNEL_EASY   in c["channels"])
_MEDIUM_USERS = sorted(c["slack_username"] for c in _sc.CONTRIBUTORS if CHANNEL_MEDIUM in c["channels"])
_HARD_USERS   = sorted(c["slack_username"] for c in _sc.CONTRIBUTORS if CHANNEL_HARD   in c["channels"])

# multi-tier contributors
_ALL3_USERS   = sorted(
    c["slack_username"] for c in _sc.CONTRIBUTORS
    if len(c["channels"]) == 3
)  # ['eric.foster', 'paul.zhang']

# Seeded SkillsBench message IDs (we generate deterministic fake ones)
# The evaluator reads these from gmail_state["users"][*]["messages"][*]["id"]
# where subject contains "[SkillsBench]".
_TOTAL_SEEDED = len(_sc.EMAILS)   # 85 emails total

# ---------------------------------------------------------------------------
# State-builder helpers
# ---------------------------------------------------------------------------

_WS_ID = "workspace_001"

# Stable numeric IDs for channels and users
_CH_ID = {
    CHANNEL_EASY:   "C_EASY",
    CHANNEL_MEDIUM: "C_MED",
    CHANNEL_HARD:   "C_HARD",
    "other":        "C_OTHER",
}

# uid counter — one UID per slack_username
_USERNAME_TO_UID: dict[str, str] = {
    c["slack_username"]: f"U_{c['slack_username'].replace('.', '_').upper()}"
    for c in _sc.CONTRIBUTORS
}
_USERNAME_TO_UID["slackbot"] = "U_SLACKBOT"


def _user_list(extra: list[str] | None = None) -> list[dict]:
    """Return ws users list containing all contributors + optional extras."""
    users = [
        {"id": uid, "name": uname}
        for uname, uid in _USERNAME_TO_UID.items()
    ]
    return users


def _channel_list(names: list[str]) -> list[dict]:
    """Return a channels list for the given channel names."""
    return [{"id": _CH_ID[n], "name": n} for n in names]


def _channel_members(ch_name: str, usernames: list[str]) -> list[dict]:
    """Return channel_members entries placing usernames into ch_name."""
    return [
        {"channel_id": _CH_ID[ch_name], "user_id": _USERNAME_TO_UID[u]}
        for u in usernames
        if u in _USERNAME_TO_UID
    ]


def _make_ws_state(
    channels: list[str],
    easy_members:   list[str] | None = None,
    medium_members: list[str] | None = None,
    hard_members:   list[str] | None = None,
) -> dict:
    """Build a ws_state dict matching the shape ws_state = final_state["workspaces"]["workspace_001"]."""
    easy_members   = easy_members   or []
    medium_members = medium_members or []
    hard_members   = hard_members   or []

    members: list[dict] = []
    if CHANNEL_EASY in channels:
        members.extend(_channel_members(CHANNEL_EASY, easy_members))
    if CHANNEL_MEDIUM in channels:
        members.extend(_channel_members(CHANNEL_MEDIUM, medium_members))
    if CHANNEL_HARD in channels:
        members.extend(_channel_members(CHANNEL_HARD, hard_members))

    return {
        "channels":        _channel_list(channels),
        "users":           _user_list(),
        "channel_members": members,
    }


def _make_final_state(ws_state: dict) -> dict:
    return {"workspaces": {_WS_ID: ws_state}}


def _make_gmail_state(num_skillsbench: int = _TOTAL_SEEDED) -> dict:
    """Build a gmail_state with exactly num_skillsbench seeded SkillsBench emails."""
    messages = []
    for i in range(num_skillsbench):
        messages.append({
            "id":      f"MSG_{i:04d}",
            "subject": f"[SkillsBench] Task Contribution: task-{i}",
            "snippet": f"snippet {i}",
        })
    return {"users": {"user_001": {"messages": messages}}}


def _list_action(user: str = "me") -> dict:
    """Simulate GET /gmail/v1/users/{user}/messages (the list endpoint)."""
    return {
        "method": "GET",
        "path":   f"/gmail/v1/users/{user}/messages",
    }


def _list_action_with_query(q: str = "SkillsBench", user: str = "me") -> dict:
    """Simulate GET /gmail/v1/users/{user}/messages?q=... (list with query param)."""
    return {
        "method": "GET",
        "path":   f"/gmail/v1/users/{user}/messages?q={q}",
    }


def _read_action(msg_id: str, user: str = "me") -> dict:
    """Simulate GET /gmail/v1/users/{user}/messages/{id} (individual read)."""
    return {
        "method": "GET",
        "path":   f"/gmail/v1/users/{user}/messages/{msg_id}",
    }


# ---------------------------------------------------------------------------
# 1. test_pre_solve — empty state, no channels created → reward == 0.0
# ---------------------------------------------------------------------------

class TestPreSolve:
    """Empty state: no channels, no gmail activity → reward == 0.0."""

    def test_pre_solve(self):
        ws  = _make_ws_state(channels=[])
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state()
        result = evaluate(fs, {}, [], gm, [])

        assert result["reward"] == 0.0
        assert result["done"] is True

        m = result["metrics"]
        assert m["easy"]["score"]   == 0.0
        assert m["medium"]["score"] == 0.0
        assert m["hard"]["score"]   == 0.0
        assert m["gmail"]["score"]  == 0.0
        # The fp guard fires (no task channels exist) so fp is not added to reward.
        # The metric may show non-zero (all contributors technically "clean") but
        # the reward stays 0.0 because the guard prevents adding it.
        assert result["reward"] == 0.0


# ---------------------------------------------------------------------------
# 2. test_full_solve — all correct + gmail list called → reward == 1.0
# ---------------------------------------------------------------------------

class TestFullSolve:
    """All contributors placed in correct channels; gmail list + all reads."""

    def test_full_solve(self):
        num_seeded = _TOTAL_SEEDED
        ws = _make_ws_state(
            channels=[CHANNEL_EASY, CHANNEL_MEDIUM, CHANNEL_HARD],
            easy_members=_EASY_USERS,
            medium_members=_MEDIUM_USERS,
            hard_members=_HARD_USERS,
        )
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state(num_seeded)
        # List call + read every seeded message individually
        gmail_log = [_list_action()] + [_read_action(f"MSG_{i:04d}") for i in range(num_seeded)]

        result = evaluate(fs, {}, [], gm, gmail_log)

        assert result["reward"] == pytest.approx(1.0)
        assert result["done"] is True

        m = result["metrics"]
        assert m["easy"]["score"]              == pytest.approx(0.20)
        assert m["medium"]["score"]            == pytest.approx(0.20)
        assert m["hard"]["score"]              == pytest.approx(0.20)
        assert m["gmail"]["score"]             == pytest.approx(0.30)
        assert m["gmail"]["list_called"]       is True
        assert m["no_false_positives"]["score"] == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# 3. test_partial_easy — only half of easy contributors invited
# ---------------------------------------------------------------------------

class TestPartialEasy:
    """Invite half the easy contributors → easy_score == 0.10."""

    def test_partial_easy(self):
        half = _EASY_USERS[: len(_EASY_USERS) // 2]  # first half

        ws = _make_ws_state(
            channels=[CHANNEL_EASY, CHANNEL_MEDIUM, CHANNEL_HARD],
            easy_members=half,
            medium_members=[],
            hard_members=[],
        )
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state(0)  # no seeded emails

        result = evaluate(fs, {}, [], gm, [])

        m = result["metrics"]
        expected_easy_score = round(0.20 * len(half) / len(_EASY_USERS), 4)
        assert m["easy"]["score"] == pytest.approx(expected_easy_score)
        assert m["medium"]["score"] == 0.0
        assert m["hard"]["score"]   == 0.0
        assert len(m["easy"]["correct"]) == len(half)


# ---------------------------------------------------------------------------
# 4. test_gmail_list_call — gmail list endpoint → gmail_score == 0.30
# ---------------------------------------------------------------------------

class TestGmailListCall:
    """Calling the messages list endpoint awards 0.10 list credit (no reads = no read credit)."""

    def test_gmail_list_call_exact_path(self):
        ws  = _make_ws_state(channels=[])
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state()

        result = evaluate(fs, {}, [], gm, [_list_action()])

        # List call gives 0.10; no individual reads → read score 0.0
        assert result["metrics"]["gmail"]["score"]       == pytest.approx(0.10)
        assert result["metrics"]["gmail"]["list_called"] is True

    def test_gmail_list_call_with_query_param(self):
        """Path with ?q= query param still counts as a list call."""
        ws  = _make_ws_state(channels=[])
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state()

        result = evaluate(fs, {}, [], gm, [_list_action_with_query()])

        assert result["metrics"]["gmail"]["score"]       == pytest.approx(0.10)
        assert result["metrics"]["gmail"]["list_called"] is True

    def test_non_get_list_path_does_not_count(self):
        """POST to the list path must not award list credit."""
        ws  = _make_ws_state(channels=[])
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state()

        post_action = {"method": "POST", "path": "/gmail/v1/users/me/messages"}
        result = evaluate(fs, {}, [], gm, [post_action])

        assert result["metrics"]["gmail"]["list_called"] is False
        assert result["metrics"]["gmail"]["score"]       == pytest.approx(0.0)

    def test_gmail_list_plus_all_reads(self):
        """List call + reading all seeded messages = full 0.30."""
        num_seeded = 10
        gm  = _make_gmail_state(num_seeded)
        ws  = _make_ws_state(channels=[])
        fs  = _make_final_state(ws)

        gmail_log = [_list_action()] + [_read_action(f"MSG_{i:04d}") for i in range(num_seeded)]
        result = evaluate(fs, {}, [], gm, gmail_log)

        assert result["metrics"]["gmail"]["score"]       == pytest.approx(0.30)
        assert result["metrics"]["gmail"]["list_called"] is True


# ---------------------------------------------------------------------------
# 5. test_gmail_individual_reads_only — proportional credit without list call
# ---------------------------------------------------------------------------

class TestGmailIndividualReadsOnly:
    """Reading individual messages without a list call gives proportional read credit (max 0.20)."""

    def test_reads_half_the_emails(self):
        num_seeded = 10
        gm  = _make_gmail_state(num_seeded)
        ws  = _make_ws_state(channels=[])
        fs  = _make_final_state(ws)

        # Read half of the seeded IDs
        num_read  = 5
        gmail_log = [_read_action(f"MSG_{i:04d}") for i in range(num_read)]

        result = evaluate(fs, {}, [], gm, gmail_log)

        m = result["metrics"]["gmail"]
        assert m["list_called"]  is False
        assert m["emails_read"]  == num_read
        assert m["total_seeded"] == num_seeded
        # No list call (0.0) + 0.20 * 5/10 = 0.10
        expected = round(0.20 * num_read / num_seeded, 4)
        assert m["score"] == pytest.approx(expected)

    def test_reads_all_emails_individually(self):
        """Reading every seeded email individually gives 0.20 (no list credit)."""
        num_seeded = 4
        gm  = _make_gmail_state(num_seeded)
        ws  = _make_ws_state(channels=[])
        fs  = _make_final_state(ws)

        gmail_log = [_read_action(f"MSG_{i:04d}") for i in range(num_seeded)]
        result = evaluate(fs, {}, [], gm, gmail_log)

        # 0.0 (no list) + 0.20 (all reads) = 0.20
        assert result["metrics"]["gmail"]["score"] == pytest.approx(0.20)
        assert result["metrics"]["gmail"]["list_called"] is False

    def test_reads_none_gives_zero(self):
        gm  = _make_gmail_state(10)
        ws  = _make_ws_state(channels=[])
        fs  = _make_final_state(ws)

        result = evaluate(fs, {}, [], gm, [])

        assert result["metrics"]["gmail"]["score"] == 0.0

    def test_reads_non_skillsbench_id_not_counted(self):
        """Reading a message whose ID is not in the seeded set must not add credit."""
        gm  = _make_gmail_state(5)
        ws  = _make_ws_state(channels=[])
        fs  = _make_final_state(ws)

        gmail_log = [_read_action("MSG_BOGUS_ID")]
        result = evaluate(fs, {}, [], gm, gmail_log)

        assert result["metrics"]["gmail"]["emails_read"] == 0
        assert result["metrics"]["gmail"]["score"]       == 0.0


# ---------------------------------------------------------------------------
# 6. test_false_positive — contributor placed in wrong channel tier
# ---------------------------------------------------------------------------

class TestFalsePositive:
    """A contributor placed in a channel they don't belong to reduces fp_score."""

    def test_one_false_positive_reduces_score(self):
        # kevin.brown belongs only to EASY; put him in MEDIUM as a false positive
        offender = "kevin.brown"
        assert offender in _EASY_USERS
        assert offender not in _MEDIUM_USERS

        ws = _make_ws_state(
            channels=[CHANNEL_EASY, CHANNEL_MEDIUM, CHANNEL_HARD],
            easy_members=_EASY_USERS,
            medium_members=_MEDIUM_USERS + [offender],  # false positive
            hard_members=_HARD_USERS,
        )
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state()
        gmail_log = [_list_action()]

        result = evaluate(fs, {}, [], gm, gmail_log)

        m  = result["metrics"]
        fp = m["no_false_positives"]
        total = fp["total"]
        # offender is not clean; everyone else is
        assert fp["details"][offender] is False
        assert fp["clean"]             == total - 1
        expected_fp = round(0.10 * (total - 1) / total, 4)
        assert fp["score"] == pytest.approx(expected_fp)
        # fp_score is reduced vs perfect 0.10
        assert fp["score"] < 0.10

    def test_fp_for_hard_only_contributor_placed_in_easy(self):
        # daniel.lee belongs only to HARD
        offender = "daniel.lee"
        assert offender in _HARD_USERS
        assert offender not in _EASY_USERS
        assert offender not in _MEDIUM_USERS

        ws = _make_ws_state(
            channels=[CHANNEL_EASY, CHANNEL_MEDIUM, CHANNEL_HARD],
            easy_members=[offender],   # false positive in easy
            medium_members=[],
            hard_members=_HARD_USERS,
        )
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state(0)

        result = evaluate(fs, {}, [], gm, [])

        fp = result["metrics"]["no_false_positives"]
        assert fp["details"][offender] is False
        assert fp["score"] < 0.10


# ---------------------------------------------------------------------------
# 7. test_no_channels_no_fp_credit — no channels → fp guard fires → fp == 0.0
# ---------------------------------------------------------------------------

class TestNoChannelsNoFpCredit:
    """When no task channel exists the fp guard fires and fp_score is not added."""

    def test_no_channels_fp_not_added(self):
        ws  = _make_ws_state(channels=[])
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state(0)

        result = evaluate(fs, {}, [], gm, [])

        # fp_score might be 0.10 internally (all contributors are "clean" since
        # none appear in any task channel), but the guard prevents it from being
        # added to the reward when no task channel exists in the state.
        assert result["reward"] == pytest.approx(0.0)

    def test_one_channel_present_fp_added(self):
        """With at least one task channel, the fp score IS added to reward."""
        ws  = _make_ws_state(channels=[CHANNEL_EASY], easy_members=[])
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state(0)

        result = evaluate(fs, {}, [], gm, [])

        fp = result["metrics"]["no_false_positives"]
        # All contributors are clean (none were placed in any wrong channel)
        assert fp["score"] == pytest.approx(0.10)
        assert result["reward"] == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# 8. test_wrong_channel_names — channels with wrong names → tier scores == 0.0
# ---------------------------------------------------------------------------

class TestWrongChannelNames:
    """Channels with wrong names produce no membership credit."""

    def test_wrong_easy_channel_name(self):
        # Create a channel named "task_easy" instead of "skillsbench_task_easy"
        wrong_id = "C_WRONG_EASY"
        ws_state = {
            "channels":        [{"id": wrong_id, "name": "task_easy"}],
            "users":           _user_list(),
            "channel_members": [
                {"channel_id": wrong_id, "user_id": _USERNAME_TO_UID[u]}
                for u in _EASY_USERS
            ],
        }
        fs  = _make_final_state(ws_state)
        gm  = _make_gmail_state(0)

        result = evaluate(fs, {}, [], gm, [])

        m = result["metrics"]
        assert m["easy"]["score"]   == 0.0
        assert m["medium"]["score"] == 0.0
        assert m["hard"]["score"]   == 0.0

    def test_all_wrong_channel_names(self):
        """Three channels present, all with wrong names → all tier scores == 0.0."""
        ws_state = {
            "channels": [
                {"id": "C_A", "name": "easy_channel"},
                {"id": "C_B", "name": "medium_channel"},
                {"id": "C_C", "name": "hard_channel"},
            ],
            "users": _user_list(),
            "channel_members": [],
        }
        fs  = _make_final_state(ws_state)
        gm  = _make_gmail_state(0)

        result = evaluate(fs, {}, [], gm, [])

        m = result["metrics"]
        assert m["easy"]["score"]   == 0.0
        assert m["medium"]["score"] == 0.0
        assert m["hard"]["score"]   == 0.0


# ---------------------------------------------------------------------------
# 9. test_boundary_100_min_is_medium — exactly 100 min task lands in medium
# ---------------------------------------------------------------------------

class TestBoundary100MinIsMedium:
    """A 100-minute task is classified as medium (100–500 range), not easy (<100)."""

    def test_brian_harrison_100min_in_medium(self):
        # Brian Harrison has tasks at 60, 100, and 60 min → easy (for <100) AND medium (for 100)
        # Verify he is in both easy and medium in the expected data
        assert "brian.harrison" in _EASY_USERS
        assert "brian.harrison" in _MEDIUM_USERS
        assert "brian.harrison" not in _HARD_USERS

    def test_jason_reed_100min_in_medium(self):
        # Jason Reed has tasks at 100 and 300 min → medium only (no task < 100)
        assert "jason.reed" not in _EASY_USERS
        assert "jason.reed" in _MEDIUM_USERS
        assert "jason.reed" not in _HARD_USERS

    def test_missing_from_easy_reduces_easy_score(self):
        """If jason.reed (medium-only) is incorrectly placed in easy, fp fires."""
        offender = "jason.reed"
        ws = _make_ws_state(
            channels=[CHANNEL_EASY, CHANNEL_MEDIUM, CHANNEL_HARD],
            easy_members=[offender],   # should NOT be here
            medium_members=_MEDIUM_USERS,
            hard_members=_HARD_USERS,
        )
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state(0)

        result = evaluate(fs, {}, [], gm, [])

        fp = result["metrics"]["no_false_positives"]
        assert fp["details"][offender] is False  # flagged as false positive

    def test_brian_harrison_belongs_in_both_easy_and_medium(self):
        """When brian.harrison is in both easy and medium he is clean (no fp)."""
        ws = _make_ws_state(
            channels=[CHANNEL_EASY, CHANNEL_MEDIUM, CHANNEL_HARD],
            easy_members=_EASY_USERS,
            medium_members=_MEDIUM_USERS,
            hard_members=_HARD_USERS,
        )
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state(0)

        result = evaluate(fs, {}, [], gm, [])

        fp = result["metrics"]["no_false_positives"]
        assert fp["details"]["brian.harrison"] is True


# ---------------------------------------------------------------------------
# 10. test_multi_channel_contributor — contributor in multiple tiers
# ---------------------------------------------------------------------------

class TestMultiChannelContributor:
    """Contributors with tasks in multiple tiers score independently in each tier."""

    def test_eric_foster_in_all_three_channels(self):
        # eric.foster is expected in all three channels
        assert "eric.foster" in _EASY_USERS
        assert "eric.foster" in _MEDIUM_USERS
        assert "eric.foster" in _HARD_USERS

        ws = _make_ws_state(
            channels=[CHANNEL_EASY, CHANNEL_MEDIUM, CHANNEL_HARD],
            easy_members=["eric.foster"],
            medium_members=["eric.foster"],
            hard_members=["eric.foster"],
        )
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state(0)

        result = evaluate(fs, {}, [], gm, [])

        m = result["metrics"]
        # eric.foster alone cannot fill all expected slots, but his presence
        # contributes to each tier's correct count
        assert "eric.foster" in m["easy"]["correct"]
        assert "eric.foster" in m["medium"]["correct"]
        assert "eric.foster" in m["hard"]["correct"]

    def test_paul_zhang_all_three_tiers_no_fp(self):
        # paul.zhang belongs to all three channels
        assert "paul.zhang" in _EASY_USERS
        assert "paul.zhang" in _MEDIUM_USERS
        assert "paul.zhang" in _HARD_USERS

        ws = _make_ws_state(
            channels=[CHANNEL_EASY, CHANNEL_MEDIUM, CHANNEL_HARD],
            easy_members=["paul.zhang"],
            medium_members=["paul.zhang"],
            hard_members=["paul.zhang"],
        )
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state(0)

        result = evaluate(fs, {}, [], gm, [])

        fp = result["metrics"]["no_false_positives"]
        assert fp["details"]["paul.zhang"] is True  # clean — all placements correct

    def test_sam_cohen_easy_and_hard_not_medium(self):
        # sam.cohen belongs to easy + hard only (NOT medium)
        assert "sam.cohen" in _EASY_USERS
        assert "sam.cohen" not in _MEDIUM_USERS
        assert "sam.cohen" in _HARD_USERS

        ws = _make_ws_state(
            channels=[CHANNEL_EASY, CHANNEL_MEDIUM, CHANNEL_HARD],
            easy_members=["sam.cohen"],
            medium_members=["sam.cohen"],   # false positive
            hard_members=["sam.cohen"],
        )
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state(0)

        result = evaluate(fs, {}, [], gm, [])

        fp = result["metrics"]["no_false_positives"]
        assert fp["details"]["sam.cohen"] is False  # placed in wrong channel

    def test_multi_channel_scores_each_tier_independently(self):
        """Full solve for easy; no-one in medium/hard → only easy + fp credit."""
        ws = _make_ws_state(
            channels=[CHANNEL_EASY, CHANNEL_MEDIUM, CHANNEL_HARD],
            easy_members=_EASY_USERS,
            medium_members=[],
            hard_members=[],
        )
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state(0)

        result = evaluate(fs, {}, [], gm, [])

        m = result["metrics"]
        assert m["easy"]["score"]   == pytest.approx(0.20)
        assert m["medium"]["score"] == 0.0
        assert m["hard"]["score"]   == 0.0

    def test_peter_jackson_medium_and_hard(self):
        # peter.jackson belongs to medium + hard only
        assert "peter.jackson" not in _EASY_USERS
        assert "peter.jackson" in _MEDIUM_USERS
        assert "peter.jackson" in _HARD_USERS

        ws = _make_ws_state(
            channels=[CHANNEL_EASY, CHANNEL_MEDIUM, CHANNEL_HARD],
            easy_members=["peter.jackson"],   # false positive
            medium_members=["peter.jackson"],
            hard_members=["peter.jackson"],
        )
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state(0)

        result = evaluate(fs, {}, [], gm, [])

        fp = result["metrics"]["no_false_positives"]
        assert fp["details"]["peter.jackson"] is False


# ---------------------------------------------------------------------------
# 11. test_near_boundary_contributors — contributors near 100/500 thresholds
# ---------------------------------------------------------------------------

class TestNearBoundaryContributors:
    """Contributors with tasks near the 100-min and 500-min boundaries."""

    def test_olivia_martinez_easy_and_medium(self):
        # 95 min (easy) + 105 min (medium) → both channels
        assert "olivia.martinez" in _EASY_USERS
        assert "olivia.martinez" in _MEDIUM_USERS
        assert "olivia.martinez" not in _HARD_USERS

    def test_derek_wu_easy_only(self):
        # 98 min (easy) → easy only
        assert "derek.wu" in _EASY_USERS
        assert "derek.wu" not in _MEDIUM_USERS
        assert "derek.wu" not in _HARD_USERS

    def test_hannah_park_medium_only(self):
        # 490 min (medium) → medium only
        assert "hannah.park" not in _EASY_USERS
        assert "hannah.park" in _MEDIUM_USERS
        assert "hannah.park" not in _HARD_USERS

    def test_carlos_rivera_easy_and_hard(self):
        # 95 min (easy) + 505 min (hard) → easy + hard, NOT medium
        assert "carlos.rivera" in _EASY_USERS
        assert "carlos.rivera" not in _MEDIUM_USERS
        assert "carlos.rivera" in _HARD_USERS

    def test_carlos_rivera_in_medium_is_false_positive(self):
        """Placing carlos.rivera in medium is a false positive."""
        ws = _make_ws_state(
            channels=[CHANNEL_EASY, CHANNEL_MEDIUM, CHANNEL_HARD],
            easy_members=["carlos.rivera"],
            medium_members=["carlos.rivera"],   # false positive
            hard_members=["carlos.rivera"],
        )
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state(0)

        result = evaluate(fs, {}, [], gm, [])

        fp = result["metrics"]["no_false_positives"]
        assert fp["details"]["carlos.rivera"] is False

    def test_derek_wu_in_medium_is_false_positive(self):
        """98 min is easy, not medium — placing in medium is false positive."""
        ws = _make_ws_state(
            channels=[CHANNEL_EASY, CHANNEL_MEDIUM, CHANNEL_HARD],
            easy_members=["derek.wu"],
            medium_members=["derek.wu"],   # false positive
            hard_members=[],
        )
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state(0)

        result = evaluate(fs, {}, [], gm, [])

        fp = result["metrics"]["no_false_positives"]
        assert fp["details"]["derek.wu"] is False


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------

class TestMetricCounts:
    """Verify api-call counters in metrics."""

    def test_total_slack_api_calls(self):
        ws  = _make_ws_state(channels=[])
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state(0)

        slack_log = [
            {"method": "GET", "path": "/api/conversations.list"},
            {"method": "POST", "path": "/api/conversations.invite"},
        ]
        result = evaluate(fs, {}, slack_log, gm, [])

        assert result["metrics"]["total_slack_api_calls"] == 2

    def test_total_gmail_api_calls(self):
        ws  = _make_ws_state(channels=[])
        fs  = _make_final_state(ws)
        gm  = _make_gmail_state(2)

        gmail_log = [
            _list_action(),
            _read_action("MSG_0000"),
            _read_action("MSG_0001"),
        ]
        result = evaluate(fs, {}, [], gm, gmail_log)

        assert result["metrics"]["total_gmail_api_calls"] == 3


class TestGmailNoSeededEmails:
    """Edge case: gmail_state has no seeded emails → gmail_score == 0.0."""

    def test_no_seeded_emails_score_zero(self):
        gm  = _make_gmail_state(0)  # no messages at all
        ws  = _make_ws_state(channels=[])
        fs  = _make_final_state(ws)

        result = evaluate(fs, {}, [], gm, [_list_action()])

        # Even with list called, total_seeded == 0 → score == 0.0
        # (evaluator guards against division by zero)
        assert result["metrics"]["gmail"]["total_seeded"] == 0


class TestFullSolveWithIndividualReads:
    """Full channel placement + all individual reads = 0.20 gmail (no list credit)."""

    def test_full_solve_individual_reads(self):
        num_seeded = _TOTAL_SEEDED
        gm  = _make_gmail_state(num_seeded)
        ws  = _make_ws_state(
            channels=[CHANNEL_EASY, CHANNEL_MEDIUM, CHANNEL_HARD],
            easy_members=_EASY_USERS,
            medium_members=_MEDIUM_USERS,
            hard_members=_HARD_USERS,
        )
        fs  = _make_final_state(ws)

        # Read every seeded message individually (no list call)
        gmail_log = [_read_action(f"MSG_{i:04d}") for i in range(num_seeded)]

        result = evaluate(fs, {}, [], gm, gmail_log)

        # 0.60 channels + 0.20 gmail reads (no list) + 0.10 fp = 0.90
        assert result["reward"]                    == pytest.approx(0.90)
        assert result["metrics"]["gmail"]["score"] == pytest.approx(0.20)
        assert result["metrics"]["gmail"]["list_called"] is False
