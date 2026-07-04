"""Token endpoint — authorization_code (+PKCE), refresh_token (rotation + reuse
detection), client_credentials (+subject impersonation), and device_code grants.

Accepts form-encoded bodies only (like Google). All errors are RFC 6749 JSON.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from mock_auth.api.deps import authenticate_client, get_db
from mock_auth.api.errors import OAuthError
from mock_auth.audit import log_event, request_meta
from mock_auth.models import (
    AuthorizationCode,
    ConsentRecord,
    DeviceCode,
    OAuthClient,
    RefreshToken,
    User,
    utcnow_iso,
)
from mock_auth.scopes import parse_scope
from mock_auth.token_service import (
    access_token_ttl_for,
    issue_access_token,
    issue_id_token,
    issue_refresh_token,
)
from mock_auth.tokens import is_expired, pkce_verify, sha256_hex

router = APIRouter()

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


def _token_response(access_token: str, scope: str, expires_in: int,
                    refresh_token: str | None = None, id_token: str | None = None) -> dict:
    resp = {
        "access_token": access_token,
        "expires_in": expires_in,
        "scope": scope,
        "token_type": "Bearer",
    }
    if refresh_token:
        resp["refresh_token"] = refresh_token
    if id_token:
        resp["id_token"] = id_token
    return resp


def _touch_consent(db: Session, client_id: str, user_id: str):
    consent = db.query(ConsentRecord).filter(
        ConsentRecord.client_id == client_id,
        ConsentRecord.user_id == user_id,
        ConsentRecord.revoked_at.is_(None),
    ).first()
    if consent is not None:
        consent.last_used_at = utcnow_iso()


@router.post("/oauth2/token")
async def token_endpoint(request: Request, db: Session = Depends(get_db)):
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" not in content_type and "multipart/form-data" not in content_type:
        raise OAuthError(
            "invalid_request",
            "Token endpoint accepts application/x-www-form-urlencoded bodies only.",
            hint="Send grant_type and parameters as form fields, not JSON.",
        )
    form = await request.form()
    grant_type = form.get("grant_type")
    if not grant_type:
        raise OAuthError("invalid_request", "Missing required parameter: grant_type.",
                         hint="Supported: authorization_code, refresh_token, "
                              f"client_credentials, {DEVICE_GRANT}.")

    client = authenticate_client(request, db, form.get("client_id"), form.get("client_secret"))

    # The device grant gets no exemption: a client may only use grant types
    # explicitly listed in its registration (oauth_clients.grant_types).
    if grant_type not in client.grant_type_list:
        raise OAuthError(
            "unauthorized_client",
            f"Client {client.client_id!r} is not authorized for grant_type {grant_type!r}.",
            hint=f"Allowed grant types: {client.grant_type_list}",
        )

    if grant_type == "authorization_code":
        return _grant_authorization_code(request, db, client, form)
    if grant_type == "refresh_token":
        return _grant_refresh_token(request, db, client, form)
    if grant_type == "client_credentials":
        return _grant_client_credentials(request, db, client, form)
    if grant_type == DEVICE_GRANT:
        return _grant_device_code(request, db, client, form)

    raise OAuthError("unsupported_grant_type", f"Unsupported grant_type: {grant_type!r}.",
                     hint="Supported: authorization_code, refresh_token, "
                          f"client_credentials, {DEVICE_GRANT}.")


def _grant_authorization_code(request: Request, db: Session, client: OAuthClient, form):
    code_value = form.get("code")
    redirect_uri = form.get("redirect_uri")
    code_verifier = form.get("code_verifier")
    if not code_value:
        raise OAuthError("invalid_request", "Missing required parameter: code.",
                         hint="Pass the authorization code from the redirect.")

    code = db.query(AuthorizationCode).filter(AuthorizationCode.code == code_value).first()

    def _invalid(reason: str, hint: str):
        log_event(db, "invalid_token", client_id=client.client_id,
                  details={"reason": reason, "grant": "authorization_code"},
                  **request_meta(request))
        db.commit()
        raise OAuthError("invalid_grant", reason, hint=hint)

    if code is None:
        _invalid("Unknown authorization code.", "Codes are single-use and expire after 30s; "
                 "restart the authorization flow.")
    if code.client_id != client.client_id:
        _invalid("Authorization code was issued to a different client.",
                 "Use the same client_id that initiated the authorization request.")
    if code.used:
        _invalid("Authorization code has already been used.",
                 "Codes are single-use; restart the authorization flow.")
    if is_expired(code.expires_at):
        _invalid("Authorization code has expired (30s TTL).",
                 "Restart the authorization flow and exchange the code promptly.")
    if redirect_uri != code.redirect_uri:
        _invalid("redirect_uri does not match the authorization request.",
                 "Pass the exact redirect_uri used at the authorization endpoint.")

    if code.code_challenge:
        if not code_verifier or not pkce_verify(code_verifier, code.code_challenge,
                                                code.code_challenge_method):
            log_event(db, "pkce_failure", client_id=client.client_id, user_id=code.user_id,
                      scope=code.scope,
                      details={"method": code.code_challenge_method,
                               "verifier_present": bool(code_verifier)},
                      **request_meta(request))
            db.commit()
            raise OAuthError("invalid_grant", "PKCE verification failed.",
                             hint="code_verifier must match the code_challenge sent to the "
                                  "authorization endpoint (S256: base64url(sha256(verifier))).")
    elif client.client_type == "public":
        _invalid("Public clients must use PKCE.",
                 "Include code_challenge (S256) in the authorization request.")

    # Atomically burn the code (UPDATE ... WHERE used=0 succeeds at most once),
    # then commit immediately — a concurrent double-exchange of the same code
    # cannot both pass the in-memory `code.used` check above.
    claimed = db.query(AuthorizationCode).filter(
        AuthorizationCode.code == code_value,
        AuthorizationCode.used == False,  # noqa: E712
    ).update({"used": True}, synchronize_session=False)
    if not claimed:
        _invalid("Authorization code has already been used.",
                 "Codes are single-use; restart the authorization flow.")
    db.commit()
    code.used = True  # keep the ORM object in sync with the bulk UPDATE
    user = db.query(User).filter(User.id == code.user_id).first()
    scope = code.scope
    access_token, _ = issue_access_token(db, client, user, scope)
    refresh_raw = None
    if "refresh_token" in client.grant_type_list:
        refresh_raw, _ = issue_refresh_token(db, client, user, scope)
    id_token = None
    if "openid" in parse_scope(scope):
        id_token = issue_id_token(db, client, user, nonce=code.nonce)
    _touch_consent(db, client.client_id, user.id)
    log_event(db, "token_issued", client_id=client.client_id, user_id=user.id, scope=scope,
              details={"grant": "authorization_code", "refresh_token_issued": bool(refresh_raw),
                       "id_token_issued": bool(id_token)},
              **request_meta(request))
    db.commit()
    return _token_response(access_token, scope, access_token_ttl_for(client),
                           refresh_raw, id_token)


def _revoke_family(db: Session, family_id: str) -> int:
    rows = (db.query(RefreshToken).filter(RefreshToken.family_id == family_id)
            .populate_existing().all())
    n = 0
    for row in rows:
        if not row.revoked:
            row.revoked = True
            n += 1
    return n


def _refresh_reuse_detected(request: Request, db: Session, client: OAuthClient,
                            row: RefreshToken):
    """Reuse of a rotated/revoked refresh token => revoke the whole family."""
    revoked_count = _revoke_family(db, row.family_id)
    log_event(db, "token_revoked", client_id=client.client_id, user_id=row.user_id,
              scope=row.scope,
              details={"reason": "reuse_detected", "event_type": "refresh_reuse_detected",
                       "family_id": row.family_id, "tokens_revoked": revoked_count,
                       "was_rotated": row.replaced_by is not None},
              **request_meta(request))
    db.commit()
    raise OAuthError(
        "invalid_grant",
        "Refresh token reuse detected; the entire token family has been revoked.",
        hint="A rotated refresh token was presented again. Re-authorize from scratch.",
    )


def _grant_refresh_token(request: Request, db: Session, client: OAuthClient, form):
    raw = form.get("refresh_token")
    if not raw:
        raise OAuthError("invalid_request", "Missing required parameter: refresh_token.",
                         hint="Pass the opaque rt_... token from a previous token response.")

    row = db.query(RefreshToken).filter(RefreshToken.token_hash == sha256_hex(raw)).first()
    if row is None or row.client_id != client.client_id:
        log_event(db, "invalid_token", client_id=client.client_id,
                  details={"reason": "unknown refresh token", "grant": "refresh_token"},
                  **request_meta(request))
        db.commit()
        raise OAuthError("invalid_grant", "Unknown refresh token.",
                         hint="The token may have been revoked, rotated, or belongs to "
                              "another client.")

    if row.revoked:
        _refresh_reuse_detected(request, db, client, row)

    if is_expired(row.expires_at):
        log_event(db, "invalid_token", client_id=client.client_id, user_id=row.user_id,
                  details={"reason": "refresh token expired", "grant": "refresh_token"},
                  **request_meta(request))
        db.commit()
        raise OAuthError("invalid_grant", "Refresh token has expired.",
                         hint="Re-authorize to obtain a new refresh token.")

    # Optional down-scoping.
    scope = row.scope
    requested = parse_scope(form.get("scope"))
    if requested:
        granted = set(parse_scope(row.scope))
        excessive = [s for s in requested if s not in granted]
        if excessive:
            log_event(db, "scope_escalation_attempt", client_id=client.client_id,
                      user_id=row.user_id, scope=" ".join(requested),
                      details={"granted": sorted(granted), "excessive": excessive,
                               "stage": "refresh"},
                      **request_meta(request))
            db.commit()
            raise OAuthError("invalid_scope",
                             f"Requested scopes exceed the original grant: {' '.join(excessive)}.",
                             hint="Refresh can only narrow scopes, never broaden them.")
        scope = " ".join(requested)

    # Atomically claim (revoke) the presented token BEFORE minting successors:
    # under a concurrent double-refresh the UPDATE ... WHERE revoked=0 succeeds
    # for exactly one request; the loser lands in the reuse path and the whole
    # family is revoked.
    claimed = db.query(RefreshToken).filter(
        RefreshToken.token_hash == row.token_hash,
        RefreshToken.revoked == False,  # noqa: E712
    ).update({"revoked": True}, synchronize_session=False)
    if not claimed:
        _refresh_reuse_detected(request, db, client, row)
    db.commit()
    row.revoked = True  # keep the ORM object in sync with the bulk UPDATE

    user = db.query(User).filter(User.id == row.user_id).first()

    # Rotate: link successor (old token already revoked by the claim above).
    new_raw, new_row = issue_refresh_token(db, client, user, scope, family_id=row.family_id)
    row.replaced_by = new_row.token_hash

    access_token, _ = issue_access_token(db, client, user, scope)
    _touch_consent(db, client.client_id, user.id)
    log_event(db, "token_refreshed", client_id=client.client_id, user_id=user.id, scope=scope,
              details={"family_id": row.family_id}, **request_meta(request))
    db.commit()
    return _token_response(access_token, scope, access_token_ttl_for(client), new_raw)


def _grant_client_credentials(request: Request, db: Session, client: OAuthClient, form):
    if client.client_type == "public":
        raise OAuthError("unauthorized_client",
                         "Public clients cannot use the client_credentials grant.",
                         hint="Use a confidential client with a client_secret.")

    scopes = parse_scope(form.get("scope"))
    if not scopes:
        raise OAuthError("invalid_scope", "Missing or empty scope parameter.",
                         hint="client_credentials requires an explicit scope list.")
    allowed = set(client.allowed_scope_list)
    excessive = [s for s in scopes if s not in allowed]
    if excessive:
        log_event(db, "scope_escalation_attempt", client_id=client.client_id,
                  scope=" ".join(scopes),
                  details={"allowed": sorted(allowed), "excessive": excessive,
                           "stage": "client_credentials"},
                  **request_meta(request))
        db.commit()
        raise OAuthError("invalid_scope",
                         f"Client {client.client_id!r} is not allowed to request: "
                         f"{' '.join(excessive)}.",
                         hint=f"Allowed scopes: {sorted(allowed)}")

    scope = " ".join(scopes)
    subject = form.get("subject")
    user = None
    act = None
    if subject:
        # Domain-wide delegation: the service client impersonates a user.
        user = db.query(User).filter(
            ((User.id == subject) | (User.email == subject)),
            User.is_active == True,  # noqa: E712
        ).first()
        if user is None:
            log_event(db, "impersonation_attempt", client_id=client.client_id,
                      scope=scope, details={"subject": subject, "reason": "unknown subject"},
                      **request_meta(request))
            db.commit()
            raise OAuthError("invalid_grant", f"Unknown subject: {subject!r}.",
                             hint="subject must be an existing user id or email.")
        act = {"sub": client.client_id}

    access_token, _ = issue_access_token(db, client, user, scope, act=act)
    log_event(db, "token_issued", client_id=client.client_id,
              user_id=user.id if user else None, scope=scope,
              details={"grant": "client_credentials", "impersonated_subject": subject},
              **request_meta(request))
    db.commit()
    return _token_response(access_token, scope, access_token_ttl_for(client))


def _grant_device_code(request: Request, db: Session, client: OAuthClient, form):
    device_code = form.get("device_code")
    if not device_code:
        raise OAuthError("invalid_request", "Missing required parameter: device_code.",
                         hint="Pass the device_code from POST /oauth2/device/code.")

    row = db.query(DeviceCode).filter(DeviceCode.device_code == device_code).first()
    if row is None or row.client_id != client.client_id:
        raise OAuthError("invalid_grant", "Unknown device_code.",
                         hint="Start the flow at POST /oauth2/device/code.")

    if row.status == "pending":
        if is_expired(row.expires_at):
            row.status = "expired"
            db.commit()
            raise OAuthError("expired_token", "The device code has expired.",
                             hint="Request a new device code.")
        raise OAuthError("authorization_pending",
                         "The user has not yet approved this device.",
                         hint="Keep polling at the configured interval, or approve via "
                              "the verification page / POST /_admin/approve_device.")
    if row.status == "denied":
        raise OAuthError("access_denied", "The user denied this device authorization.",
                         hint="Do not retry; inform the operator.")
    if row.status in ("expired",) or is_expired(row.expires_at):
        row.status = "expired"
        db.commit()
        raise OAuthError("expired_token", "The device code has expired.",
                         hint="Request a new device code.")
    if row.status == "redeemed":
        raise OAuthError("invalid_grant", "This device code has already been redeemed.",
                         hint="Device codes are single-use.")

    # approved
    user = db.query(User).filter(User.id == row.user_id).first()
    if user is None:
        raise OAuthError("invalid_grant", "Approving user no longer exists.",
                         hint="Re-run the device flow.")
    scope = row.scope
    row.status = "redeemed"
    access_token, _ = issue_access_token(db, client, user, scope)
    refresh_raw = None
    if "refresh_token" in client.grant_type_list:
        refresh_raw, _ = issue_refresh_token(db, client, user, scope)
    id_token = None
    if "openid" in parse_scope(scope):
        id_token = issue_id_token(db, client, user)
    log_event(db, "token_issued", client_id=client.client_id, user_id=user.id, scope=scope,
              details={"grant": "device_code"}, **request_meta(request))
    db.commit()
    return _token_response(access_token, scope, access_token_ttl_for(client),
                           refresh_raw, id_token)
