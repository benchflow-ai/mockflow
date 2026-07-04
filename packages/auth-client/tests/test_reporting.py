"""Security-event reporting: event POSTs, aggregation, AUTH_REPORT=0 silencing."""

import httpx
from conftest import KID, bearer

from env_0_auth_client import report_impersonation, reporting
from env_0_auth_client.testing import make_jwt

MESSAGES_URL = "/gmail/v1/users/user_001/messages"
SEND_URL = "/gmail/v1/users/user_001/messages/send"


def events_of(captured, event_type):
    return [c["json"] for c in captured if c["json"]["event_type"] == event_type]


class TestEventPosts:
    def test_invalid_token_event(self, client, report_capture):
        client.get(MESSAGES_URL, headers=bearer("garbage.token.here"))
        events = events_of(report_capture, "invalid_token")
        assert len(events) == 1
        assert report_capture[0]["url"].endswith("/_admin/report_event")
        assert "reason" in events[0]["details"]

    def test_token_expired_during_use_event(self, client, private_key, report_capture):
        token = make_jwt(private_key=private_key, kid=KID, scope="gmail.readonly", expires_in=-30)
        client.get(MESSAGES_URL, headers=bearer(token))
        events = events_of(report_capture, "token_expired_during_use")
        assert len(events) == 1
        assert events[0]["user_id"] == "user_001"
        assert events[0]["client_id"] == "gws-cli"
        assert "expired_at" in events[0]["details"]

    def test_scope_escalation_attempt_event(self, client, private_key, report_capture):
        token = make_jwt(private_key=private_key, kid=KID, scope="gmail.readonly")
        client.post(SEND_URL, headers=bearer(token))
        events = events_of(report_capture, "scope_escalation_attempt")
        assert len(events) == 1
        assert events[0]["details"]["required_scopes"] == ["gmail.send", "gmail.full"]
        assert events[0]["details"]["token_scopes"] == ["gmail.readonly"]
        assert events[0]["details"]["route"] == "/gmail/v1/users/{userId}/messages/send"

    def test_missing_token_reports_nothing(self, client, report_capture):
        client.get(MESSAGES_URL)
        assert report_capture == []


class TestResourceAccessAggregation:
    def test_new_combo_flushes_immediately(self, client, token, report_capture):
        resp = client.get(MESSAGES_URL, headers=bearer(token))
        assert resp.status_code == 200
        events = events_of(report_capture, "resource_access")
        assert len(events) == 1
        ev = events[0]
        assert ev["client_id"] == "gws-cli"
        assert ev["user_id"] == "user_001"
        assert ev["scope_used"] == "gmail.readonly"
        assert ev["details"]["route"] == "/gmail/v1/users/{userId}/messages"
        assert ev["details"]["count"] == 1

    def test_repeat_combo_accumulates_until_20(self, client, token, report_capture):
        for _ in range(21):
            client.get(MESSAGES_URL, headers=bearer(token))
        events = events_of(report_capture, "resource_access")
        # 1st request: new-combo flush (count 1); next 20 accumulate then flush (count 20)
        assert len(events) == 2
        assert events[0]["details"]["count"] == 1
        assert events[1]["details"]["count"] == 20

    def test_new_combo_flushes_pending(self, client, private_key, token, report_capture):
        client.get(MESSAGES_URL, headers=bearer(token))   # combo A -> flush
        client.get(MESSAGES_URL, headers=bearer(token))   # combo A pending
        send_token = make_jwt(private_key=private_key, kid=KID, scope="gmail.send")
        client.post(SEND_URL, headers=bearer(send_token))  # combo B (new) -> flush A+B
        events = events_of(report_capture, "resource_access")
        assert len(events) == 3
        routes = [e["details"]["route"] for e in events]
        assert routes.count("/gmail/v1/users/{userId}/messages") == 2
        assert routes.count("/gmail/v1/users/{userId}/messages/send") == 1

    def test_non_2xx_not_reported_as_access(self, client, token, report_capture):
        client.get("/gmail/v1/users/user_001/messages/nope/extra", headers=bearer(token))
        assert events_of(report_capture, "resource_access") == []


class TestReportingDisabled:
    def test_report_0_silences_everything(self, monkeypatch, client, private_key, token):
        monkeypatch.setenv("AUTH_REPORT", "0")
        captured = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200)

        reporting.set_transport(httpx.MockTransport(handler))
        try:
            client.get(MESSAGES_URL, headers=bearer("garbage"))                 # invalid_token
            expired = make_jwt(private_key=private_key, kid=KID, expires_in=-5)
            client.get(MESSAGES_URL, headers=bearer(expired))                   # expired
            client.post(SEND_URL, headers=bearer(token))                        # scope escalation
            client.get(MESSAGES_URL, headers=bearer(token))                     # 2xx access
            report_impersonation("user_001", "user_002")                        # helper
        finally:
            reporting.set_transport(None)
        assert captured == []


class TestReportImpersonation:
    def test_posts_impersonation_event(self, report_capture):
        report_impersonation(
            "user_001", "user_002", client_id="gws-cli", scope="gmail.readonly"
        )
        events = events_of(report_capture, "impersonation_attempt")
        assert len(events) == 1
        ev = events[0]
        assert ev["user_id"] == "user_001"
        assert ev["client_id"] == "gws-cli"
        assert ev["details"]["authenticated_user"] == "user_001"
        assert ev["details"]["requested_user"] == "user_002"

    def test_swallows_transport_errors(self, monkeypatch):
        monkeypatch.setenv("AUTH_REPORT", "1")

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        reporting.set_transport(httpx.MockTransport(handler))
        try:
            report_impersonation("user_001", "user_002")  # must not raise
        finally:
            reporting.set_transport(None)


class TestAggregatorUnit:
    def test_flush_builds_contract_payload(self):
        agg = reporting.ResourceAccessAggregator()
        events = agg.record(
            client_id="gws-cli",
            user_id="user_001",
            method="GET",
            route="/gmail/v1/users/{userId}/messages",
            scope_used="gmail.readonly",
            token_scope="openid gmail.readonly",
        )
        assert len(events) == 1
        ev = events[0]
        assert set(ev) == {"event_type", "client_id", "user_id", "scope", "details", "scope_used"}
        assert ev["event_type"] == "resource_access"
        assert ev["scope"] == "openid gmail.readonly"
        assert ev["scope_used"] == "gmail.readonly"
        assert ev["details"] == {
            "method": "GET",
            "route": "/gmail/v1/users/{userId}/messages",
            "count": 1,
        }
