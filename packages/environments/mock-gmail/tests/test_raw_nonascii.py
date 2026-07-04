"""Regression tests for non-ASCII headers/bodies in format=raw export.

Previously ``build_rfc2822`` flattened compat32 MIME objects with
``policy.SMTP`` without pre-encoding headers; on Python < 3.12 a short
non-ASCII header (e.g. an em-dash Subject) raised UnicodeEncodeError and
``messages.get?format=raw`` returned a 500. Headers are now RFC 2047-encoded
so raw export round-trips UTF-8 subjects and bodies on all supported Pythons.
"""

from email import message_from_bytes, policy

from mock_gmail.api.mime import (
    base64url_decode,
    base64url_encode,
    build_rfc2822,
    parse_rfc2822,
)

EMDASH_SUBJECT = "Budget review — final numbers"
CJK_SUBJECT = "会議の議題 — 予算レビュー"
UTF8_BODY = "Café costs rose by 12% — 詳細は添付をご覧ください。\nÜber alles."


class TestBuildRfc2822NonAscii:
    def test_emdash_subject_builds_ascii_bytes(self):
        raw = build_rfc2822(
            sender="alice@example.com",
            to="bob@example.com",
            subject=EMDASH_SUBJECT,
            body_plain="hi",
        )
        # RFC 2822 wire format must be pure ASCII (RFC 2047 encoded words)
        raw.decode("ascii")
        assert b"=?utf-8?" in raw.lower()

    def test_emdash_subject_round_trips(self):
        raw = build_rfc2822(
            sender="alice@example.com",
            to="bob@example.com",
            subject=EMDASH_SUBJECT,
            body_plain="hi",
        )
        parsed = parse_rfc2822(raw)
        assert parsed["subject"] == EMDASH_SUBJECT

    def test_cjk_subject_and_utf8_body_round_trip(self):
        raw = build_rfc2822(
            sender="alice@example.com",
            to="bob@example.com",
            subject=CJK_SUBJECT,
            body_plain=UTF8_BODY,
            body_html="<p>" + UTF8_BODY + "</p>",
        )
        raw.decode("ascii")
        parsed = parse_rfc2822(raw)
        assert parsed["subject"] == CJK_SUBJECT
        assert parsed["body_plain"] == UTF8_BODY
        assert parsed["body_html"] == "<p>" + UTF8_BODY + "</p>"

    def test_nonascii_display_names_round_trip(self):
        raw = build_rfc2822(
            sender="Ülrike Müller <ulrike@example.com>",
            to="José García <jose@example.com>",
            cc="田中太郎 <tanaka@example.com>",
            subject="hello",
            body_plain="hi",
        )
        raw.decode("ascii")
        parsed = parse_rfc2822(raw)
        # Display names decode back; addr-specs are preserved verbatim
        assert "ulrike@example.com" in parsed["sender"]
        assert "Ülrike Müller" in parsed["sender"]
        assert "jose@example.com" in parsed["to"]
        assert "José García" in parsed["to"]
        assert "田中太郎" in parsed["cc"]

    def test_ascii_headers_unchanged(self):
        """Pure-ASCII messages keep their exact legacy header serialization."""
        raw = build_rfc2822(
            sender="alice@example.com",
            to="bob@example.com",
            subject="Plain ASCII subject",
            body_plain="hi",
        )
        assert b"Subject: Plain ASCII subject" in raw
        assert b"From: alice@example.com" in raw
        assert b"=?utf-8?" not in raw.lower()


class TestRawEndpointNonAscii:
    def _send_utf8_message(self, client) -> str:
        """Upload a UTF-8 message via messages.send (raw) and return its id."""
        raw_bytes = build_rfc2822(
            sender="alex@nexusai.com",
            to="someone@example.com",
            subject=EMDASH_SUBJECT,
            body_plain=UTF8_BODY,
        )
        resp = client.post(
            "/gmail/v1/users/me/messages/send",
            json={"raw": base64url_encode(raw_bytes)},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["id"]

    def test_format_raw_returns_200_for_emdash_subject(self, client):
        msg_id = self._send_utf8_message(client)
        resp = client.get(
            f"/gmail/v1/users/me/messages/{msg_id}", params={"format": "raw"}
        )
        assert resp.status_code == 200, resp.text
        assert "raw" in resp.json()

    def test_format_raw_base64url_decodes_and_round_trips_utf8(self, client):
        msg_id = self._send_utf8_message(client)
        resp = client.get(
            f"/gmail/v1/users/me/messages/{msg_id}", params={"format": "raw"}
        )
        assert resp.status_code == 200, resp.text

        raw_bytes = base64url_decode(resp.json()["raw"])
        raw_bytes.decode("ascii")  # wire format is ASCII-safe
        msg = message_from_bytes(raw_bytes, policy=policy.default)
        assert str(msg["Subject"]) == EMDASH_SUBJECT
        body = msg.get_body(preferencelist=("plain",))
        assert body.get_content().rstrip("\n") == UTF8_BODY.rstrip("\n")

    def test_format_raw_cjk_subject(self, client):
        raw_bytes = build_rfc2822(
            sender="alex@nexusai.com",
            to="someone@example.com",
            subject=CJK_SUBJECT,
            body_plain="本文です。",
        )
        resp = client.post(
            "/gmail/v1/users/me/messages/send",
            json={"raw": base64url_encode(raw_bytes)},
        )
        assert resp.status_code == 200, resp.text
        msg_id = resp.json()["id"]

        resp = client.get(
            f"/gmail/v1/users/me/messages/{msg_id}", params={"format": "raw"}
        )
        assert resp.status_code == 200, resp.text
        decoded = message_from_bytes(
            base64url_decode(resp.json()["raw"]), policy=policy.default
        )
        assert str(decoded["Subject"]) == CJK_SUBJECT
