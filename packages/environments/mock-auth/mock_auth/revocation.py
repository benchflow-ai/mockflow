"""Shared revocation primitives.

Used by `/_admin/revoke_scope`, `/_admin/revoke_at` (scheduled revocation), and
the user-facing `/v1/myaccount` surface. Callers commit; every mutation writes
audit events.

Pinned caveat (applies to ALL of these): revocation flips the server-side
records only — already-signed JWTs remain valid to *offline* verifiers until
their `exp`. Introspection (and auth's own Bearer-protected endpoints)
reflect revocation immediately; resource servers must run with
`AUTH_INTROSPECT=1` (auth-client) to observe it before expiry.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from mock_auth.audit import log_event
from mock_auth.models import AccessToken, ConsentRecord, RefreshToken, utcnow_iso
from mock_auth.scopes import parse_scope


def revoke_scope_for(db: Session, user_id: str, scope: str,
                     client_id: str | None = None) -> dict:
    """Strip one scope: revoke active access tokens carrying it and remove it
    from consent records. Returns counts (caller commits)."""
    q = db.query(AccessToken).filter(
        AccessToken.user_id == user_id,
        AccessToken.revoked == False,  # noqa: E712
    )
    if client_id:
        q = q.filter(AccessToken.client_id == client_id)
    revoked = 0
    for row in q.all():
        if scope in parse_scope(row.scope):
            row.revoked = True
            revoked += 1
            log_event(db, "token_revoked", client_id=row.client_id, user_id=row.user_id,
                      scope=row.scope,
                      details={"reason": "scope_revoked", "revoked_scope": scope,
                               "jti": row.jti})

    cq = db.query(ConsentRecord).filter(ConsentRecord.user_id == user_id)
    if client_id:
        cq = cq.filter(ConsentRecord.client_id == client_id)
    updated_consents = 0
    for consent in cq.all():
        scopes = parse_scope(consent.granted_scopes)
        if scope in scopes:
            scopes.remove(scope)
            consent.granted_scopes = " ".join(scopes)
            updated_consents += 1
            log_event(db, "consent_revoked", client_id=consent.client_id,
                      user_id=consent.user_id, scope=scope,
                      details={"partial": True, "remaining_scopes": scopes})
    return {"revoked_tokens": revoked, "updated_consents": updated_consents}


def revoke_tokens_for(db: Session, user_id: str, client_id: str | None = None,
                      *, reason: str = "user_revoked") -> dict:
    """Revoke ALL active access tokens and refresh-token families for a user
    (optionally restricted to one client). Returns counts (caller commits)."""
    q = db.query(AccessToken).filter(
        AccessToken.user_id == user_id,
        AccessToken.revoked == False,  # noqa: E712
    )
    if client_id:
        q = q.filter(AccessToken.client_id == client_id)
    revoked_access = 0
    for row in q.all():
        row.revoked = True
        revoked_access += 1
        log_event(db, "token_revoked", client_id=row.client_id, user_id=row.user_id,
                  scope=row.scope,
                  details={"reason": reason, "token_type": "access_token",
                           "jti": row.jti})

    rq = db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked == False,  # noqa: E712
    )
    if client_id:
        rq = rq.filter(RefreshToken.client_id == client_id)
    revoked_refresh = 0
    families_logged: set[str] = set()
    for row in rq.all():
        # Family revocation: every member of each rotation family for this
        # (user, client) is matched by the query above; one audit event per family.
        row.revoked = True
        revoked_refresh += 1
        if row.family_id not in families_logged:
            families_logged.add(row.family_id)
            log_event(db, "token_revoked", client_id=row.client_id, user_id=row.user_id,
                      scope=row.scope,
                      details={"reason": reason, "token_type": "refresh_token",
                               "family_id": row.family_id})
    return {"revoked_access_tokens": revoked_access,
            "revoked_refresh_tokens": revoked_refresh}


def revoke_client_consent(db: Session, user_id: str, client_id: str,
                          *, via: str = "myaccount") -> dict:
    """Fully de-authorize a client for a user: mark the consent revoked and
    revoke all of the client's active tokens for the user (family revocation).

    Returns None-equivalent {"consent_revoked": False, ...} if there is no
    active consent (caller decides the error shape). Caller commits.
    """
    consent = db.query(ConsentRecord).filter(
        ConsentRecord.user_id == user_id,
        ConsentRecord.client_id == client_id,
        ConsentRecord.revoked_at.is_(None),
    ).first()
    if consent is None:
        return {"consent_revoked": False,
                "revoked_access_tokens": 0, "revoked_refresh_tokens": 0}

    revoked_scopes = parse_scope(consent.granted_scopes)
    consent.revoked_at = utcnow_iso()
    counts = revoke_tokens_for(db, user_id, client_id, reason="consent_revoked")
    log_event(db, "consent_revoked", client_id=client_id, user_id=user_id,
              scope=" ".join(revoked_scopes),
              details={"partial": False, "via": via,
                       "revoked_scopes": revoked_scopes, **counts})
    return {"consent_revoked": True, **counts}


def revoke_all_for(db: Session, user_id: str, client_id: str | None = None,
                   *, via: str = "scheduled_revocation") -> dict:
    """Nuclear option: revoke every active consent + token for a user
    (optionally one client). Used by /_admin/revoke_at with all=true."""
    cq = db.query(ConsentRecord).filter(
        ConsentRecord.user_id == user_id,
        ConsentRecord.revoked_at.is_(None),
    )
    if client_id:
        cq = cq.filter(ConsentRecord.client_id == client_id)
    consents_revoked = 0
    for consent in cq.all():
        revoked_scopes = parse_scope(consent.granted_scopes)
        consent.revoked_at = utcnow_iso()
        consents_revoked += 1
        log_event(db, "consent_revoked", client_id=consent.client_id, user_id=user_id,
                  scope=" ".join(revoked_scopes),
                  details={"partial": False, "via": via,
                           "revoked_scopes": revoked_scopes})
    counts = revoke_tokens_for(db, user_id, client_id, reason=via)
    return {"consents_revoked": consents_revoked, **counts}
