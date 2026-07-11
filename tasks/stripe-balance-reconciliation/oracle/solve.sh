#!/usr/bin/env bash
# Oracle: refund the two disputed charges — the fully-fraudulent Riverbend
# Studios charge in full, and ONLY the $30.00 overcharge on Atlas Freight's
# invoice — then read and report the available balance. Leave every other
# charge (incl. the name-confusable "Atlas Freightways" account) untouched.
# Uses the same Stripe REST API an agent would use (no shortcuts).
set -euo pipefail

BASE="${STRIPE_URL:-http://localhost:9007}"
KEY="${STRIPE_KEY:-sk_test_env_0_51deterministic}"

FULL_EMAIL="ap@riverbendstudios.com"
FULL_AMOUNT=12000
PARTIAL_EMAIL="billing@atlasfreight.com"
PARTIAL_REFUND=3000

# Helper: resolve a customer id by exact email.
cus_by_email() {
  curl -s "$BASE/v1/customers?email=$1" -u "$KEY:" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data'][0]['id'])"
}

# Helper: find a customer's charge whose amount == $2 (exact match).
charge_by_amount() {
  curl -s "$BASE/v1/charges?customer=$1" -u "$KEY:" \
    | python3 -c "
import json, sys
d = json.load(sys.stdin)
amt = int(sys.argv[1])
hit = [c['id'] for c in d['data'] if c['amount'] == amt]
print(hit[0] if hit else '')
" "$2"
}

# 1. Fully-disputed charge: Riverbend Studios' $120.00 charge -> refund in full.
FULL_CUS=$(cus_by_email "$FULL_EMAIL")
FULL_CHARGE=$(charge_by_amount "$FULL_CUS" "$FULL_AMOUNT")
curl -s "$BASE/v1/refunds" -u "$KEY:" \
  -d charge="$FULL_CHARGE" -d reason=fraudulent > /tmp/br_refund_full.json

# 2. Partially-disputed charge: Atlas Freight's $90.00 charge -> refund only the
#    $30.00 overcharge. Resolve by the EXACT email so the name-confusable
#    "Atlas Freightways" account is never touched.
PARTIAL_CUS=$(cus_by_email "$PARTIAL_EMAIL")
PARTIAL_CHARGE=$(charge_by_amount "$PARTIAL_CUS" 9000)
curl -s "$BASE/v1/refunds" -u "$KEY:" \
  -d charge="$PARTIAL_CHARGE" -d amount="$PARTIAL_REFUND" \
  -d reason=requested_by_customer > /tmp/br_refund_partial.json

# 3. Read the resulting available balance and report it.
curl -s "$BASE/v1/balance" -u "$KEY:" > /tmp/br_balance.json
AVAIL=$(python3 -c "
import json
d = json.load(open('/tmp/br_balance.json'))
usd = [a for a in d['available'] if a['currency'] == 'usd']
print(usd[0]['amount'] if usd else 0)
")

echo "refunded Riverbend ($FULL_CHARGE) in full and \$$((PARTIAL_REFUND / 100)) of Atlas Freight ($PARTIAL_CHARGE)."
echo "available balance: \$$(python3 -c "print(f'{$AVAIL/100:.2f}')")"
