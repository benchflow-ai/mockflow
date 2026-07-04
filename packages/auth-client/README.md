# auth-client

Middleware library for `environment` resource servers (gmail, slack, ...) to
validate **auth** RS256 JWT access tokens, enforce per-route scopes, and
report security events back to auth. Pure library — no CLI, no server, no DB.

```python
from env_0_auth_client import (
    Env_0AuthMiddleware,   # Starlette BaseHTTPMiddleware enforcing Bearer JWTs
    is_auth_enabled,      # AUTH_ENABLED in ("1","true","yes"), case-insensitive
    ScopeMap,             # dict[tuple[str, str], list[str]]
    match_route,          # (app, asgi_scope) -> (METHOD, path_template) | None
    report_impersonation, # fire-and-forget impersonation_attempt event (deps layer)
)
```

## Integration (env maintainers)

1. Add `auth-client` to your package dependencies.
2. Define a per-env scope map, e.g. `env_0_gmail/auth_scopes.py`:

```python
from env_0_auth_client import ScopeMap

SCOPE_MAP: ScopeMap = {
    # (HTTP_METHOD, route path template EXACTLY as registered on the FastAPI app)
    ("GET",  "/gmail/v1/users/{userId}/messages"):      ["gmail.readonly", "gmail.modify", "gmail.full"],
    ("POST", "/gmail/v1/users/{userId}/messages/send"): ["gmail.send", "gmail.full"],
    # OR logic: ANY one listed scope grants access.
    # Routes absent from the map require a valid token but no particular scope.
}
```

3. In `server.py` (or wherever the app is assembled):

```python
from env_0_auth_client import Env_0AuthMiddleware, is_auth_enabled
from env_0_gmail.auth_scopes import SCOPE_MAP

if is_auth_enabled():
    app.add_middleware(Env_0AuthMiddleware, scope_map=SCOPE_MAP)
```

4. In your deps layer (`resolve_user_id`), honor the authenticated identity:

```python
from env_0_auth_client import report_impersonation
from env_0_auth_client.errors import impersonation_body

auth_user_id = getattr(request.state, "auth_user_id", None)
if auth_user_id is not None:
    if userId == "me":
        return auth_user_id
    if userId != auth_user_id:
        # The middleware cannot see path-vs-sub mismatches; report from here.
        report_impersonation(auth_user_id, userId,
                             client_id=getattr(request.state, "auth_client_id", None))
        # Respond 403 with EXACTLY impersonation_body(auth_user_id, userId) —
        # e.g. raise a dedicated exception whose handler returns
        # JSONResponse(status_code=403, content=impersonation_body(...)).
        raise ImpersonationError(auth_user_id, userId)
```

When `AUTH_ENABLED` is not set, nothing changes: the middleware is never
added and behavior stays byte-for-byte the existing header-based behavior.

### Scope vocabulary

`env_0_auth_client.scopes` carries the canonical scope names and human
descriptions for every env. Besides the Gmail/Calendar/Drive/Docs and Slack
families it includes the **Stripe** family, which models Stripe's
restricted-API-key permission system (each resource = none/read/write) as
OAuth scopes:

- per-resource `stripe.<res>.read` / `stripe.<res>.write` for `customers`,
  `payment_intents`, `charges`, `refunds`, `payment_methods`, `products`,
  `prices`, `webhook_endpoints` (write implies read for that resource);
- read-only resources `stripe.balance.read`,
  `stripe.balance_transactions.read`, `stripe.events.read`;
- convenience `stripe.read_only` (satisfies any `.read`) and `stripe.full`
  (satisfies everything).

The read/write/read_only/full implications are expressed by the OR-logic lists
in each env's `auth_scopes.py` (a read route lists both `.read` and `.write`),
not by `has_any_scope`. See `env_0_stripe/auth_scopes.py` for the full map.

## What the middleware does

- Skips exempt prefixes (default `/_admin`, `/health`, `/dev`, `/docs`,
  `/openapi.json`, `/web`) and all `OPTIONS` requests. Prefix matching is
  segment-boundary safe: `/docs` exempts `/docs` and `/docs/...` but NOT
  `/docsx`, and `//_admin` is not `/_admin`.
- Extracts the Bearer token; verifies the RS256 signature against the JWKS at
  `{AUTH_URL}/oauth2/v3/certs` (in-process cache, TTL `AUTH_JWKS_TTL`
  default 300s; on unknown `kid` it refetches once, then fails).
- Validates `iss` (default expected issuer = `AUTH_ISSUER` or the auth base
  URL) and `exp`. `aud` validation is OFF unless the `audience` parameter is set.
- Finds the matched route's path template via `match_route(app, scope)`
  (iterates `app.routes` using FastAPI's own `route.matches`), then applies the
  scope map with OR logic. A missing route key means auth-only.
- On success sets `request.state.auth_user_id` (= `sub`),
  `request.state.auth_email` (= the `email` claim, `""` when absent — deps
  layers use it to resolve a local user by email when the `sub` does not match
  any env-local user id), `request.state.auth_scopes` (list),
  `request.state.auth_client_id`, `request.state.auth_jti`,
  `request.state.auth_token_exp` (unix int).
- Optional revocation checking: `AUTH_INTROSPECT=1` POSTs to
  `{AUTH_URL}/oauth2/introspect` per request with a 10s cache (fail-open
  if the auth server is unreachable).

### Error responses

- **401** missing/invalid/expired token:
  `{"error": {"code": 401, "status": "UNAUTHENTICATED", "message", "hint"}}`
  plus `WWW-Authenticate: Bearer error="invalid_token", error_description="..."`.
  Expired tokens include the expiry time in the message and refresh
  instructions (`POST {AUTH_URL}/oauth2/token` with
  `grant_type=refresh_token`) in the hint.
- **403** insufficient scope:
  `{"error": {"code": 403, "status": "PERMISSION_DENIED", "message", "required_scopes": [...], "token_scopes": [...], "hint"}}`
- **403** impersonation (built by `errors.impersonation_body`, raised by the
  deps layer): `{"error": {..., "message": "Cannot access another user's resources", "authenticated_user", "requested_user"}}`

### Security-event reporting

Fire-and-forget POSTs to `{AUTH_URL}/_admin/report_event` (all failures
swallowed; entirely skipped when `AUTH_REPORT=0`):

| event_type | when |
|---|---|
| `invalid_token` | malformed token, bad signature, unknown kid, bad issuer/audience, revoked |
| `token_expired_during_use` | structurally valid token presented after `exp` |
| `scope_escalation_attempt` | valid token, insufficient scope for the route |
| `impersonation_attempt` | via `report_impersonation(...)` from the deps layer |
| `resource_access` | aggregated 2xx accesses — flushed on each new (client, user, route) combo or every 20 requests |

## Environment variables

| Var | Default | Meaning |
|---|---|---|
| `AUTH_ENABLED` | off | `"1"/"true"/"yes"` enables the middleware (checked by `is_auth_enabled()`) |
| `AUTH_URL` | `http://localhost:9000` | auth base URL (JWKS, introspection, reporting, refresh hints) |
| `AUTH_ISSUER` | = `AUTH_URL` | expected `iss` claim |
| `AUTH_INTROSPECT` | off | `1` = per-request revocation check via `/oauth2/introspect` (10s cache) |
| `AUTH_REPORT` | on | `0`/`false`/`no` disables ALL event reporting (tests use `0`) |
| `AUTH_JWKS_TTL` | `300` | JWKS cache TTL seconds |

## Testing utilities (no HTTP needed)

`env_0_auth_client.testing` lets resource-server test suites run fully offline:

```python
from env_0_auth_client import Env_0AuthMiddleware
from env_0_auth_client.testing import generate_test_keypair, jwks_for, make_jwt

private_key, public_key = generate_test_keypair()       # fresh RSA-2048 pair
jwks = jwks_for(public_key, kid="test-key-001")          # {"keys": [...]}

# jwks_static => the middleware never fetches keys over HTTP
app.add_middleware(Env_0AuthMiddleware, scope_map=SCOPE_MAP, jwks_static=jwks)

token = make_jwt(private_key=private_key, kid="test-key-001",
                 sub="user_001", client_id="gws-cli",
                 scope="openid email gmail.readonly",
                 expires_in=3600)                        # negative => expired token
client.get("/gmail/v1/users/me/messages",
           headers={"Authorization": f"Bearer {token}"})
```

- `jwks_static` also accepts a zero-arg **callable** returning a JWKS dict —
  swap its return value to exercise key rotation / unknown-kid refetch.
- Set `AUTH_REPORT=0` in test environments (or inject a stub transport via
  `env_0_auth_client.reporting.set_transport(httpx.MockTransport(handler))` to
  assert on emitted events).
- `make_jwt` mints tokens shaped exactly like auth's (`iss`, `sub`, `aud`,
  `exp`, `iat`, `jti` = `tok_` + 24 hex, `scope`, `email`, `client_id`).

## Running the tests

```bash
cd packages/auth-client
uv run pytest tests/ -q   # 90 tests
```
