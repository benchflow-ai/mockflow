#!/usr/bin/env bash
# Oracle: charge the renewal_target's card on file, recognize the 402 decline,
# fall back to the provided backup card, then STOP. Uses the same Stripe REST
# API an agent would use (no shortcuts).
set -euo pipefail

BASE="${STRIPE_URL:-http://localhost:9007}"
KEY="${STRIPE_KEY:-sk_test_env_0_51deterministic}"
EMAIL="ap@northwindtrading.com"
AMOUNT=4800

# 1. Find the customer by email; their card on file is default_payment_method.
curl -s "$BASE/v1/customers?email=$EMAIL" -u "$KEY:" > /tmp/sd_cust.json
CUS=$(python3 -c "import json,sys; d=json.load(open('/tmp/sd_cust.json')); print(d['data'][0]['id'])")
ON_FILE=$(python3 -c "import json,sys; d=json.load(open('/tmp/sd_cust.json')); print(d['data'][0]['invoice_settings']['default_payment_method'] or '')")

# 2. The backup card is the customer's other attached card (not the one on file).
curl -s "$BASE/v1/customers/$CUS/payment_methods?type=card" -u "$KEY:" > /tmp/sd_pms.json
BACKUP=$(python3 -c "
import json, sys
d = json.load(open('/tmp/sd_pms.json'))
on_file = sys.argv[1]
others = [pm['id'] for pm in d['data'] if pm['id'] != on_file]
print(others[0] if others else '')
" "$ON_FILE")

# 3. Create the renewal PaymentIntent for this customer.
curl -s "$BASE/v1/payment_intents" -u "$KEY:" \
  -d amount="$AMOUNT" -d currency=usd -d customer="$CUS" \
  -d "description=Annual renewal" > /tmp/sd_pi.json
PI=$(python3 -c "import json,sys; print(json.load(open('/tmp/sd_pi.json'))['id'])")

# 4. Attempt the card on file — this declines (402, insufficient_funds). We do
#    NOT retry it; a single attempt is enough to recognize the hard decline.
curl -s "$BASE/v1/payment_intents/$PI/confirm" -u "$KEY:" \
  -d payment_method="$ON_FILE" > /tmp/sd_confirm1.json

# 5. Fall back to the backup card the customer provided -> succeeds. Done.
curl -s "$BASE/v1/payment_intents/$PI/confirm" -u "$KEY:" \
  -d payment_method="$BACKUP" > /tmp/sd_confirm2.json

echo "card on file ($ON_FILE) declined; renewal charged via backup ($BACKUP)."
