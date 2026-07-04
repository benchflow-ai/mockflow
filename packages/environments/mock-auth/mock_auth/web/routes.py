"""Web UI: login form (sets the mock_auth_session cookie), home page, device verification."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from mock_auth.api.deps import check_password, get_db, get_web_user
from mock_auth.audit import log_event, request_meta
from mock_auth.models import ConsentRecord, DeviceCode, OAuthClient, User, utcnow_iso
from mock_auth.scopes import describe, parse_scope
from mock_auth.tokens import is_expired
from mock_auth.web.sessions import SESSION_COOKIE, create_session, delete_session

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _is_cross_origin(target: str, request: Request) -> bool:
    """True when ``target`` is an absolute URL on a different origin than this
    request -- i.e. a hand-off to another service (gmail's web UI), not one
    of auth's own relative/same-origin pages (consent, device, home)."""
    try:
        parsed = urlparse(target)
    except ValueError:
        return False
    if not parsed.scheme or not parsed.netloc:
        return False  # relative path -> same origin
    return parsed.netloc != request.url.netloc


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = get_web_user(request, db)
    users = db.query(User).order_by(User.id).all()
    if not users:
        return HTMLResponse("<h1>No users. Run <code>mock-auth seed</code></h1>")
    clients = db.query(OAuthClient).order_by(OAuthClient.client_id).all()
    return templates.TemplateResponse(request, "home.html", {
        "user": user, "users": users, "clients": clients,
    })


@router.get("/web/login", response_class=HTMLResponse)
def login_form(request: Request, next: str = Query("/")):
    return templates.TemplateResponse(request, "login.html", {
        "next_url": next, "prefill_email": "", "error": None,
    })


@router.post("/web/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(
        User.email == email,
        User.is_active == True,  # noqa: E712
    ).first()
    if user is None or not check_password(password, user.password_hash):
        log_event(db, "invalid_client", user_id=user.id if user else None,
                  details={"reason": "web login failed", "email": email},
                  **request_meta(request))
        db.commit()
        return templates.TemplateResponse(request, "login.html", {
            "next_url": next, "prefill_email": email,
            "error": "Invalid email or password.",
        }, status_code=401)

    sid = create_session(user.id)

    # Cross-service web SSO (W7): when redirecting back to ANOTHER origin's web
    # UI (e.g. gmail's /web/auth/callback), hand off the authenticated
    # identity as a short-lived signed assertion the target verifies against our
    # JWKS. Same-origin/relative `next` (consent, device, home) is untouched.
    target = next or "/"
    if _is_cross_origin(target, request):
        from mock_auth.token_service import issue_identity_assertion

        assertion = issue_identity_assertion(db, user)
        log_event(db, "web_sso_assertion_issued", user_id=user.id,
                  details={"audience": urlparse(target).netloc},
                  **request_meta(request))
        db.commit()
        sep = "&" if "?" in target else "?"
        target = f"{target}{sep}{urlencode({'env_0_identity': assertion})}"

    response = RedirectResponse(target, status_code=303)
    response.set_cookie(SESSION_COOKIE, sid, httponly=True)
    return response


@router.post("/web/logout")
def logout(request: Request):
    delete_session(request.cookies.get(SESSION_COOKIE))
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


# --- Device verification page (RFC 8628 user interaction) ---

@router.get("/device", response_class=HTMLResponse)
def device_page(request: Request, user_code: str = Query(""), db: Session = Depends(get_db)):
    user = get_web_user(request, db)
    if user is None:
        return templates.TemplateResponse(request, "login.html", {
            "next_url": str(request.url), "prefill_email": "", "error": None,
        })

    row = None
    client = None
    error = None
    if user_code:
        row = db.query(DeviceCode).filter(DeviceCode.user_code == user_code).first()
        if row is None:
            error = f"Unknown code: {user_code}"
        elif row.status != "pending":
            error = f"This code is {row.status}."
        elif is_expired(row.expires_at):
            error = "This code has expired."
        else:
            client = db.query(OAuthClient).filter(
                OAuthClient.client_id == row.client_id).first()

    return templates.TemplateResponse(request, "device_approve.html", {
        "user": user,
        "user_code": user_code,
        "device": row if (row and not error) else None,
        "client": client,
        "scopes": ([{"name": s, "description": describe(s)}
                    for s in parse_scope(row.scope)] if row and not error else []),
        "error": error,
    })


@router.post("/device/decision")
def device_decision(
    request: Request,
    user_code: str = Form(...),
    decision: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_web_user(request, db)
    if user is None:
        return RedirectResponse(f"/device?user_code={user_code}", status_code=303)

    row = db.query(DeviceCode).filter(DeviceCode.user_code == user_code).first()
    if row is None or row.status != "pending" or is_expired(row.expires_at):
        return RedirectResponse(f"/device?user_code={user_code}", status_code=303)

    if decision == "allow":
        row.status = "approved"
        row.user_id = user.id
        # Approval implies consent for the requested scopes.
        consent = db.query(ConsentRecord).filter(
            ConsentRecord.user_id == user.id,
            ConsentRecord.client_id == row.client_id,
        ).first()
        if consent is None:
            db.add(ConsentRecord(user_id=user.id, client_id=row.client_id,
                                 granted_scopes=row.scope,
                                 last_used_at=utcnow_iso()))
        else:
            merged = parse_scope(consent.granted_scopes + " " + row.scope)
            consent.granted_scopes = " ".join(merged)
            consent.revoked_at = None
            consent.last_used_at = utcnow_iso()
        log_event(db, "device_code_approved", client_id=row.client_id, user_id=user.id,
                  scope=row.scope, details={"user_code": user_code, "via": "web"},
                  **request_meta(request))
        log_event(db, "consent_granted", client_id=row.client_id, user_id=user.id,
                  scope=row.scope, details={"via": "device_flow"},
                  **request_meta(request))
    else:
        row.status = "denied"
        log_event(db, "device_code_denied", client_id=row.client_id, user_id=user.id,
                  scope=row.scope, details={"user_code": user_code, "via": "web"},
                  **request_meta(request))
    db.commit()
    return RedirectResponse(f"/device?user_code={user_code}", status_code=303)
