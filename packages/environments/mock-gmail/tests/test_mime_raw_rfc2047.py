"""Cross-version regression guard for RFC 2047 non-ASCII handling in format=raw.

W5. ``messages.get?format=raw`` returns a urlsafe-base64 RFC 2822 message.
Non-ASCII Subjects and From/To **display names** must be RFC 2047-encoded so
that (a) the wire format is pure ASCII, (b) the encoded words round-trip back
to the original Unicode via ``decode_header``/``make_header``, and (c) export
never crashes.

The bug this pins is interpreter-specific and **does not reproduce on 3.12**:
flattening a compat32 MIME object with ``policy.SMTP`` auto-encodes short
non-ASCII headers on 3.12 but raises ``UnicodeEncodeError`` on 3.10/3.11. The
fix (``mime._encode_unstructured_header`` / ``_encode_address_header``) pre-
encodes non-ASCII headers up front. Run this module under EACH supported
interpreter (3.10/3.11/3.12) — the assertions below are the cross-version
guard, so a regression on the older stdlib fails the suite instead of 500ing
at runtime.
"""

from email import message_from_bytes, policy
from email.header import decode_header, make_header
from email.utils import parseaddr

import pytest

from mock_gmail.api.mime import base64url_decode, base64url_encode, build_rfc2822


# (display_name, addr_spec) split out so we can assert each independently.
SENDER_NAME = "Ülrike Müller"
SENDER_ADDR = "ulrike@example.com"
TO_NAME = "田中太郎"
TO_ADDR = "tanaka@example.com"
SUBJECT = "Budget review — 予算レビュー (Café)"
BODY = "Über alles — 詳細は添付をご覧ください。\nCafé costs rose 12%."


def _decode_word(value: str) -> str:
    """Round-trip an RFC 2047 header value back to Unicode (the stdlib idiom)."""
    return str(make_header(decode_header(value)))


def _insert_nonascii_message(client) -> str:
    """Insert (not send) a message carrying non-ASCII Subject + From/To display
    names + body, so the stored sender/to are NOT overwritten by the auth user.
    Returns the new message id."""
    raw_bytes = build_rfc2822(
        sender=f"{SENDER_NAME} <{SENDER_ADDR}>",
        to=f"{TO_NAME} <{TO_ADDR}>",
        subject=SUBJECT,
        body_plain=BODY,
    )
    resp = client.post(
        "/gmail/v1/users/me/messages",
        json={"raw": base64url_encode(raw_bytes), "labelIds": ["INBOX"]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


class TestFormatRawRfc2047CrossVersion:
    def test_export_returns_200(self, client):
        msg_id = _insert_nonascii_message(client)
        resp = client.get(
            f"/gmail/v1/users/me/messages/{msg_id}", params={"format": "raw"}
        )
        assert resp.status_code == 200, resp.text
        assert "raw" in resp.json()

    def test_header_lines_are_pure_ascii(self, client):
        """(c) No raw non-ASCII bytes may leak into the header block."""
        msg_id = _insert_nonascii_message(client)
        resp = client.get(
            f"/gmail/v1/users/me/messages/{msg_id}", params={"format": "raw"}
        )
        raw_bytes = base64url_decode(resp.json()["raw"])
        header_block = raw_bytes.split(b"\r\n\r\n", 1)[0]
        # Raises UnicodeDecodeError if any encoded word was left un-encoded.
        header_block.decode("ascii")
        assert b"=?utf-8?" in header_block.lower()

    def test_parses_as_valid_rfc2822(self, client):
        """(a) The decoded bytes parse as a structurally valid message."""
        msg_id = _insert_nonascii_message(client)
        resp = client.get(
            f"/gmail/v1/users/me/messages/{msg_id}", params={"format": "raw"}
        )
        raw_bytes = base64url_decode(resp.json()["raw"])
        msg = message_from_bytes(raw_bytes, policy=policy.default)
        assert msg.get_content_type() == "text/plain"
        assert msg["Subject"] is not None
        assert msg["From"] is not None
        body = msg.get_body(preferencelist=("plain",))
        assert body.get_content().rstrip("\n") == BODY.rstrip("\n")

    def test_subject_decode_header_round_trips(self, client):
        """(b) Subject decodes back to the original Unicode via decode_header."""
        msg_id = _insert_nonascii_message(client)
        resp = client.get(
            f"/gmail/v1/users/me/messages/{msg_id}", params={"format": "raw"}
        )
        raw_bytes = base64url_decode(resp.json()["raw"])
        # compat32 leaves headers RFC 2047-encoded so decode_header has work to do.
        raw_msg = message_from_bytes(raw_bytes, policy=policy.compat32)
        assert _decode_word(raw_msg["Subject"]) == SUBJECT

    def test_display_names_decode_header_round_trip(self, client):
        """(b) From/To display names decode back; addr-specs are preserved."""
        msg_id = _insert_nonascii_message(client)
        resp = client.get(
            f"/gmail/v1/users/me/messages/{msg_id}", params={"format": "raw"}
        )
        raw_bytes = base64url_decode(resp.json()["raw"])
        raw_msg = message_from_bytes(raw_bytes, policy=policy.compat32)

        from_name, from_addr = parseaddr(raw_msg["From"])
        assert _decode_word(from_name) == SENDER_NAME
        assert from_addr == SENDER_ADDR

        to_name, to_addr = parseaddr(raw_msg["To"])
        assert _decode_word(to_name) == TO_NAME
        assert to_addr == TO_ADDR


@pytest.mark.parametrize(
    "subject",
    [
        "Plain ASCII subject",
        "Budget review — final numbers",   # Latin-1 em-dash
        "会議の議題 — 予算レビュー",          # CJK
        "Reçu: naïve café façade",          # accented Latin
    ],
)
def test_subject_round_trip_matrix(subject):
    """Unit-level guard independent of the DB/endpoint: every Subject variant
    builds ASCII-safe header lines and round-trips via decode_header."""
    raw = build_rfc2822(
        sender="alice@example.com",
        to="bob@example.com",
        subject=subject,
        body_plain="hi",
    )
    header_block = raw.split(b"\r\n\r\n", 1)[0]
    header_block.decode("ascii")  # never leaks raw non-ASCII into headers
    raw_msg = message_from_bytes(raw, policy=policy.compat32)
    assert _decode_word(raw_msg["Subject"]) == subject
    if subject.isascii():
        # ASCII path stays byte-identical: no encoded words introduced.
        assert b"=?utf-8?" not in header_block.lower()
        assert f"Subject: {subject}".encode() in header_block
