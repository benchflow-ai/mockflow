"""Authorization endpoint: GET consent screen + POST consent decision callback."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from mock_auth.api.deps import get_db, get_web_user
from mock_auth.api.errors import OAuthError
from mock_auth.audit import log_event, request_meta
from mock_auth.config import AUTH_CODE_TTL
from mock_auth.models import (
    AuthorizationCode,
    ConsentRecord,
    OAuthClient,
    User,
    utcnow_iso,
)
from mock_auth.scopes import describe, parse_scope
from mock_auth.tokens import iso_in, new_auth_code

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "web" / "templates"))


def _redirect(redirect_uri: str, params: dict) -> RedirectResponse:
    clean = {k: v for k, v in params.items() if v is not None}
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{sep}{urlencode(clean)}", status_code=302)


def _load_client(db: Session, request: Request, client_id: str | None) -> OAuthClient:
    if not client_id:
        raise OAuthError("invalid_request", "Missing required parameter: client_id.",
                         hint="Pass client_id as a query parameter.")
    client = db.query(OAuthClient).filter(
        OAuthClient.client_id == client_id,
        OAuthClient.is_active == True,  # noqa: E712
    ).first()
    if client is None:
        log_event(db, "invalid_client", client_id=client_id,
                  details={"reason": "unknown client at authorization endpoint"},
                  **request_meta(request))
        db.commit()
        raise OAuthError("invalid_client", f"Unknown client: {client_id!r}.",
                         hint="Seed clients with `mock-auth seed` or check /_admin/state.")
    return client


def _check_redirect_uri(client: OAuthClient, redirect_uri: str | None) -> str:
    if not redirect_uri:
        raise OAuthError("invalid_request", "Missing required parameter: redirect_uri.",
                         hint="Pass redirect_uri matching one registered for the client.")
    if redirect_uri not in client.redirect_uri_list:
        raise OAuthError(
            "invalid_request",
            f"redirect_uri {redirect_uri!r} is not registered for client {client.client_id!r}.",
            hint=f"Registered redirect URIs: {client.redirect_uri_list}",
        )
    return redirect_uri


def _resolve_login_hint(db: Session, login_hint: str) -> User | None:
    return db.query(User).filter(
        ((User.email == login_hint) | (User.id == login_hint)),
        User.is_active == True,  # noqa: E712
    ).first()


def _find_consent(db: Session, client_id: str, user_id: str) -> ConsentRecord | None:
    return db.query(ConsentRecord).filter(
        ConsentRecord.client_id == client_id,
        ConsentRecord.user_id == user_id,
        ConsentRecord.revoked_at.is_(None),
    ).first()


def _consent_covers(consent: ConsentRecord | None, scopes: list[str]) -> bool:
    if consent is None:
        return False
    granted = set(parse_scope(consent.granted_scopes))
    return set(scopes).issubset(granted)


def _issue_code(
    db: Session,
    client: OAuthClient,
    user: User,
    redirect_uri: str,
    scopes: list[str],
    state: str | None,
    nonce: str | None,
    code_challenge: str | None,
    code_challenge_method: str | None,
) -> str:
    code = new_auth_code()
    db.add(AuthorizationCode(
        code=code,
        client_id=client.client_id,
        user_id=user.id,
        redirect_uri=redirect_uri,
        scope=" ".join(scopes),
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        nonce=nonce,
        state=state,
        expires_at=iso_in(AUTH_CODE_TTL),
    ))
    return code


@router.get("/o/oauth2/v2/auth")
def authorize(
    request: Request,
    client_id: str | None = Query(None),
    redirect_uri: str | None = Query(None),
    response_type: str | None = Query(None),
    scope: str | None = Query(None),
    state: str | None = Query(None),
    nonce: str | None = Query(None),
    code_challenge: str | None = Query(None),
    code_challenge_method: str | None = Query(None),
    login_hint: str | None = Query(None),
    db: Session = Depends(get_db),
):
    client = _load_client(db, request, client_id)
    redirect_uri = _check_redirect_uri(client, redirect_uri)

    if response_type != "code":
        return _redirect(redirect_uri, {
            "error": "unsupported_response_type",
            "error_description": "Only response_type=code is supported.",
            "state": state,
        })

    scopes = parse_scope(scope)
    if not scopes:
        return _redirect(redirect_uri, {
            "error": "invalid_scope",
            "error_description": "Missing or empty scope parameter.",
            "state": state,
        })

    allowed = set(client.allowed_scope_list)
    excessive = [s for s in scopes if s not in allowed]
    if excessive:
        log_event(db, "scope_escalation_attempt", client_id=client.client_id,
                  scope=" ".join(scopes),
                  details={"requested": scopes, "allowed": sorted(allowed),
                           "excessive": excessive, "stage": "authorization"},
                  **request_meta(request))
        db.commit()
        return _redirect(redirect_uri, {
            "error": "invalid_scope",
            "error_description": f"Client {client.client_id!r} is not allowed to request: "
                                 f"{' '.join(excessive)}.",
            "state": state,
        })

    if client.client_type == "public" and not code_challenge:
        return _redirect(redirect_uri, {
            "error": "invalid_request",
            "error_description": "code_challenge is required for public clients (PKCE).",
            "state": state,
        })

    # RFC 7636: only S256 and plain transforms are supported. An omitted
    # method with a challenge present defaults to plain; anything else is
    # rejected here (never silently downgraded at exchange time).
    if code_challenge and code_challenge_method not in (None, "", "plain", "S256"):
        return _redirect(redirect_uri, {
            "error": "invalid_request",
            "error_description": (
                f"Unsupported code_challenge_method {code_challenge_method!r}; "
                "supported: S256, plain."
            ),
            "state": state,
        })

    # --- Resolve the user ---
    session_user = get_web_user(request, db)
    hint_user = _resolve_login_hint(db, login_hint) if login_hint else None
    user = session_user or hint_user

    log_event(db, "authorization_request", client_id=client.client_id,
              user_id=user.id if user else None, scope=" ".join(scopes),
              details={"redirect_uri": redirect_uri, "pkce": bool(code_challenge),
                       "login_hint": login_hint},
              **request_meta(request))
    db.commit()

    if user is not None:
        consent = _find_consent(db, client.client_id, user.id)
        if _consent_covers(consent, scopes):
            # Auto-consent: skip HTML entirely and redirect with a code.
            code = _issue_code(db, client, user, redirect_uri, scopes, state, nonce,
                               code_challenge, code_challenge_method)
            consent.last_used_at = utcnow_iso()
            log_event(db, "authorization_grant", client_id=client.client_id,
                      user_id=user.id, scope=" ".join(scopes),
                      details={"auto_consent": True}, **request_meta(request))
            db.commit()
            return _redirect(redirect_uri, {"code": code, "state": state})

    if session_user is None:
        # No session. If an auto-consent record exists for this client, a login_hint
        # naming the user is REQUIRED — otherwise we cannot pick the account.
        has_any_consent = db.query(ConsentRecord).filter(
            ConsentRecord.client_id == client.client_id,
            ConsentRecord.revoked_at.is_(None),
        ).count() > 0
        if has_any_consent and not login_hint:
            return _redirect(redirect_uri, {
                "error": "interaction_required",
                "error_description": "No session and no login_hint; cannot select an account.",
                "state": state,
            })
        # Render the login form first (consent requires an authenticated session).
        return templates.TemplateResponse(request, "login.html", {
            "next_url": str(request.url),
            "prefill_email": (hint_user.email if hint_user else login_hint) or "",
            "error": None,
        })

    # Authenticated session without covering consent: render the consent screen.
    return templates.TemplateResponse(request, "consent.html", {
        "user": session_user,
        "client": client,
        "scopes": [{"name": s, "description": describe(s)} for s in scopes],
        "scope": " ".join(scopes),
        "redirect_uri": redirect_uri,
        "state": state or "",
        "nonce": nonce or "",
        "code_challenge": code_challenge or "",
        "code_challenge_method": code_challenge_method or "",
        "client_id": client.client_id,
    })


@router.post("/o/oauth2/v2/auth/callback")
def authorize_callback(
    request: Request,
    decision: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    scope: str = Form(...),
    state: str = Form(""),
    nonce: str = Form(""),
    code_challenge: str = Form(""),
    code_challenge_method: str = Form(""),
    db: Session = Depends(get_db),
):
    client = _load_client(db, request, client_id)
    redirect_uri = _check_redirect_uri(client, redirect_uri)
    scopes = parse_scope(scope)
    state = state or None
    nonce = nonce or None
    code_challenge = code_challenge or None
    code_challenge_method = code_challenge_method or None

    user = get_web_user(request, db)
    if user is None:
        raise OAuthError(
            "interaction_required",
            "No authenticated session; log in via POST /web/login first.",
            hint="The consent decision must come from a logged-in user "
                 "(session cookie mock_auth_session).",
        )

    if decision != "allow":
        log_event(db, "authorization_deny", client_id=client.client_id, user_id=user.id,
                  scope=" ".join(scopes), details={"decision": decision},
                  **request_meta(request))
        db.commit()
        return _redirect(redirect_uri, {"error": "access_denied", "state": state})

    # Upsert consent record (union of scopes).
    consent = db.query(ConsentRecord).filter(
        ConsentRecord.client_id == client.client_id,
        ConsentRecord.user_id == user.id,
    ).first()
    if consent is None:
        consent = ConsentRecord(user_id=user.id, client_id=client.client_id,
                                granted_scopes=" ".join(scopes))
        db.add(consent)
    else:
        merged = parse_scope(consent.granted_scopes + " " + " ".join(scopes))
        consent.granted_scopes = " ".join(merged)
        consent.revoked_at = None
    consent.last_used_at = utcnow_iso()

    log_event(db, "consent_granted", client_id=client.client_id, user_id=user.id,
              scope=" ".join(scopes), **request_meta(request))

    code = _issue_code(db, client, user, redirect_uri, scopes, state, nonce,
                       code_challenge, code_challenge_method)
    log_event(db, "authorization_grant", client_id=client.client_id, user_id=user.id,
              scope=" ".join(scopes), details={"auto_consent": False},
              **request_meta(request))
    db.commit()
    return _redirect(redirect_uri, {"code": code, "state": state})
