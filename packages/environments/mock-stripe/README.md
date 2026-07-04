# mock-stripe

Mock Stripe API environment for AI agent safety evaluation and RL training.
Stripe-compatible REST API (`/v1/*`) over SQLite: customers, payment methods,
payment intents (full status machine incl. declines, 3DS/SCA
`requires_action`, and manual capture), charges, refunds, products/prices,
balance, balance transactions, events, and webhook endpoints with real signed
delivery.

## Quick start

```bash
cd packages/environments/mock-stripe
uv sync --extra dev

uv run mock-stripe seed --scenario default --seed 42
uv run mock-stripe serve --no-mcp     # port from config.toml [mock-stripe], fallback 9007
```

Then:

```bash
KEY=sk_test_env_0_51deterministic           # seeded API key

curl -s http://localhost:9007/v1/customers -H "Authorization: Bearer $KEY"

# Same auth as real Stripe — HTTP Basic with the key as username also works:
curl -s http://localhost:9007/v1/balance -u "$KEY:"

# Create + confirm a payment (form-encoded bodies, bracket notation):
curl -s http://localhost:9007/v1/payment_intents -u "$KEY:" \
  -d amount=1099 -d currency=usd -d "automatic_payment_methods[enabled]=true"
curl -s http://localhost:9007/v1/payment_intents/<pi_id>/confirm -u "$KEY:" \
  -d payment_method=pm_card_visa
```

Web dashboard (customers + recent payments): http://localhost:9007/
Interactive API docs: http://localhost:9007/docs

## Test payment methods

Use the documented Stripe test tokens directly (no prior creation needed):
`pm_card_visa`, `pm_card_mastercard`, `pm_card_amex`,
`pm_card_chargeDeclined` / `pm_card_visa_chargeDeclined` (generic decline, 402),
`pm_card_chargeDeclinedInsufficientFunds` /
`pm_card_visa_chargeDeclinedInsufficientFunds`, lost/stolen/expired/cvc/
processing/velocity variants, plus `tok_*` equivalents for
`card[token]=`. Raw test card numbers (`card[number]=4242424242424242`, decline
numbers `4000000000000002`, `4000000000009995`, ...) behave per
https://docs.stripe.com/testing.

### 3DS / SCA

`pm_card_authenticationRequired` / `pm_card_authenticationRequiredOnSetup`
(cards `4000002760003184` / `4000002500003155`): confirm returns
`status=requires_action` with a real-shape `next_action` and nothing is
charged. Real Stripe completes the challenge via Stripe.js; the mock stands
that in with a **mock-only** endpoint:

```bash
curl -s http://localhost:9007/v1/payment_intents/<pi_id>/_complete_authentication \
  -u "$KEY:" -d succeed=true     # -> succeeded (or requires_capture if manual)
# succeed=false -> requires_payment_method + last_payment_error
#                  authentication_required + a failed charge
```

## Webhooks

```bash
# Register an endpoint — the whsec_ secret is returned ONLY here (real behavior):
curl -s http://localhost:9007/v1/webhook_endpoints -u "$KEY:" \
  -d url=https://my-receiver.local/hook -d "enabled_events[]=*"
```

Every recorded event matching an endpoint's `enabled_events` (or `["*"]`) is
POSTed asynchronously as the standard event JSON with a `Stripe-Signature`
header (`t=<ts>,v1=<HMAC-SHA256("<ts>.<payload>", secret)>`) that
`stripe.Webhook.construct_event()` verifies. One attempt per event, 5s
timeout, no retries (divergence from real Stripe — see API_NOTES.md).
Delivery attempts (status_code/error) are logged at
`GET /_admin/webhook_deliveries?endpoint=&event=`.

## Scenarios

| Scenario | Contents |
|---|---|
| `default` | API key, 3 customers with attached cards, 2 products + prices, 4 succeeded payments (+charges, balance txns, events), 1 partial refund, 1 uncaptured (`requires_capture`) payment. Deterministic per `--seed`. |
| `fresh` | Only the API key (`sk_test_env_0_51deterministic`). |
| `task:<name>` | Auto-discovered from `tasks/<name>/data/stripe_seed.py` exposing `seed(db, rng, fake) -> dict` (uses `TASKS_DIR` env var or repo `tasks/`). |

## CLI

```bash
mock-stripe --db <path> seed --scenario <name> --seed 42
mock-stripe --db <path> serve --host 0.0.0.0 --port 9007 --no-mcp
mock-stripe --db <path> reset
mock-stripe list-tasks | run-task <name> | eval-task <name>
```

## Admin API (no auth)

`POST /_admin/reset`, `POST /_admin/seed?scenario=&seed=`, `GET /_admin/state`,
`GET /_admin/diff`, `GET /_admin/action_log`,
`GET /_admin/webhook_deliveries?endpoint=&event=&limit=`,
`POST /_admin/snapshot/{name}`, `POST /_admin/restore/{name}`,
`GET /_admin/tasks`, `POST /_admin/tasks/{name}/evaluate`,
`GET /_admin/skills[/{name}]`, `GET /health`. Snapshots/diff cover all tables
including `webhook_endpoints` and `webhook_deliveries`.

## Tests

```bash
cd packages/environments/mock-stripe
uv run pytest tests/ -q        # 252 tests: functional + conformance + webhooks + 3DS
```

`tests/test_conformance.py` validates response shapes against the golden
fixtures in `tests/fixtures/real_stripe/` (authored from docs.stripe.com
reference examples — see `_capture_metadata.json` and API_NOTES.md for
provenance). `scripts/capture_fixtures.py` re-captures from the real API when
`STRIPE_SECRET_KEY=sk_test_...` is set.

## Notable mechanics (see API_NOTES.md for the full list)

- Bearer **and** Basic auth, 401 envelopes matching real Stripe.
- Form-encoded bodies with bracket notation (JSON accepted leniently).
- `Idempotency-Key` replay/conflict on POST.
- `expand[]` dot-paths (`latest_charge`, `customer`, `payment_method`,
  `balance_transaction`, `charge`, ... up to 4 levels, `data.` on lists).
- Declines: 402 `card_error` + failed charge + `last_payment_error`.
- 3DS: `requires_action` + `next_action` (`use_stripe_sdk` /
  `redirect_to_url`), completed via the mock-only
  `_complete_authentication` endpoint.
- Webhooks: signed delivery (`Stripe-Signature` t/v1 HMAC-SHA256) on a
  background thread; secret shown only on create; delivery log under
  `/_admin/webhook_deliveries`.
- Balance: fee = round(2.9% + 30¢) per captured charge; refunds are fee-free
  negative transactions.
