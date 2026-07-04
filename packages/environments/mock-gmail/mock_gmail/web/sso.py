"""Web-session SSO: model accounts.google.com's browser login hand-off.

When ``AUTH_ENABLED=1`` the human web UI (``/``, ``/thread/*``) is no
longer an open, first-user dashboard: a browser without an established gmail
web session is bounced into auth's login flow, exactly like hitting Gmail
while signed out bounces you to accounts.google.com.

The two services run on different origins (auth :9000, gmail :9001),
so auth's ``env_0_auth_session`` cookie is never sent to gmail -- a pure
cookie-share is impossible. Instead this is a redirect-with-identity-hand-off
(the OIDC id_token shape):

1.  gmail's :class:`GmailWebSessionMiddleware` 302s the browser to
    ``{AUTH_URL}/web/login?next=<gmail>/web/auth/callback?next=<orig>``.
2.  auth authenticates the user (sets its own session) and, because the
    ``next`` target is cross-origin, redirects back with a short-lived RS256
    *identity assertion* (``env_0_identity=<jwt>``) signed by its active signing
    key -- see ``env_0_auth.token_service.issue_identity_assertion``.
3.  gmail's ``GET /web/auth/callback`` verifies that assertion against
    auth's JWKS (the same keys the API Bearer middleware already trusts),
    resolves the local user, and sets the ``mock_gmail_user`` cookie -- the
    established gmail web session. Subsequent requests carry the cookie and
    sail past the middleware.

With ``AUTH_ENABLED`` off the middleware is never installed and the legacy
cookie / first-user behavior is byte-identical.
"""

from __future__ import annotations

from urllib.parse import urlencode

from sqlalchemy import func
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from mock_gmail.models import User, get_session_factory

#: The browser-session identity cookie (unchanged: the web routes already key
#: identity off it). The callback sets it to the authenticated local user id.
WEB_SESSION_COOKIE = "mock_gmail_user"

#: gmail-side endpoint auth redirects back to after authenticating.
CALLBACK_PATH = "/web/auth/callback"

#: Query param carrying auth's signed identity assertion to the callback.
ASSERTION_PARAM = "env_0_identity"

#: Human mailbox web routes that REQUIRE a session under auth. Everything else
#: root-mounted is either the API (``/gmail/v1``), infra/admin (``/_admin``,
#: ``/health``, ``/docs`` ...), dev tooling (``/dev``), or the login dance
#: itself (``/web``) -- all left open, mirroring the Bearer middleware's
#: exemptions. Kept an allowlist (not a denylist) so new infra routes can't be
#: accidentally gated.
_GATED_EXACT = frozenset({"/"})
_GATED_PREFIXES: tuple[str, ...] = ("/thread",)

#: Offline-test hook: a JWKS dict or zero-arg callable. When set, assertion
#: verification uses it instead of fetching ``{AUTH_URL}/oauth2/v3/certs``
#: over HTTP. Wired by ``mock_gmail.api.app._apply_auth`` from ``jwks_static``.
_JWKS_STATIC = None


def set_jwks_static(source) -> None:
    """Install (or clear, with ``None``) a static JWKS source for verification."""
    global _JWKS_STATIC
    _JWKS_STATIC = source


def _is_gated(path: str) -> bool:
    """True for the human mailbox web routes that require a session."""
    if path in _GATED_EXACT:
        return True
    for prefix in _GATED_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def _safe_next(next_path: str) -> str:
    """Clamp the post-login redirect to a same-site path (no open redirect)."""
    if next_path.startswith("/") and not next_path.startswith("//"):
        return next_path
    return "/"


def build_login_redirect(request: Request, original: str) -> str:
    """Build the ``{AUTH_URL}/web/login?next=<callback>`` redirect URL.

    The callback URL is absolute (derived from this request's base URL) so the
    browser lands back on gmail after authenticating; ``original`` is preserved
    through the round-trip so the user resumes where they started.
    """
    from env_0_auth_client import config as auth_config

    auth_url = auth_config.get_auth_url()
    base = str(request.base_url).rstrip("/")
    callback = f"{base}{CALLBACK_PATH}?" + urlencode({"next": original})
    return f"{auth_url}/web/login?" + urlencode({"next": callback})


def _original_target(request: Request) -> str:
    path = request.url.path
    if request.url.query:
        return f"{path}?{request.url.query}"
    return path


def _has_web_session(request: Request) -> bool:
    """True when the ``mock_gmail_user`` cookie resolves to a real local user."""
    user_id = request.cookies.get(WEB_SESSION_COOKIE, "")
    if not user_id:
        return False
    db = get_session_factory()()
    try:
        return db.query(User).filter(User.id == user_id).first() is not None
    finally:
        db.close()


async def verify_identity_assertion(token: str) -> dict | None:
    """Verify a auth web-SSO assertion JWT; return its claims or ``None``.

    Validates the RS256 signature against auth's JWKS, the issuer, the
    expiry, and the ``purpose=web_sso`` marker. Audience is intentionally not
    enforced (mock). Any failure returns ``None`` -- callers restart the login.
    """
    if not token:
        return None

    import jwt

    from env_0_auth_client import config as auth_config
    from env_0_auth_client.jwks import JWKSCache

    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError:
        return None
    kid = header.get("kid")
    if not kid:
        return None

    cache = (
        JWKSCache(static=_JWKS_STATIC)
        if _JWKS_STATIC is not None
        else JWKSCache(auth_base_url=auth_config.get_auth_url())
    )
    try:
        key = await cache.get_key(kid)
    except Exception:
        return None

    try:
        claims = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            issuer=auth_config.get_issuer(),
            options={"verify_aud": False, "require": ["exp", "iss"]},
        )
    except jwt.InvalidTokenError:
        return None

    if claims.get("purpose") != "web_sso":
        return None
    return claims


def resolve_assertion_user(db, claims: dict) -> User | None:
    """Map an assertion's identity to a local gmail user.

    Mirrors ``deps.resolve_user_id``: id == ``sub`` first, else
    ``email_address`` == the ``email`` claim (case-insensitive).
    """
    sub = claims.get("sub")
    user = None
    if sub:
        user = db.query(User).filter(User.id == sub).first()
    if user is None:
        email = (claims.get("email") or "").strip()
        if email:
            user = db.query(User).filter(
                func.lower(User.email_address) == email.lower()
            ).first()
    return user


class GmailWebSessionMiddleware(BaseHTTPMiddleware):
    """Bounce sessionless browsers on the mailbox web UI into auth login.

    Only installed when ``AUTH_ENABLED`` is truthy (see
    ``mock_gmail.api.app._apply_auth``). Gates only ``GET`` requests to the
    human mailbox routes (``/``, ``/thread/*``); the API, infra, dev tooling
    and the ``/web`` login-dance endpoints pass through untouched.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method != "GET" or not _is_gated(request.url.path):
            return await call_next(request)
        if _has_web_session(request):
            return await call_next(request)
        return RedirectResponse(
            build_login_redirect(request, _original_target(request)),
            status_code=302,
        )
