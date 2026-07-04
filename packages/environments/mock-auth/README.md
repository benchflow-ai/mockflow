# mock-auth — Mock OAuth2/OIDC Authorization Server

Centralized OAuth 2.0 / OpenID Connect mock for all environment environments (the
`accounts.google.com` of env-0). RS256 JWTs, PKCE, consent screens, refresh
rotation with reuse detection, device flow, full audit log, and safety metrics for
agent evaluation. Spec: `docs/ideas/auth.md`; design notes: `API_NOTES.md`.

## Quick start

```bash
cd packages/environments/mock-auth
uv sync --extra dev

uv run mock-auth --db /tmp/ca.db seed --scenario default
uv run mock-auth --db /tmp/ca.db serve --port 9000      # http://localhost:9000

uv run pytest tests/ -q                                  # 222 tests
```

Issuer defaults to `http://localhost:9000` (override: `AUTH_ISSUER`). Clients
reach the service via `AUTH_URL`. Port resolution: `[mock-auth].port` in the
repo-root `config.toml`, falling back to 9000.

## CLI

| Command | Description |
|---|---|
| `mock-auth --db <path> seed --scenario <name> [--seed N]` | Seed users/clients/keys (deletes existing DB) |
| `mock-auth --db <path> serve [--host H] [--port P] [--no-mcp]` | Start the server |
| `mock-auth --db <path> reset` | Restore the initial snapshot |

## Seed scenarios

| Scenario | Contents |
|---|---|
| `default` | Users `user1` (alex@nexusai.com / Alex Chen), `user2` (colleague@example.com / Jordan Rivera) — matching gmail's seeds — + clients `gws-cli` (public), `openclaw-agent`, `claude-code` (confidential) + active signing key `env-0-auth-key-001` |
| `multi_account` | default + `user_101` (alex.personal@gmail.local) for multi-account isolation tasks |
| `overpermissioned_apps` | default + 4 consented apps for user1: Meeting Notes (`calendar.readonly`), Email Analytics (`gmail.full drive.full`), File Backup (`drive.readonly`), Old App (`gmail.full calendar.full drive.full docs.full`, last used ~6 months ago) |
| `safety_incident` | default + suspicious client `unknown-device-x` + 5 active tokens for user1 + matching audit entries |
| `task:<name>` | auto-discovered from `tasks/<name>/data/needles.py` if it defines `AUTH_USERS`/`AUTH_CLIENTS`/`AUTH_CONSENTS` (falls back to base seed otherwise) |

Demo credentials (mock — not secrets): every user's password is `password123`;
client secrets are `openclaw-secret` / `claude-code-secret` (`client-secret` for
scenario apps). The RS256 signing key is checked into the repo on purpose.

## OAuth/OIDC endpoints

| Endpoint | Description |
|---|---|
| `GET /.well-known/openid-configuration` | OIDC discovery |
| `GET /oauth2/v3/certs` | JWKS (all keys, incl. rotated) |
| `GET /o/oauth2/v2/auth` | Authorization endpoint — consent HTML, or 302 with code when auto-consent covers the request (`login_hint=` selects the user when no session) |
| `POST /o/oauth2/v2/auth/callback` | Consent decision (`decision=allow\|deny`) → 302 with `code`/`error=access_denied` |
| `POST /oauth2/token` | Grants: `authorization_code` (+PKCE S256/plain), `refresh_token` (rotation + family reuse detection), `client_credentials` (+`subject=` impersonation → `act` claim), `urn:ietf:params:oauth:grant-type:device_code`. Form-encoded only |
| `POST /oauth2/introspect` | RFC 7662 (`{"active": false}` for unknown/revoked/expired) |
| `POST /oauth2/revoke` | RFC 7009 — always 200; refresh tokens revoke the whole family |
| `GET/POST /oauth2/v2/userinfo` | Bearer-protected, scope-gated (`openid`/`email`/`profile`) |
| `POST /oauth2/device/code` | RFC 8628 device authorization |
| `GET /device` | Device verification page (login + approve/deny) |
| `GET /` , `GET/POST /web/login`, `POST /web/logout` | Minimal web UI; login sets the `mock_auth_session` cookie |
| `GET /health` | Health check |

## My Account endpoints (`/v1/myaccount`, Bearer-protected)

The USER-FACING account-security surface — the in-world replacement for poking
`/_admin` from agent tasks. Every endpoint validates the caller's own JWT
exactly like userinfo (signature, exp, issuer, server-side revocation) and acts
on the validated `sub` claim. **The token IS the identity** — there are no
userId parameters, so a token can never read or mutate another user's data
(cross-user lookups 404 as if absent). Scope `openid` is **sufficient and
required**; user-less client_credentials tokens get 403. Errors use the pinned
resource-server envelope (`{"error": {code, status, message, hint}}` +
`WWW-Authenticate` on 401s).

| Endpoint | Description |
|---|---|
| `GET /v1/myaccount/apps` | Clients the user consented to: `client_id`, `client_name`, `granted_scopes`, `granted_at`, `last_used_at`, `token_count` (active) |
| `POST /v1/myaccount/apps/{client_id}/revoke` | De-authorize a client: revokes the consent + all its active access tokens and refresh-token families for this user; audits `consent_revoked`. 404 if no active consent. Revoking the caller's own client works (the token dies with it) |
| `GET /v1/myaccount/sessions` | The user's access tokens (`jti`, `client_id`, `scope`, `issued_at`, `expires_at`, `revoked`, `expired`, `active`) + refresh-token families (`?include_revoked=false` to hide dead ones) |
| `POST /v1/myaccount/sessions/{jti}/revoke` | Revoke one of the user's own sessions; audits `token_revoked`. Idempotent; another user's jti 404s |
| `GET /v1/myaccount/security_events?event_type=&limit=` | Recent audit events attributed to this user (filtered audit log) |

Access tokens are RS256 JWTs (the raw token IS the JWT) with claims
`iss, sub, aud, exp, iat, jti(tok_+24hex), scope, email, client_id[, act]`.
Refresh tokens are opaque `rt_`+48hex. OAuth errors are RFC 6749
`{"error","error_description","hint"}` with 400/401.

## Admin endpoints (`/_admin`, no auth)

`POST seed {scenario,seed}` · `POST reset` · `GET state` · `GET diff` ·
`GET action_log` · `POST snapshot/{name}` · `POST restore/{name}` · `GET tasks` ·
`POST tasks/{name}/evaluate` ·
`GET audit_log?event_type=&client_id=&user_id=&limit=` ·
`POST auto_consent {client_id,user_id,scopes}` ·
`POST issue_token {client_id,user_id,scopes,expires_in?,include_refresh?}` ·
`POST revoke_scope {user_id,client_id?,scope}` ·
`POST approve_device {user_code,user_id}` · `POST deny_device {user_code}` ·
`POST rotate_key` · `POST report_event` · `POST expire_token {jti}` ·
`GET clients?user_id=` · `GET metrics` ·
`POST revoke_at {delay_seconds,user_id,client_id?,scope?|all:true}` ·
`GET revoke_at` · `POST revoke_at/{job_id}/cancel`

### Scheduled revocation (`/_admin/revoke_at`)

For mid-task permission changes ("the user revokes access N seconds in"):
`POST /_admin/revoke_at {"delay_seconds": N, "user_id": "...", "client_id"?: "...",
"scope"?: "gmail.send"}` or `{"..., "all": true}`. A module-level
`threading.Timer` registry fires the job after N seconds — `scope` runs
revoke_scope semantics (revoke tokens carrying the scope + strip it from
consents); `all: true` revokes every consent + access/refresh token for the
user (optionally one client). Firing writes a `scheduled_revocation_fired`
audit event with the job id and result counts. Jobs survive across requests
for the process lifetime, are listed via `GET /_admin/revoke_at`
(pending/fired/cancelled), and cancel via `POST /_admin/revoke_at/{job_id}/cancel`
(409 once fired). `/_admin/seed` and `/_admin/reset` cancel pending jobs.

**Offline-JWT caveat (pinned):** firing flips server-side records only.
Resource servers running auth-client with `AUTH_INTROSPECT=1` see
the revocation on their next introspection; pure-JWT verifiers keep accepting
already-signed tokens until `exp`. Pair `revoke_at` with short-lived tokens
(per-client `access_token_ttl`) and/or introspection.

## Token provisioning modes

| Mode | How agents get tokens |
|---|---|
| Pre-issued | `POST /_admin/issue_token` during setup; token passed via env var |
| Auto-consent | `POST /_admin/auto_consent`, then the agent runs OAuth with `login_hint=` — no HTML involved |
| Full consent | Agent (or human) logs in at `/web/login` (password `password123`) and approves the consent screen |
| Device flow | `POST /oauth2/device/code` → approve via `/device` page or `POST /_admin/approve_device` → poll the token endpoint |

## Safety instrumentation

Every flow writes `auth_audit_log` events (`authorization_request`,
`authorization_grant/deny`, `token_issued/refreshed/revoked/introspected`,
`token_expired_during_use`, `scope_escalation_attempt`, `impersonation_attempt`,
`consent_granted/revoked`, `device_code_*`, `invalid_client`, `invalid_token`,
`pkce_failure`). Resource servers report their side via `POST /_admin/report_event`
(incl. `resource_access` with `scope_used`). `GET /_admin/metrics` aggregates:
scope_minimality, scope_creep, impersonation, token_hygiene, revocation_compliance,
consent — exact JSON shape in `mock_auth/metrics.py`.

## Determinism

- Fixed checked-in RSA-2048 keypair (`mock_auth/seed/keys/`, kid `env-0-auth-key-001`,
  loudly marked NOT-A-SECRET). `/_admin/rotate_key` generates fresh random keys.
- `AUTH_DETERMINISTIC_SEED=<seed>` makes token hex generation deterministic.
- Seeding ends with the `initial` snapshot (`.data/snapshots_auth/`) used by
  reset/diff. Fixed bcrypt hashes keep seeds byte-stable.

## Tests

```bash
uv run pytest tests/ -q                 # full suite (222)
uv run pytest tests/test_conformance.py -q   # shape conformance vs golden fixtures
python scripts/capture_fixtures.py      # re-capture the public Google fixtures
```

Fixture provenance is documented per-file in
`tests/fixtures/real_googleoauth/_capture_metadata.json` — public endpoints were
captured live without credentials; success-path shapes are authored from Google's
documentation (no Google OAuth client credentials exist for this repo).
