"""Per-route OAuth scope requirements for auth (used when AUTH_ENABLED=1).

``STRIPE_SCOPE_MAP`` keys are ``(HTTP_METHOD, route_path_template)`` tuples
EXACTLY as the routes are registered on the FastAPI app (see
``mock_stripe/api/*.py``; all Stripe REST routes live under ``/v1``). Values
are OR-logic scope lists: ANY one listed scope grants access. A route absent
from the map requires a valid token but no particular scope (contract: "missing
route key => only auth required") -- we keep every /v1 key present so the
coverage test proves each route was considered.

This models Stripe's restricted-API-key permission system, where each resource
carries a none/read/write permission, as OAuth scopes:

- per-resource ``stripe.<res>.read`` / ``stripe.<res>.write`` -- WRITE IMPLIES
  READ, expressed by listing ``.write`` on every read route;
- ``stripe.read_only`` satisfies ANY ``.read`` (listed on every read route);
- ``stripe.full`` satisfies EVERYTHING (listed on every route);
- read-only resources (balance / balance_transactions / events) expose only
  ``.read`` scopes.

Mapping rules (mission-pinned):
- GET / list on a resource     -> [<res>.read, <res>.write, read_only, full]
- POST / DELETE mutations
  (create / update / confirm /
   capture / cancel / attach /
   detach / refund / delete)    -> [<res>.write, full]
- payment_intents confirm /
  capture / cancel and the 3DS
  ``_complete_authentication``  -> payment_intents.write
- refunds create               -> refunds.write
- balance / balance_transactions
  / events                     -> read-only resource scopes
- webhook_endpoints CRUD       -> webhook_endpoints.read / .write
- GET /v1/account              -> any Stripe scope (lowest-privilege read)

This module deliberately has NO env_0_auth_client import so that stripe
works unchanged when auth-client is not installed (mirrors gmail /
slack). Scope names are kept as local literals.

Coverage of every registered /v1 route is enforced by
``tests/test_auth_integration.py::TestScopeMapCoverage``.
"""

from __future__ import annotations

# Mirrors env_0_auth_client.ScopeMap (kept local: auth-client is optional).
ScopeMap = dict[tuple[str, str], list[str]]

V1 = "/v1"

# Convenience aggregates.
READ_ONLY = "stripe.read_only"
FULL = "stripe.full"


def _read(resource: str) -> list[str]:
    """Read route: own .read OR own .write (write implies read) OR aggregates."""
    return [f"stripe.{resource}.read", f"stripe.{resource}.write", READ_ONLY, FULL]


def _write(resource: str) -> list[str]:
    """Mutating route: own .write OR full."""
    return [f"stripe.{resource}.write", FULL]


def _read_only_resource(resource: str) -> list[str]:
    """A resource Stripe exposes read-only (no .write scope exists)."""
    return [f"stripe.{resource}.read", READ_ONLY, FULL]


# Per-resource read/write lists.
CUSTOMERS_READ = _read("customers")
CUSTOMERS_WRITE = _write("customers")
PAYMENT_INTENTS_READ = _read("payment_intents")
PAYMENT_INTENTS_WRITE = _write("payment_intents")
CHARGES_READ = _read("charges")
CHARGES_WRITE = _write("charges")
REFUNDS_READ = _read("refunds")
REFUNDS_WRITE = _write("refunds")
PAYMENT_METHODS_READ = _read("payment_methods")
PAYMENT_METHODS_WRITE = _write("payment_methods")
PRODUCTS_READ = _read("products")
PRODUCTS_WRITE = _write("products")
PRICES_READ = _read("prices")
PRICES_WRITE = _write("prices")
WEBHOOK_ENDPOINTS_READ = _read("webhook_endpoints")
WEBHOOK_ENDPOINTS_WRITE = _write("webhook_endpoints")

# Read-only resources.
BALANCE_READ = _read_only_resource("balance")
BALANCE_TRANSACTIONS_READ = _read_only_resource("balance_transactions")
EVENTS_READ = _read_only_resource("events")

# Listing a customer's payment methods reads payment-method data nested under a
# customer, so EITHER reading customers OR reading payment_methods suffices.
CUSTOMER_PM_READ = [
    "stripe.customers.read", "stripe.customers.write",
    "stripe.payment_methods.read", "stripe.payment_methods.write",
    READ_ONLY, FULL,
]

# GET /v1/account returns only sandbox account metadata -- the lowest-privilege
# read in the API. Any valid Stripe scope (read, write, or aggregate) grants it
# ("stripe.read_only-or-any").
ACCOUNT_ANY = sorted({
    s
    for lst in (
        CUSTOMERS_READ, CUSTOMERS_WRITE, PAYMENT_INTENTS_READ, PAYMENT_INTENTS_WRITE,
        CHARGES_READ, CHARGES_WRITE, REFUNDS_READ, REFUNDS_WRITE,
        PAYMENT_METHODS_READ, PAYMENT_METHODS_WRITE, PRODUCTS_READ, PRODUCTS_WRITE,
        PRICES_READ, PRICES_WRITE, WEBHOOK_ENDPOINTS_READ, WEBHOOK_ENDPOINTS_WRITE,
        BALANCE_READ, BALANCE_TRANSACTIONS_READ, EVENTS_READ,
    )
    for s in lst
})


STRIPE_SCOPE_MAP: ScopeMap = {
    # --- customers ---
    ("POST", f"{V1}/customers"): CUSTOMERS_WRITE,
    ("GET", f"{V1}/customers"): CUSTOMERS_READ,
    ("GET", f"{V1}/customers/{{customer_id}}"): CUSTOMERS_READ,
    ("POST", f"{V1}/customers/{{customer_id}}"): CUSTOMERS_WRITE,
    ("DELETE", f"{V1}/customers/{{customer_id}}"): CUSTOMERS_WRITE,
    ("GET", f"{V1}/customers/{{customer_id}}/payment_methods"): CUSTOMER_PM_READ,
    # --- payment_methods ---
    ("POST", f"{V1}/payment_methods"): PAYMENT_METHODS_WRITE,
    ("GET", f"{V1}/payment_methods"): PAYMENT_METHODS_READ,
    ("GET", f"{V1}/payment_methods/{{pm_id}}"): PAYMENT_METHODS_READ,
    ("POST", f"{V1}/payment_methods/{{pm_id}}"): PAYMENT_METHODS_WRITE,
    ("POST", f"{V1}/payment_methods/{{pm_id}}/attach"): PAYMENT_METHODS_WRITE,
    ("POST", f"{V1}/payment_methods/{{pm_id}}/detach"): PAYMENT_METHODS_WRITE,
    # --- payment_intents ---
    ("POST", f"{V1}/payment_intents"): PAYMENT_INTENTS_WRITE,
    ("GET", f"{V1}/payment_intents"): PAYMENT_INTENTS_READ,
    ("GET", f"{V1}/payment_intents/{{pi_id}}"): PAYMENT_INTENTS_READ,
    ("POST", f"{V1}/payment_intents/{{pi_id}}"): PAYMENT_INTENTS_WRITE,
    ("POST", f"{V1}/payment_intents/{{pi_id}}/confirm"): PAYMENT_INTENTS_WRITE,
    ("POST", f"{V1}/payment_intents/{{pi_id}}/_complete_authentication"): PAYMENT_INTENTS_WRITE,
    ("POST", f"{V1}/payment_intents/{{pi_id}}/capture"): PAYMENT_INTENTS_WRITE,
    ("POST", f"{V1}/payment_intents/{{pi_id}}/cancel"): PAYMENT_INTENTS_WRITE,
    # --- charges ---
    ("GET", f"{V1}/charges"): CHARGES_READ,
    ("GET", f"{V1}/charges/{{charge_id}}"): CHARGES_READ,
    ("POST", f"{V1}/charges/{{charge_id}}"): CHARGES_WRITE,
    # --- refunds ---
    ("POST", f"{V1}/refunds"): REFUNDS_WRITE,
    ("GET", f"{V1}/refunds"): REFUNDS_READ,
    ("GET", f"{V1}/refunds/{{refund_id}}"): REFUNDS_READ,
    ("POST", f"{V1}/refunds/{{refund_id}}"): REFUNDS_WRITE,
    ("POST", f"{V1}/refunds/{{refund_id}}/cancel"): REFUNDS_WRITE,
    # --- products ---
    ("POST", f"{V1}/products"): PRODUCTS_WRITE,
    ("GET", f"{V1}/products"): PRODUCTS_READ,
    ("GET", f"{V1}/products/{{product_id}}"): PRODUCTS_READ,
    ("POST", f"{V1}/products/{{product_id}}"): PRODUCTS_WRITE,
    ("DELETE", f"{V1}/products/{{product_id}}"): PRODUCTS_WRITE,
    # --- prices ---
    ("POST", f"{V1}/prices"): PRICES_WRITE,
    ("GET", f"{V1}/prices"): PRICES_READ,
    ("GET", f"{V1}/prices/{{price_id}}"): PRICES_READ,
    ("POST", f"{V1}/prices/{{price_id}}"): PRICES_WRITE,
    # --- balance (read-only resource) ---
    ("GET", f"{V1}/balance"): BALANCE_READ,
    ("GET", f"{V1}/balance_transactions"): BALANCE_TRANSACTIONS_READ,
    ("GET", f"{V1}/balance_transactions/{{txn_id}}"): BALANCE_TRANSACTIONS_READ,
    # --- events (read-only resource) ---
    ("GET", f"{V1}/events"): EVENTS_READ,
    ("GET", f"{V1}/events/{{event_id}}"): EVENTS_READ,
    # --- account (any Stripe scope) ---
    ("GET", f"{V1}/account"): ACCOUNT_ANY,
    # --- webhook_endpoints ---
    ("POST", f"{V1}/webhook_endpoints"): WEBHOOK_ENDPOINTS_WRITE,
    ("GET", f"{V1}/webhook_endpoints"): WEBHOOK_ENDPOINTS_READ,
    ("GET", f"{V1}/webhook_endpoints/{{we_id}}"): WEBHOOK_ENDPOINTS_READ,
    ("POST", f"{V1}/webhook_endpoints/{{we_id}}"): WEBHOOK_ENDPOINTS_WRITE,
    ("DELETE", f"{V1}/webhook_endpoints/{{we_id}}"): WEBHOOK_ENDPOINTS_WRITE,
}
