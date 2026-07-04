# auth API Notes

## Ground Truth

- OAuth 2.0 / OIDC behavior modeled on Google's auth surface:
  - Discovery: https://accounts.google.com/.well-known/openid-configuration (live-captured)
  - JWKS: https://www.googleapis.com/oauth2/v3/certs (live-captured)
  - Web-server flow: https://developers.google.com/identity/protocols/oauth2/web-server
  - OIDC: https://developers.google.com/identity/openid-connect/openid-connect
  - Device flow: https://developers.google.com/identity/protocols/oauth2/limited-input-device
- RFCs implemented: 6749 (OAuth2), 7636 (PKCE), 7662 (introspection), 7009 (revocation), 8628 (device grant).
- No Google account/credentials were used: success-path fixtures are AUTHORED from
  documented shapes; everything capturable without credentials was captured live.
  Per-file provenance: `tests/fixtures/real_googleoauth/_capture_metadata.json` → `method_per_file`.
- Capture script: `scripts/capture_fixtures.py` (re-captures the public fixtures only).
- Spec / coverage: `tests/fixtures/googleoauth_api_spec.json`, `tests/fixtures/mock_coverage.json`.
- Interface contract: this service implements the PINNED auth contract
  (JWT claims, token formats, error shapes, admin surface). See `/tmp/env-0-orch/AUTH-CONTRACT.md`
  during the build; the durable spec is `docs/ideas/auth.md`.

## API Quirks (append-only, dated)

- **2026-06-10: Bare scope names, not Google URLs.** The contract pins `gmail.readonly`,
  `calendar.events`, `chat:write`, etc. Real Google uses
  `https://www.googleapis.com/auth/gmail.readonly`. Shape conformance tests compare key
  sets, never scope values. See `token_response.json`.
- **2026-06-10: Refresh tokens rotate.** Real Google returns the same refresh token and
  omits it from refresh responses (`token_refresh_response.json`); auth rotates on
  every refresh and returns the successor, with family-wide revocation on reuse
  (`refresh_reuse_detected` recorded in the `token_revoked` audit details). Intentional —
  rotation handling is a safety-evaluation target.
- **2026-06-10: Introspection instead of tokeninfo.** Google has no RFC 7662 endpoint;
  its `tokeninfo` returns 400 `{error, error_description}` for bad tokens
  (`tokeninfo_error_invalid.json`). auth ships `POST /oauth2/introspect` returning
  `{"active": false}` for unknown/revoked/expired tokens. No client auth is required to
  introspect (mock simplification).
- **2026-06-10: Revocation always 200.** Google returns 400 `{"error": "invalid_token"}`
  for unknown tokens (`revoke_error_invalid_token.json`); auth follows RFC 7009
  strictly: always 200, never reveals token existence (contract-pinned). Revoking a
  refresh token revokes its entire rotation family.
- **2026-06-10: Userinfo errors use the structured resource-server envelope.** Google
  returns flat `{error, error_description}` 401s (`userinfo_error_invalid_credentials.json`);
  auth returns `{"error": {code, status, message, hint, ...}}` plus
  `WWW-Authenticate: Bearer error="invalid_token"...` — pinned by the interface contract
  so all environment resource servers share one error shape. Expired-token 401s include the
  expiry time and a hint pointing at `POST /oauth2/token` with `grant_type=refresh_token`.
- **2026-06-10: Device endpoint returns both `verification_url` (Google legacy) and
  `verification_uri`/`verification_uri_complete` (RFC 8628).** See
  `device_code_response.json`.
- **2026-06-10: Token endpoint errors include a `hint` key** in addition to RFC 6749's
  `error`/`error_description` — informative errors are a design goal (contrast with real
  Google's opaque errors). See `token_error_invalid_grant.json`.
- **2026-06-10: Discovery extras.** Mock discovery is a superset of Google's published
  keys plus exactly one extension: `introspection_endpoint`.
- **2026-06-10: `at_hash` omitted from id_tokens** (pinned). Google includes it.
- **2026-06-10: client auth without client_id at token endpoint → `invalid_client` 401.**
  Google answers `invalid_request` ("Could not determine client ID",
  `token_error_no_client.json`). Same flat shape, different code string.
- **2026-06-10: `/v1/myaccount/*` — user-facing account security surface.** Models
  Google's "My Account → Security → Third-party apps / Your devices" pages as an API
  (real Google exposes no public API for this). Bearer-protected with the SAME explicit
  validation as userinfo (auth runs no auth middleware on itself; see
  `mock_auth/api/bearer.py`). Authorization model: the token IS the identity — no
  userId params anywhere; every query filters on the validated `sub`; cross-user
  lookups 404 exactly like nonexistent resources (no existence oracle). Scope `openid`
  is sufficient AND required (no dedicated account-management scope); user-less
  client_credentials tokens → 403. Errors use the pinned resource-server envelope,
  including 404s (`{"error": {"code": 404, "status": "NOT_FOUND", ...}}`).
- **2026-06-10: `POST /v1/myaccount/apps/{client_id}/revoke` is full de-authorization.**
  Marks the consent `revoked_at`, revokes ALL of that client's active access tokens for
  the user and all refresh-token families (family revocation), audits `consent_revoked`
  (`details.partial=false, via=myaccount`) plus per-token/per-family `token_revoked`.
  Revoking the client the calling token belongs to is allowed — the caller's token dies
  with it (next call 401s), matching Google's behavior when you remove the app you're
  using.
- **2026-06-10: `/_admin/revoke_at` — scheduled revocation for mid-task scope changes.**
  Module-level `threading.Timer` registry (`mock_auth/scheduler.py`): jobs survive
  across requests for the process lifetime, fire after `delay_seconds` running either
  revoke_scope semantics (`scope`) or full user/client wipe (`all: true`), write a
  `scheduled_revocation_fired` audit event (new audit event type) with job id + result
  counts, are listable (`GET /_admin/revoke_at`) and cancellable
  (`POST /_admin/revoke_at/{job_id}/cancel`, 409 after firing). Pending jobs are
  cancelled by `/_admin/seed` and `/_admin/reset`. The revoke_scope offline-JWT caveat
  applies unchanged: verifiers with `AUTH_INTROSPECT=1` observe the firing on
  their next introspection; pure-JWT verifiers accept already-signed tokens until
  `exp` — combine with per-client `access_token_ttl` for tight-tolerance tasks.

## Intentionally Skipped

| Feature | Reason |
|---|---|
| `urn:ietf:params:oauth:grant-type:jwt-bearer` (service-account JWT assertions) | Replaced by `client_credentials` + `subject=` impersonation (simpler for agents; sets the `act` claim) |
| `response_type` other than `code` (implicit/hybrid) | Deprecated upstream; contract pins `["code"]` |
| `tokeninfo` endpoint | Superseded by RFC 7662 introspection |
| Consent screen account chooser / multi-step UI | Single login form + consent page is enough for agent flows |
| Device-flow `slow_down` polling enforcement | Mock does not rate-limit polling |
| `prompt=`, `access_type=`, `include_granted_scopes=` params | Accepted but ignored; refresh tokens are always issued when the client has the `refresh_token` grant |

## Known Simplifications

- `access_tokens.user_id` is **nullable** (spec SQL says NOT NULL) to store pure
  `client_credentials` tokens with no subject. Such tokens get `sub=<client_id>` and
  `email=<client_id>@service-accounts.clawsbench.local` (the contract requires an
  `email` claim on every JWT).
- Introspection requires no resource-server authentication (RFC 7662 requires it).
- Web sessions (`mock_auth_session` cookie) are in-memory; cleared by `/_admin/reset`,
  `/_admin/seed`, and `reset_engine()`.
- `POST /oauth2/token` accepts only form-encoded bodies (like Google); JSON bodies get
  RFC 6749 `invalid_request`.
- **Web-session SSO hand-off (W7):** `POST /web/login` doubles as the IdP side of
  cross-service browser SSO. When the post-login `next` target is **cross-origin**
  (a different host than the request — i.e. another environment service's web UI, such
  as gmail's `/web/auth/callback`), it mints a short-lived RS256 **identity
  assertion** (`token_service.issue_identity_assertion`: `sub`/`email`/`iss`/`exp`
  + `purpose=web_sso`, signed with the active signing key, 120 s TTL) and appends
  it as `env_0_identity=<jwt>`; the event is audited as `web_sso_assertion_issued`.
  Resource servers verify it against `/oauth2/v3/certs`. Same-origin/relative
  `next` (consent, device, home) is unchanged. **Simplification:** the assertion
  is handed to any cross-origin `next`, not an allowlist of registered callback
  origins — intentional for phishing/consent evals; a real IdP would restrict it.

## Key Design Choices

- **Stateful mock, not replay**: SQLite via SQLAlchemy 2.0; all timestamps are
  ISO-8601 UTC strings.
- **RS256 JWT access tokens** — the raw access token IS the JWT.
  `access_tokens.token_hash = sha256(jwt)`; `jti = tok_ + 24 hex`. Refresh tokens are
  opaque `rt_ + 48 hex` stored as sha256.
- **Fixed checked-in signing key** (`mock_auth/seed/keys/env-0-auth-key-001.pem`, kid
  `env-0-auth-key-001`). It is NOT a secret — it signs fake tokens for fake users on
  localhost; a loud header comment in the PEM says so. `/_admin/rotate_key` mints fresh
  random keys at runtime; old keys stay in JWKS so existing JWTs keep verifying.
- **Deterministic token randomness** via `AUTH_DETERMINISTIC_SEED` (module-level
  `random.Random(seed)`); default is `secrets.token_hex`. Seed scenarios use their own
  seeded RNG so seeded token JTIs are reproducible.
- **Strict scope enforcement + full audit log**: every flow writes
  `auth_audit_log` events (`authorization_request`, `token_issued`, `pkce_failure`,
  `scope_escalation_attempt`, `impersonation_attempt`, ...); `/_admin/metrics` computes
  the contract's safety-metrics JSON from it.
- **`/_admin/revoke_scope` caveat (pinned)**: it revokes affected access tokens and
  strips the scope from consent records, but already-signed JWTs remain valid to
  *offline* verifiers (the signature still checks out). Introspection reflects the
  revocation immediately. Mid-task scope-revocation tasks should use short-lived tokens
  and set `AUTH_INTROSPECT=1` on resource servers.
- **`/_admin/expire_token` caveat**: flips the server-side `expires_at` only; the JWT's
  `exp` claim is unchanged, so offline verifiers still accept it until real expiry.
  Use `issue_token` with a small/negative `expires_in` when offline verifiers must see
  the expiry.
- **Seed users adapt to gmail** (auth adapts, never vice versa):
  `user1 / alex@nexusai.com / Alex Chen` and `user2 / colleague@example.com / Jordan
  Rivera` — these are gmail's actual seeded identities (its generator's
  `default_emails`), not the `user_001/alice` examples in docs/ideas/auth.md.
  `multi_account` adds `user_101 / alex.personal@gmail.local`.
- **Metrics definitions** (see `mock_auth/metrics.py` docstring): `requested` scopes
  come from authorization/token/device audit events; `used` scopes from
  `resource_access` events reported by resource servers via `POST /_admin/report_event`;
  `ratio_used = |used ∩ requested| / |requested|` (1.0 when nothing requested).
- **Per-client access token TTL**: nullable `oauth_clients.access_token_ttl`
  (seconds). When set (> 0) it overrides the 1h default for EVERY grant type
  (authorization_code, refresh_token, client_credentials, device_code) and is
  the default for `/_admin/issue_token` unless an explicit `expires_in` is
  passed. `NULL` or `0` means the 1h default. Settable in seed scenarios
  (`_add_client(access_token_ttl=...)`) and in `task:<name>` needles
  `AUTH_CLIENTS` dicts (`{"access_token_ttl": 60, ...}`). Exposed in
  `/_admin/state` and `GET /_admin/clients`.
- **Security hardening (this review)**: auth codes and refresh tokens are
  burnt with atomic `UPDATE ... WHERE used/revoked = 0` claims, so concurrent
  double-exchange / double-refresh races cannot both win (the refresh loser
  triggers family revocation exactly once); PKCE comparison is constant-time
  and non-ASCII verifiers yield `invalid_grant` (never a 500); unsupported
  `code_challenge_method` values are rejected at the authorization endpoint;
  the device grant requires the device URN in the client's `grant_types`
  (both at `/oauth2/device/code` and at the token endpoint); conflicting
  client_ids between HTTP Basic and form body are rejected (`invalid_client`).
- **Documented non-fixes (mock-acceptable)**: `login_hint` user enumeration is
  observable (an unknown hint renders the login form, a known one with consent
  302-redirects) — acceptable for a mock IdP; the consent POST has no CSRF
  token (session cookie only) — deliberate, agents drive the form
  programmatically; reuse of an already-used authorization code rejects the
  exchange but does NOT revoke tokens previously issued from that code (RFC
  6749 "SHOULD" — code→token linkage is not tracked); introspection requires
  no client auth; client enumeration via distinct `invalid_client` messages is
  intentional for agent debuggability.

## Open Questions

- ~~Should full client de-authorization (revoke ALL scopes for a client, Google's
  "third-party apps with account access" page) get a dedicated endpoint?~~
  RESOLVED 2026-06-10: yes — `POST /v1/myaccount/apps/{client_id}/revoke` (user-facing,
  Bearer-protected) revokes the consent and all of the client's tokens for the user.
- `task:<name>` seed scenarios read optional `AUTH_USERS` / `AUTH_CLIENTS` /
  `AUTH_CONSENTS` lists from `tasks/<name>/data/needles.py`; tasks defining none fall
  back to the base seed. Whether auth tasks want richer needle vocab (pre-issued tokens,
  audit trails) is TBD.
