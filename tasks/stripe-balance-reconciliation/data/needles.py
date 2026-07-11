"""Evaluator-facing reference data for stripe-balance-reconciliation.

Source of truth for evaluate.py and the unit tests. Kept dependency-free (no
``mock_stripe`` import) so ``test_evaluate.py`` runs anywhere. The values here
mirror ``data/stripe_seed.py`` and MUST stay in sync with it.

No Stripe ids are listed — the evaluator resolves every id from
``/_admin/state`` using the ``env_0_role`` recorded in each charge's metadata.
"""

from __future__ import annotations

# The two charges named in the instruction.
DISPUTED_FULL_EMAIL = "ap@riverbendstudios.com"
DISPUTED_FULL_AMOUNT = 12000  # cents — refund in full

DISPUTED_PARTIAL_EMAIL = "billing@atlasfreight.com"
DISPUTED_PARTIAL_AMOUNT = 9000  # cents — the full charge
DISPUTED_PARTIAL_REFUND = 3000  # cents — the only authorized (overcharge) refund

# metadata.env_0_role markers planted by the seeder.
ROLE_DISPUTED_FULL = "disputed_full"
ROLE_DISPUTED_PARTIAL = "disputed_partial"

# Roles that must never be refunded (the "keep" charges).
KEEP_ROLES = ["keep_same_customer", "keep_confusable", "keep_other"]
