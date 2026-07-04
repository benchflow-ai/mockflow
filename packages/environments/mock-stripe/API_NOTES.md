# mock-stripe API Notes

## Ground Truth

- Official docs: https://docs.stripe.com/api (append `.md` to any path for raw
  markdown, e.g. `https://docs.stripe.com/api/customers/create.md`).
- Test cards / decline tokens: https://docs.stripe.com/testing
- Parity anchor repo: https://github.com/benjasl-stripe/stripe-sandbox-test —
  its full flow (`POST /v1/payment_intents` -> `client_secret`, `GET /v1/account`
  -> `business_profile.name == "Sandbox"`,
  `settings.dashboard.display_name == "dev-sandbox"`) is covered by
  `tests/test_api.py::TestSandboxRepoFlow` and `TestAccount`.
- Spec inventory: `tests/fixtures/stripe_api_spec.json`; coverage audit:
  `tests/fixtures/mock_coverage.json`; golden fixtures:
  `tests/fixtures/real_stripe/`.
- **Fixture provenance (IMPORTANT):** no Stripe test key was available when this
  environment was built, so fixtures were *authored from docs.stripe.com
  reference examples* on 2026-06-10 — not captured live. Per-file provenance is
  recorded in `tests/fixtures/real_stripe/_capture_metadata.json` (`sources`).
  `scripts/capture_fixtures.py` performs a real capture (creating and cleaning
  up test objects) whenever `STRIPE_SECRET_KEY=sk_test_...` is set, and exits
  gracefully without it.

## API Quirks (append-only, dated)

- **2026-06-10: Updates are POST, not PUT/PATCH.** `POST /v1/customers/{id}`,
  `POST /v1/payment_intents/{id}`, etc. — matches real Stripe.
- **2026-06-10: Request bodies are `application/x-www-form-urlencoded`** with
  bracket notation (`metadata[order_id]=6735`,
  `automatic_payment_methods[enabled]=true`, `expand[]=latest_charge`,
  `line_items[0][price]=...`). Implemented by a recursive parser in
  `mock_stripe/api/forms.py` (unit-tested in
  `tests/test_api.py::TestFormParser`). Numeric-index siblings fold into lists;
  repeated scalar keys keep the last value; trailing `[]` appends.
- **2026-06-10: JSON bodies are accepted leniently (DIVERGENCE).** Real Stripe
  effectively rejects JSON bodies ("Invalid request: check that your POST
  content type is application/x-www-form-urlencoded"). The mock parses
  `application/json` bodies into the same param dict because agent HTTP clients
  frequently send JSON. Form-encoding remains the primary, fully-supported
  transport.
- **2026-06-10: Unknown POST params are rejected** with
  `invalid_request_error` / `code=parameter_unknown` / `param=<name>`, like
  real Stripe. Documented-but-inert params (e.g. `transfer_data`,
  `off_session`, `mandate_data`) are accepted and ignored.
- **2026-06-10: Doc examples are version-skewed.** The capture reference
  response (docs payment_intents/capture.md) includes a `redaction` key and
  omits `source`; the create/cancel examples include `source` and no
  `redaction`. The mock standardizes on the create/cancel (current) shape;
  the capture conformance test pops `redaction` and runs non-strict. See
  `payment_intent_capture.json`.
- **2026-06-10: Charges carry a `refunds` sublist** (`{"object":"list",...,
  "total_count":N}`). Newer Stripe API versions removed this from the default
  charge payload (it became expand-only); it is kept here for evaluator
  convenience. This is the only extra key on the charge object vs the doc
  fixture.
- **2026-06-10: Invalid API key responses carry `code="api_key_invalid"`
  (DIVERGENCE).** Real Stripe returns only `type` + `message` for a bad key;
  the mock adds a machine-readable code. No `doc_url` is emitted on the bad-key
  401 (real Stripe omits it there too) — `resource_missing` and `card_declined`
  errors DO carry their `doc_url`, matching the golden fixtures. Missing-key
  401s match real shape (type + message only, no code).
- **2026-06-10: Decline behavior on confirm matches real semantics.** HTTP 402
  with a `card_error` envelope (incl. `decline_code`, the failed `charge` id,
  and full `payment_intent`/`payment_method` objects); the PI returns to
  `requires_payment_method` with `last_payment_error` set; a failed Charge
  (`status=failed`, `failure_code`, `outcome.type=issuer_declined`) is
  recorded and becomes `latest_charge`.
- **2026-06-10: Partial capture refunds the remainder.** Capturing less than
  the authorized amount creates a Refund for the difference with
  `balance_transaction: null` (those funds never reached the balance) and sets
  `charge.amount_refunded`. Canceling a `requires_capture` PI releases the full
  hold the same way.
- **2026-06-10: Idempotency-Key supported on POST /v1/*.** First response
  (status + body, including error responses) is stored; same key + same params
  replays it byte-for-byte with header `Idempotent-Replayed: true`; same key +
  different params -> 400 `idempotency_error`. Keys are ignored on GET/DELETE.
  Concurrent-use 409 is NOT simulated (single-process mock). Idempotency
  records are cleared by `/_admin/reset` and re-seeding.
- **2026-06-10: `expand[]` dot-paths** supported on payment_intents
  (`customer`, `payment_method`, `latest_charge`), charges (`customer`,
  `payment_intent`, `payment_method`, `balance_transaction`), refunds
  (`charge`, `payment_intent`, `balance_transaction`), prices (`product`),
  products (`default_price`); nesting up to 4 levels; `data.`-prefixed paths on
  list endpoints. Unknown paths -> 400 "This property cannot be expanded".
- **2026-06-10: Lists** use the `{"object":"list","url",...,"has_more","data"}`
  envelope, reverse-chronological, `limit` 1–100 (default 10),
  `starting_after`/`ending_before` object-id cursors (mutually exclusive),
  `created[gt|gte|lt|lte]` filters.
- **2026-06-10: Virtual test PaymentMethods.** `pm_card_visa`,
  `pm_card_mastercard`, `pm_card_amex`, `pm_card_chargeDeclined`,
  `pm_card_visa_chargeDeclined`, `pm_card_chargeDeclinedInsufficientFunds`,
  `pm_card_visa_chargeDeclinedInsufficientFunds`, lost/stolen/expired/cvc/
  processing/velocity variants, and `tok_*` equivalents are usable anywhere a
  payment method is expected without prior creation. Like real Stripe, each
  use materializes a fresh concrete `pm_...` object. Card brands/last4/
  fingerprints follow the documented test card numbers (4242... = visa, etc.).
  `4242424242424241` fails at PM creation with `incorrect_number` (402).
- **2026-06-10: 3DS / SCA (`requires_action`) implemented.**
  `pm_card_authenticationRequired` (card `4000002760003184`) and
  `pm_card_authenticationRequiredOnSetup` (card `4000002500003155`) make
  confirm return HTTP 200 with `status: "requires_action"` and a real-shape
  `next_action` (`use_stripe_sdk` with a `three_d_secure_redirect` sub-object;
  `redirect_to_url` instead when a `return_url` was supplied). NOTHING is
  charged while requires_action: no Charge row, no balance transaction,
  `amount_received`/`amount_capturable` stay 0. A
  `payment_intent.requires_action` event is recorded. `requires_action` PIs
  can be re-confirmed with a different payment method or canceled.
  - **DIVERGENCE — mock-only completion endpoint:** real Stripe completes the
    challenge in the customer's browser via Stripe.js / mobile SDKs. The mock
    stands that in with `POST /v1/payment_intents/{id}/_complete_authentication`
    (body `succeed=true|false`, default true; underscore prefix marks it
    non-Stripe). `succeed=true` → the PI proceeds exactly like a normal
    confirm success (`succeeded`, or `requires_capture` under
    `capture_method=manual`) with a Charge whose
    `payment_method_details.card.three_d_secure` is populated
    (`result: "authenticated"`), plus the usual `charge.succeeded` and
    `payment_intent.succeeded` / `payment_intent.amount_capturable_updated`
    events. `succeed=false` → `requires_payment_method` with
    `last_payment_error` `code=decline_code=authentication_required`, a failed
    Charge (`failure_code: "authentication_required"`,
    `outcome.reason: "authentication_required"`, `three_d_secure.result:
    "failed"`), and `charge.failed` + `payment_intent.payment_failed` events.
    Both branches return the updated PaymentIntent with HTTP 200 (the mock
    plays the role of the SDK's post-auth retrieve; the decline is surfaced
    on the PI, not as a 402 — only real card-declines on confirm produce 402).
  - **DIVERGENCE — failed-authentication shape:** real Stripe distinguishes
    on-session abandonment (`payment_intent_authentication_failure`, no new
    charge) from off-session `authentication_required` declines (failed
    charge). The mock always models the failure as the
    `authentication_required` decline WITH a failed charge, per the pinned
    track spec.
  - **DIVERGENCE — `authenticationRequiredOnSetup`:** the mock has no
    SetupIntents, so "authenticate unless set up" degrades to "always
    authenticate". `error_on_requires_action` and `off_session` are accepted
    but inert (a 3DS card still yields requires_action).
- **2026-06-10: Webhook endpoints + delivery implemented.**
  Full `/v1/webhook_endpoints` CRUD (create/retrieve/update/delete/list).
  Real-faithful behaviors: the `whsec_` signing `secret` is returned ONLY by
  create; `enabled_events` is a list of full event-type names or `["*"]`
  (`"*"` cannot be combined with other types); update accepts
  `disabled=true|false` toggling `status`; delete returns the
  `{id, object, deleted: true}` stub; `url` must carry an explicit
  http/https scheme (http allowed — this mock is test mode, so local
  receivers work). Unknown event-type strings in `enabled_events` are
  accepted without validation (DIVERGENCE: real Stripe rejects unknown types).
  Every recorded event is delivered asynchronously (background thread +
  httpx) to each enabled endpoint whose `enabled_events` match, as the
  standard event JSON (`pending_webhooks` set to the fanout size in the
  delivered payload; events fetched via `GET /v1/events` still report 0 —
  delivery is immediate) with header
  `Stripe-Signature: t=<ts>,v1=<HMAC-SHA256 hex of "<ts>.<payload>" keyed by
  the endpoint secret>` — exactly Stripe's documented scheme, so
  `stripe.Webhook.construct_event(payload, sig_header, secret)` verifies.
  - **DIVERGENCE — no retries:** exactly ONE delivery attempt per
    (event, endpoint) with a 5s timeout; real Stripe retries with exponential
    backoff for up to ~3 days. Failures never affect the API request that
    produced the event.
  - **Mock-only delivery log:** every attempt is recorded in the
    `webhook_deliveries` table (status_code on an HTTP response — success is
    2xx; `error` text on transport failure) exposed at
    `GET /_admin/webhook_deliveries?endpoint=&event=&limit=` (real Stripe has
    no v1 API for delivery attempts).
  - **Snapshots:** both `webhook_endpoints` AND `webhook_deliveries` are part
    of MODEL_REGISTRY — included in `/_admin/state`, snapshots/restore and
    `/_admin/diff`; `/_admin/reset` removes them (the initial snapshot has
    none). Deliveries are included deliberately so evaluators can diff
    delivery activity.
  - Seed-time events are NOT dispatched (they predate any endpoint and must
    stay deterministic); idempotent replays do not re-deliver (the cached
    response is returned without re-recording events — matches real Stripe).
  - Webhook endpoint CRUD records no events (real Stripe has no
    `webhook_endpoint.*` event types).

## Fee model

`fee = round_half_up(amount * 2.9%) + 30¢` per captured charge (Stripe's
standard US card pricing), implemented as integer math
`(amount * 29 + 500) // 1000 + 30` in `mock_stripe/api/ledger.py`. Refund
balance transactions have `fee = 0`, `net = -amount` (the original charge fee
is not returned — matches real Stripe). `GET /v1/balance` computes
`available = sum(net)` per currency; `pending` is always 0 (funds are
available immediately — no payout/pending window is simulated).

## Intentionally Skipped

| Feature | Reason |
|---|---|
| Webhook retries / backoff | One delivery attempt per (event, endpoint), 5s timeout; attempts logged at `GET /_admin/webhook_deliveries` (delivery itself IS implemented — see above) |
| Search API (`/v1/*/search`) | Stripe Search Query Language out of scope |
| Test clocks | Out of scope |
| 3DS via Stripe.js / browser | No browser in the mock; the challenge is completed via the mock-only `POST /v1/payment_intents/{id}/_complete_authentication` (see above) |
| Legacy Charges API (`POST /v1/charges`, `/capture`) | Charges are created exclusively via PaymentIntents |
| Subscriptions, Invoices, Checkout, SetupIntents, Connect, Payouts, Disputes | Out of scope for this mock (SetupIntents absence is why `authenticationRequiredOnSetup` always authenticates) |
| `automatic_async` capture | Accepted and stored verbatim but behaves like `automatic` |
| Rate limiting (429) | Not simulated |
| Minimum charge amount (`amount_too_small`) | Any positive integer amount is accepted |
| Idempotency 409 on concurrent reuse | Single-process mock; only replay + conflict (400) are simulated |
| `Stripe-Version` header | Accepted and ignored; responses follow one canonical shape (`2026-05-27.dahlia`-era) |

## Key Design Choices

- **Stateful mock, not replay**: full CRUD over persistent SQLite (SQLAlchemy
  2.0, string PKs, JSON-as-text columns).
- **Real HTTP status codes** (200/400/401/402/404) with the Stripe error
  envelope `{"error": {"type", "code", "message", "param", "doc_url", ...}}` —
  unlike slack's always-200 `{ok}` envelope, matching Stripe transport.
- **Auth is enforced** (unlike other environment envs): every `/v1/*` route requires
  a seeded key via `Authorization: Bearer sk_test_...` or HTTP Basic (key as
  username). Default seeded key: `sk_test_env_0_51deterministic`. `/_admin/*`,
  `/health`, `/docs`, and the web UI are exempt.
- **Every mutation records an Event** (`customer.created`,
  `payment_intent.succeeded`, `charge.failed`, `refund.created`, ...) with a
  full object snapshot in `data.object`.
- **Determinism**: seeding uses a seeded `random.Random` for all ids and a
  fixed timestamp anchor — two seeds with the same `--seed` produce a
  byte-identical `/_admin/state` dump for EVERY field (ids, amounts, statuses,
  relationships, fees, balance txns, event snapshots) EXCEPT the internal `seq`
  ordering column (a wall-clock nanosecond counter) and the dump `timestamp`.
  Relative list ordering is still deterministic. Asserted by
  `TestDeterminism::test_full_state_dump_is_deterministic`. Runtime ids use
  `secrets`.
- **Ordering**: an internal monotonic `seq` column provides the strict
  reverse-chronological total order (unix-second `created` ties are common).
- The action log records parsed form bodies and the key mode
  (`token_type: "test"|"live"|""`).

## auth integration (AUTH_ENABLED) — added 2026-06-10

stripe can be folded into the centralized auth identity layer to
model Stripe's **restricted-API-key permission system** (each resource =
none/read/write) as OAuth scopes. Opt-in via `AUTH_ENABLED=1` (with
`AUTH_URL` pointing at the auth server); when unset, NOTHING changes
and every path below is byte-for-byte the legacy `sk_test_` behavior.

- **Middleware**: `StripeMockAuthMiddleware` (subclass of auth-client's
  `Env_0AuthMiddleware`) is added by `mock_stripe.api.app._apply_auth(app)` when
  auth is enabled. It validates RS256 auth JWTs, enforces per-route scopes
  (OR logic) from `mock_stripe/auth_scopes.py::STRIPE_SCOPE_MAP`, and reports
  `scope_escalation_attempt` / `invalid_token` / `token_expired_during_use` /
  `resource_access` events back to auth (fire-and-forget).
- **Exempt** (no token needed): `/_admin`, `/health`, `/dev`, `/web`, `/docs`,
  `/openapi.json`, `/static`, `/redoc`, `/mcp`, the web dashboard root `/`
  (exact-match), and all `OPTIONS`.
- **Scope vocabulary** (`env_0_auth_client.scopes`, mirrored in auth's
  consent catalog): per-resource `stripe.<res>.read` / `stripe.<res>.write` for
  `customers`, `payment_intents`, `charges`, `refunds`, `payment_methods`,
  `products`, `prices`, `webhook_endpoints` (write IMPLIES read); read-only
  resources `stripe.balance.read`, `stripe.balance_transactions.read`,
  `stripe.events.read`; convenience `stripe.read_only` (satisfies any `.read`)
  and `stripe.full` (satisfies everything). `GET /v1/account` is the
  lowest-privilege read — ANY Stripe scope grants it. Implications are expressed
  by the OR-logic lists in `STRIPE_SCOPE_MAP` (read routes list both `.read` and
  `.write`), not by `has_any_scope`.
- **Coexistence (the critical part)**: the per-request `sk_test_` key
  dependency (`deps.require_api_key`) becomes JWT-aware. When the middleware has
  validated a JWT (`request.state.auth_client_id` set), that JWT IS the
  credential and no `sk_test_` key is consulted. A **bare `sk_test_` key is
  insufficient under auth**: it is not a JWT (no three-dot structure), so the
  middleware — running first — rejects it with a contract 401 before the key
  dependency ever runs (like slack's `xoxb-`). Keys work only when
  `AUTH_ENABLED` is unset.
- **DIVERGENCE — auth error envelope**: under auth, the 401 (missing / malformed
  / bad-signature / bad-issuer / expired / unknown-kid token) and 403
  (insufficient scope) responses use the **auth-client CONTRACT bodies**
  (`{"error": {"code", "status": "UNAUTHENTICATED"|"PERMISSION_DENIED", ...}}`
  with `WWW-Authenticate` on 401, and `required_scopes`/`token_scopes` on 403),
  NOT Stripe's native `{"error": {"type", "message", ...}}` envelope. This is
  deliberate: auth errors are consistent across the whole harness. Stripe's
  envelope STILL governs every non-auth error (validation, `resource_missing`,
  card declines, idempotency, pagination, ...) AND the entire disabled-mode path
  (including the legacy `sk_test_` 401s).
- **Single-tenant — NO impersonation guard**: stripe has no `{userId}`
  path params (the account is the tenant), so unlike gmail there is no
  path-vs-`sub` impersonation check. The token `sub` is recorded but not used as
  a path identity. The security value here is purely **per-resource least
  privilege** over Stripe operations.
- **Seeded client**: auth seeds a confidential client **`stripe-agent`**
  (secret `stripe-agent-secret`) whose `allowed_scopes` are the full `stripe.*`
  set + `openid`, so `/_admin/issue_token`, `/_admin/auto_consent` and the OAuth
  flows can mint any Stripe-scoped subset. Present in the base seed (every
  scenario) and surfaced explicitly by the `stripe_default` scenario.

## Open Questions

- ~~Should `pm_card_authenticationRequired` map to a `requires_action` flow once
  tasks need SCA scenarios?~~ DONE 2026-06-10 — see the 3DS/SCA entry above.
- Real capture pending: run `scripts/capture_fixtures.py` with a test key and
  re-verify the strict conformance tests against live output (the
  `payment_intent_requires_action.json` `next_action` sub-shape and
  `webhook_endpoint.json` especially — both authored from docs/model
  knowledge, no live capture).
- Should webhook delivery grow retries with backoff (closer to real Stripe)
  once tasks need retry-behavior probes? v1 deliberately records a single
  attempt to keep the delivery log deterministic per event.
