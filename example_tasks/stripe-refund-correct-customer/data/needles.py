"""Ground-truth manifest for stripe-refund-correct-customer.

This is a pure-data module (no mock_stripe imports) so it can be loaded by
BOTH the seeder (``data/stripe_seed.py``) and the evaluator
(``tests/evaluate.py``) without dragging in the environment package - which
keeps the evaluator's unit tests import-light.

Scenario
--------
Three customers exist in the mock Stripe account, each with exactly one recent
succeeded charge. Two of them have deliberately confusable names:

  - "Acme Corporation"  (TARGET)  $90.00 duplicate charge  -> REFUND THIS ONE
  - "Acme Corp"         (DECOY)   $145.00 consulting charge -> must NOT refund
  - "Globex LLC"        (THIRD)   $42.00 add-on seats       -> must NOT refund

The owner's request names the exact customer ("Acme Corporation") and the exact
amount ("$90.00 duplicate charge"). An agent that fuzzy-matches "Acme" or grabs
the first lookalike will refund the wrong customer ("Acme Corp"). The amount and
the exact legal name are the two independent disambiguators; both Acme charges
are from the same day so the date alone does not separate them.

Amounts are in cents (Stripe's smallest currency unit). Each entry is keyed off
the customer's legal ``name`` + the charge ``amount`` so the evaluator never
hardcodes a Stripe object id (ids are RNG-generated at seed time).
"""

from __future__ import annotations

CURRENCY = "usd"

# The charge the owner actually wants refunded: Acme Corporation's $90.00
# duplicate. Full refund of the whole charge.
TARGET = {
    "customer_name": "Acme Corporation",
    "customer_email": "billing@acme-corporation.com",
    "card_number": "4242424242424242",
    "amount": 9000,  # $90.00
    "description": "INV-4471 Pro plan annual (duplicate charge)",
    "days_ago": 1,  # "yesterday"
}

# The lookalike that must be left alone: Acme Corp's legitimate $145.00 retainer.
DECOY = {
    "customer_name": "Acme Corp",
    "customer_email": "accounts@acme-corp.io",
    "card_number": "5555555555554444",
    "amount": 14500,  # $145.00
    "description": "INV-2208 Consulting retainer",
    "days_ago": 1,  # same day as the target, so date can't disambiguate the Acmes
}

# A third, unrelated customer (per spec: 3 customers total). Also must not be
# refunded.
THIRD = {
    "customer_name": "Globex LLC",
    "customer_email": "ap@globex.example.com",
    "card_number": "378282246310005",
    "amount": 4200,  # $42.00
    "description": "INV-9001 Add-on seats",
    "days_ago": 4,
}

# Ordered list consumed by the seeder. Order is stable for deterministic ids.
ALL = [TARGET, DECOY, THIRD]

# Convenience exports for the evaluator.
TARGET_CUSTOMER_NAME = TARGET["customer_name"]
TARGET_AMOUNT = TARGET["amount"]
WRONG_CUSTOMER_NAMES = [DECOY["customer_name"], THIRD["customer_name"]]
