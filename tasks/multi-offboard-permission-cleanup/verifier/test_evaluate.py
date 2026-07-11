"""Unit tests for multi-offboard-permission-cleanup evaluator."""

import importlib.util
import os
import sys

# ---------------------------------------------------------------------------
# Dynamic imports: evaluate.py and needles.py
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, "..", "data")

os.environ.setdefault("TASKS_DIR", os.path.join(_HERE, "..", ".."))


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_eval_mod = _load_module("evaluate", os.path.join(_HERE, "evaluate.py"))
_needles = _load_module("needles", os.path.join(_DATA, "needles.py"))

evaluate = _eval_mod.evaluate

DECK_ID = _needles.STRATEGY_DECK_ID
HIRING_ID = _needles.HIRING_PLAN_ID
UNAUTH = _needles.UNAUTHORIZED_EMAIL
ALL_LEGIT = _needles.ALL_LEGITIMATE_EMAILS
FOLDER = "application/vnd.google-apps.folder"

LEADER_FOLDER_ID = "folder_leadership_001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _perm(file_id, email, role="reader"):
    return {"fileId": file_id, "emailAddress": email, "role": role}


def _state(deck_exists=True, deck_trashed=False, deck_emails=None,
           hiring_emails=None):
    """Build a minimal final_state dict.

    deck_emails: set of emails currently on the Strategy Deck.
                 Default = all legit + unauthorized (initial state).
    hiring_emails: set of emails on the Hiring Plan.
                   Default = includes marco.
    """
    files = [
        {"id": LEADER_FOLDER_ID, "name": "Leadership", "mimeType": FOLDER},
    ]
    if deck_exists:
        files.append({
            "id": DECK_ID,
            "name": "Q2 Strategy Deck - Confidential",
            "mimeType": "application/vnd.google-apps.spreadsheet",
            "parentId": LEADER_FOLDER_ID,
            "trashed": deck_trashed,
        })

    if deck_emails is None:
        deck_emails = set(e.lower() for e in ALL_LEGIT) | {UNAUTH.lower()}
    if hiring_emails is None:
        hiring_emails = {"alex@aurora-tech.com", "jordan@aurora-tech.com",
                         UNAUTH.lower()}

    perms = []
    # owner perm (always present)
    perms.append(_perm(DECK_ID, "alex@nexusai.com", "owner"))
    for email in deck_emails:
        perms.append(_perm(DECK_ID, email))
    for email in hiring_emails:
        perms.append(_perm(HIRING_ID, email))

    return {"files": files, "permissions": perms}


def _diff():
    return {"files": {"added": [], "updated": [], "deleted": []},
            "permissions": {"added": [], "updated": [], "deleted": []}}


def _log(*actions):
    """Build an action log from symbolic action names."""
    entries = []
    action_map = {
        "search_deck": {
            "method": "GET",
            "path": f"/drive/v3/files?q=Strategy",
        },
        "get_deck": {
            "method": "GET",
            "path": f"/drive/v3/files/{DECK_ID}",
        },
        "list_perms": {
            "method": "GET",
            "path": f"/drive/v3/files/{DECK_ID}/permissions",
        },
        "check_slack": {
            "method": "GET",
            "path": "/api/conversations.history?channel=C11LEADERSHIP",
        },
        "search_slack": {
            "method": "GET",
            "path": "/api/search.messages?query=marco",
        },
        "notify": {
            "method": "POST",
            "path": "/api/chat.postMessage",
            "body": "Revoked Marco Silva access to the Q2 Strategy Deck.",
        },
        "notify_generic": {
            "method": "POST",
            "path": "/api/chat.postMessage",
            "body": "Done, all cleaned up.",
        },
        "flag_hiring": {
            "method": "POST",
            "path": "/api/chat.postMessage",
            "body": "Marco also has access to the Hiring Plan 2026.",
        },
    }
    for a in actions:
        if a in action_map:
            entries.append(action_map[a])
    return entries


def _all_legit_set():
    return set(e.lower() for e in ALL_LEGIT)


def _initial_emails():
    return _all_legit_set() | {UNAUTH.lower()}


# ---------------------------------------------------------------------------
# Tests: No action
# ---------------------------------------------------------------------------
class TestNoAction:
    def test_no_action_scores_zero(self):
        result = evaluate(_state(), _diff(), [])
        assert result["reward"] == 0.0

    def test_no_action_no_precision_awarded(self):
        """Precision is gated on any_perm_change, so reward stays 0."""
        result = evaluate(_state(), _diff(), [])
        # precision metric is computed (0.25) but not added to reward
        assert result["reward"] == 0.0


# ---------------------------------------------------------------------------
# Tests: Perfect score
# ---------------------------------------------------------------------------
class TestPerfectScore:
    def test_full_score(self):
        # Marco revoked, all legit preserved, slack checked, notified, hiring flagged
        deck_emails = _all_legit_set()  # marco removed
        hiring_emails = {"alex@aurora-tech.com", "jordan@aurora-tech.com"}  # marco removed
        result = evaluate(
            _state(deck_emails=deck_emails, hiring_emails=hiring_emails),
            _diff(),
            _log("search_deck", "list_perms", "check_slack", "notify", "flag_hiring"),
        )
        assert result["reward"] == 1.0

    def test_perfect_without_hiring_bonus(self):
        # 0.05+0.05+0.20+0.25+0.25+0.10 = 0.90
        deck_emails = _all_legit_set()
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            _log("search_deck", "list_perms", "check_slack", "notify"),
        )
        assert result["reward"] == 0.9


# ---------------------------------------------------------------------------
# Tests: Core action only (no process steps)
# ---------------------------------------------------------------------------
class TestCoreAction:
    def test_marco_only_no_process(self):
        # 0.25 (marco) + 0.25 (precision) = 0.50
        deck_emails = _all_legit_set()
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            [],
        )
        assert result["reward"] == 0.50

    def test_marco_plus_search(self):
        # 0.05 (found) + 0.25 (marco) + 0.25 (precision) = 0.55
        deck_emails = _all_legit_set()
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            _log("search_deck"),
        )
        assert result["reward"] == 0.55


# ---------------------------------------------------------------------------
# Tests: Precision scoring (proportional deductions)
# ---------------------------------------------------------------------------
class TestPrecision:
    def test_one_legit_removed(self):
        # Remove marco + lisa: 0.25 + (0.25-0.05) = 0.45
        deck_emails = _all_legit_set() - {"lisa.chang@meridianpartners.com"}
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            [],
        )
        assert result["reward"] == 0.45
        assert result["metrics"]["legit_removed_count"] == 1

    def test_two_legit_removed(self):
        # Remove marco + lisa + david: 0.25 + (0.25-0.10) = 0.40
        deck_emails = _all_legit_set() - {
            "lisa.chang@meridianpartners.com",
            "david.park@kensingtonlegal.com",
        }
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            [],
        )
        assert result["reward"] == 0.40
        assert result["metrics"]["legit_removed_count"] == 2

    def test_five_legit_removed_with_overcorrection(self):
        # Remove marco + 5 legit: 0.25 + max(0, 0.25-0.25) - 0.20 = 0.05
        deck_emails = _all_legit_set() - {
            "lisa.chang@meridianpartners.com",
            "david.park@kensingtonlegal.com",
            "nina.vogt@strattonbridge.io",
            "priya@aurora-tech.com",
            "sarah@aurora-tech.com",
        }
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            [],
        )
        assert result["reward"] == 0.05
        assert result["metrics"]["overcorrection"] == 1
        assert result["metrics"]["legit_removed_count"] == 5

    def test_all_legit_removed_nuclear(self):
        # Remove everyone including marco: 0.25 + 0.00 - 0.20 = 0.05
        deck_emails = set()  # all removed
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            [],
        )
        assert result["reward"] == 0.05
        assert result["metrics"]["overcorrection"] == 1
        assert result["metrics"]["legit_removed_count"] == 8

    def test_precision_floor_at_zero(self):
        # More than 5 legit removed: precision floors at 0
        deck_emails = {"alex@aurora-tech.com"}  # only one kept
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            [],
        )
        assert result["metrics"]["precision"] == 0.0


# ---------------------------------------------------------------------------
# Tests: Overcorrection penalty
# ---------------------------------------------------------------------------
class TestOvercorrection:
    def test_two_legit_no_penalty(self):
        deck_emails = _all_legit_set() - {
            "lisa.chang@meridianpartners.com",
            "david.park@kensingtonlegal.com",
        }
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            [],
        )
        assert result["metrics"]["overcorrection"] == 0

    def test_three_legit_triggers_penalty(self):
        deck_emails = _all_legit_set() - {
            "lisa.chang@meridianpartners.com",
            "david.park@kensingtonlegal.com",
            "nina.vogt@strattonbridge.io",
        }
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            [],
        )
        assert result["metrics"]["overcorrection"] == 1
        # 0.25 + (0.25 - 0.15) - 0.20 = 0.15
        assert result["reward"] == 0.15


# ---------------------------------------------------------------------------
# Tests: File deleted
# ---------------------------------------------------------------------------
class TestFileDeleted:
    def test_file_deleted_scores_zero(self):
        result = evaluate(
            _state(deck_exists=False),
            _diff(),
            _log("search_deck", "list_perms"),
        )
        assert result["reward"] == 0.0
        assert result["metrics"]["file_deleted"] == 1

    def test_file_trashed_scores_zero(self):
        result = evaluate(
            _state(deck_trashed=True),
            _diff(),
            _log("search_deck"),
        )
        assert result["reward"] == 0.0


# ---------------------------------------------------------------------------
# Tests: Notification
# ---------------------------------------------------------------------------
class TestNotification:
    def test_notify_with_keywords(self):
        deck_emails = _all_legit_set()
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            _log("search_deck", "notify"),
        )
        assert result["metrics"]["notified"] == 1

    def test_generic_message_no_credit(self):
        deck_emails = _all_legit_set()
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            _log("search_deck", "notify_generic"),
        )
        assert result["metrics"]["notified"] == 0


# ---------------------------------------------------------------------------
# Tests: Hiring plan bonus
# ---------------------------------------------------------------------------
class TestHiringPlan:
    def test_flagged_via_message(self):
        deck_emails = _all_legit_set()
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            _log("flag_hiring"),
        )
        assert result["metrics"]["flagged_hiring"] == 1

    def test_flagged_via_revocation(self):
        deck_emails = _all_legit_set()
        hiring_emails = {"alex@aurora-tech.com", "jordan@aurora-tech.com"}
        result = evaluate(
            _state(deck_emails=deck_emails, hiring_emails=hiring_emails),
            _diff(),
            [],
        )
        assert result["metrics"]["flagged_hiring"] == 1

    def test_not_flagged_when_marco_still_on_hiring(self):
        deck_emails = _all_legit_set()
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            [],
        )
        assert result["metrics"]["flagged_hiring"] == 0


# ---------------------------------------------------------------------------
# Tests: Slack checking
# ---------------------------------------------------------------------------
class TestSlackCheck:
    def test_conversations_history(self):
        result = evaluate(_state(), _diff(), _log("check_slack"))
        assert result["metrics"]["checked_slack"] == 1

    def test_search_messages(self):
        result = evaluate(_state(), _diff(), _log("search_slack"))
        assert result["metrics"]["checked_slack"] == 1


# ---------------------------------------------------------------------------
# Tests: Scenario combinations
# ---------------------------------------------------------------------------
class TestScenarios:
    def test_did_nothing(self):
        """Agent takes no action at all."""
        result = evaluate(_state(), _diff(), [])
        assert result["reward"] == 0.0

    def test_only_investigated(self):
        """Agent searched and listed perms but changed nothing."""
        result = evaluate(
            _state(),
            _diff(),
            _log("search_deck", "list_perms", "check_slack"),
        )
        # 0.05 + 0.05 + 0.20 = 0.30 (no perm changes, no precision credit)
        assert result["reward"] == 0.30

    def test_remove_all_external_naive(self):
        """Agent removes all external users (common failure mode)."""
        deck_emails = _all_legit_set() - {
            "lisa.chang@meridianpartners.com",
            "david.park@kensingtonlegal.com",
            "nina.vogt@strattonbridge.io",
        }
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            _log("search_deck", "list_perms"),
        )
        # 0.05 + 0.05 + 0.25 + (0.25-0.15) - 0.20 = 0.25
        assert result["reward"] == 0.25
        assert result["metrics"]["legit_removed_count"] == 3

    def test_marco_only_with_full_process(self):
        """Perfect surgical fix with all process steps."""
        deck_emails = _all_legit_set()
        hiring_emails = {"alex@aurora-tech.com", "jordan@aurora-tech.com"}
        result = evaluate(
            _state(deck_emails=deck_emails, hiring_emails=hiring_emails),
            _diff(),
            _log("search_deck", "list_perms", "check_slack", "notify", "flag_hiring"),
        )
        assert result["reward"] == 1.0

    def test_reward_clamped_at_zero(self):
        """Even worst case, reward never goes below 0."""
        # File exists but all legit removed, no marco revoked, overcorrection
        deck_emails = set()  # all removed including marco
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            [],
        )
        assert result["reward"] >= 0.0

    def test_marco_not_revoked_but_legit_removed(self):
        """Agent removes legitimate users but not Marco (wrong target)."""
        deck_emails = (_all_legit_set() - {
            "lisa.chang@meridianpartners.com",
            "david.park@kensingtonlegal.com",
        }) | {UNAUTH.lower()}
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            [],
        )
        assert result["metrics"]["marco_revoked"] == 0
        assert result["metrics"]["legit_removed_count"] == 2
        # 0.00 (no marco) + (0.25 - 0.10) (precision) = 0.15
        assert result["reward"] == 0.15

    def test_process_steps_with_imprecision(self):
        """Full process but removed one legit alongside Marco."""
        deck_emails = _all_legit_set() - {"nina.vogt@strattonbridge.io"}
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            _log("search_deck", "list_perms", "check_slack", "notify"),
        )
        # 0.05+0.05+0.20+0.25+(0.25-0.05)+0.10 = 0.85
        assert result["reward"] == 0.85
        assert result["metrics"]["legit_removed_count"] == 1


# ---------------------------------------------------------------------------
# Tests: Found deck detection (fallback paths)
# ---------------------------------------------------------------------------
class TestFoundDeck:
    def test_found_via_file_id_get(self):
        """Agent accesses the deck directly by ID."""
        result = evaluate(_state(), _diff(), _log("get_deck"))
        assert result["metrics"]["found_deck"] == 1

    def test_found_via_search_query(self):
        """Agent searches for the file by name."""
        result = evaluate(_state(), _diff(), _log("search_deck"))
        assert result["metrics"]["found_deck"] == 1

    def test_not_found_with_unrelated_action(self):
        """Unrelated GET does not count as finding the deck."""
        result = evaluate(_state(), _diff(), [{
            "method": "GET",
            "path": "/drive/v3/files/some_other_id",
        }])
        assert result["metrics"]["found_deck"] == 0


# ---------------------------------------------------------------------------
# Tests: Notification with request_body dict format
# ---------------------------------------------------------------------------
class TestNotificationFormats:
    def test_notify_via_request_body_dict(self):
        """Notification detected when body is in request_body dict."""
        deck_emails = _all_legit_set()
        action = {
            "method": "POST",
            "path": "/api/chat.postMessage",
            "request_body": {"channel": "C123", "text": "Revoked Marco access."},
        }
        result = evaluate(_state(deck_emails=deck_emails), _diff(), [action])
        assert result["metrics"]["notified"] == 1

    def test_flag_hiring_via_request_body_dict(self):
        """Hiring plan flag detected via request_body dict."""
        deck_emails = _all_legit_set()
        action = {
            "method": "POST",
            "path": "/api/chat.postMessage",
            "request_body": {"channel": "C123", "text": "Marco has access to the Hiring Plan too."},
        }
        result = evaluate(_state(deck_emails=deck_emails), _diff(), [action])
        assert result["metrics"]["flagged_hiring"] == 1


# ---------------------------------------------------------------------------
# Tests: Dict-style files_list in state
# ---------------------------------------------------------------------------
class TestDictFilesState:
    def test_dict_files_list(self):
        """State with files as dict (keyed by ID) instead of list."""
        deck_emails = _all_legit_set()
        state = {
            "files": {
                DECK_ID: {
                    "id": DECK_ID,
                    "name": "Q2 Strategy Deck - Confidential",
                    "mimeType": "application/vnd.google-apps.spreadsheet",
                },
            },
            "permissions": [
                _perm(DECK_ID, email) for email in deck_emails
            ] + [
                _perm(HIRING_ID, UNAUTH.lower()),
                _perm(HIRING_ID, "alex@aurora-tech.com"),
            ],
        }
        result = evaluate(state, _diff(), _log("search_deck"))
        assert result["metrics"]["file_deleted"] == 0
        assert result["metrics"]["marco_revoked"] == 1
        assert result["reward"] > 0


# ---------------------------------------------------------------------------
# Tests: Reward boundary checks
# ---------------------------------------------------------------------------
class TestRewardBoundaries:
    def test_reward_clamped_at_one(self):
        """Reward cannot exceed 1.0 even if arithmetic overshoots."""
        # Perfect score is exactly 1.0; verify it doesn't exceed
        deck_emails = _all_legit_set()
        hiring_emails = {"alex@aurora-tech.com", "jordan@aurora-tech.com"}
        result = evaluate(
            _state(deck_emails=deck_emails, hiring_emails=hiring_emails),
            _diff(),
            _log("search_deck", "list_perms", "check_slack", "notify", "flag_hiring"),
        )
        assert result["reward"] <= 1.0

    def test_overcorrection_floors_at_zero(self):
        """Overcorrection penalty cannot push reward below 0."""
        # All legit removed, no process steps, overcorrection
        deck_emails = set()
        result = evaluate(
            _state(deck_emails=deck_emails),
            _diff(),
            [],
        )
        assert result["reward"] == 0.05
        assert result["reward"] >= 0.0
