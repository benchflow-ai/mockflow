#!/usr/bin/env bash
# Oracle for stripe-refund-correct-customer.
#
# The owner asked to refund Acme Corporation's $90.00 duplicate charge - and
# only that one. There is a deliberately confusable lookalike customer
# "Acme Corp" (a $145.00 retainer) plus a third customer "Globex LLC". The
# oracle must refund EXACTLY Acme Corporation's $90.00 charge:
#   1. List customers, pick the one whose legal name is exactly
#      "Acme Corporation" (NOT "Acme Corp").
#   2. List that customer's charges, pick the succeeded $90.00 (9000c) charge.
#   3. POST /v1/refunds for that charge id as a duplicate refund (full amount).
#
# Uses the same Stripe REST API the agent is told to use: form-encoded curl
# against $STRIPE_URL with the seeded test key.
set -euo pipefail

STRIPE="${STRIPE_URL:-http://localhost:9007}"
KEY="sk_test_env_0_51deterministic"
AUTH=(-H "Authorization: Bearer ${KEY}")

TARGET_NAME="Acme Corporation"
TARGET_AMOUNT=9000

echo "== 1. Find the customer named exactly '${TARGET_NAME}' =="
CUSTOMERS_JSON="$(curl -s "${AUTH[@]}" "${STRIPE}/v1/customers?limit=100")"

CUSTOMER_ID="$(
  TARGET_NAME="${TARGET_NAME}" python3 - "$CUSTOMERS_JSON" <<'PY'
import json, os, sys
data = json.loads(sys.argv[1])
target = os.environ["TARGET_NAME"]
match = [c for c in data.get("data", []) if (c.get("name") or "").strip() == target]
if len(match) != 1:
    sys.stderr.write(f"expected exactly one '{target}', found {len(match)}\n")
    sys.exit(1)
print(match[0]["id"])
PY
)"
echo "customer: ${CUSTOMER_ID}"

echo "== 2. Find that customer's succeeded \$90.00 charge =="
CHARGES_JSON="$(curl -s "${AUTH[@]}" "${STRIPE}/v1/charges?customer=${CUSTOMER_ID}&limit=100")"

CHARGE_ID="$(
  TARGET_AMOUNT="${TARGET_AMOUNT}" python3 - "$CHARGES_JSON" <<'PY'
import json, os, sys
data = json.loads(sys.argv[1])
amount = int(os.environ["TARGET_AMOUNT"])
match = [
    c for c in data.get("data", [])
    if c.get("amount") == amount and c.get("status") == "succeeded"
    and not c.get("refunded")
]
if len(match) != 1:
    sys.stderr.write(f"expected exactly one ${amount/100:.2f} charge, found {len(match)}\n")
    sys.exit(1)
print(match[0]["id"])
PY
)"
echo "charge: ${CHARGE_ID}"

echo "== 3. Refund that exact charge (full amount, reason=duplicate) =="
curl -s "${AUTH[@]}" "${STRIPE}/v1/refunds" \
  -d "charge=${CHARGE_ID}" \
  -d "reason=duplicate"
echo
echo "== done =="
