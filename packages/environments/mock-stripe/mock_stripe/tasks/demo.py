"""Demo tasks for local debugging (independent of Docker tasks)."""

from __future__ import annotations

from dataclasses import dataclass

from .base import Task
from .registry import register_task


@dataclass
class RefundProWidgetTask(Task):
    """Refund the remaining balance of the Pro Widget charge."""

    def evaluate(self, final_state, diff, action_log):
        # The default seed leaves the 2500c "Pro Widget" charge with 500c
        # already refunded. Full completion = charge fully refunded.
        for ch in final_state.get("charges", []):
            if ch.get("description") == "Pro Widget":
                if ch.get("refunded") and ch.get("amount_refunded") == ch.get("amount"):
                    return 1.0, True
                return 0.0, False
        return 0.0, False


@dataclass
class CapturePendingHoldTask(Task):
    """Capture the outstanding requires_capture PaymentIntent."""

    def evaluate(self, final_state, diff, action_log):
        for pi in final_state.get("payment_intents", []):
            if pi.get("description") == "Hold for equipment rental":
                if pi.get("status") == "succeeded" and pi.get("amount_received", 0) > 0:
                    return 1.0, True
                return 0.0, False
        return 0.0, False


register_task(RefundProWidgetTask(
    name="refund-pro-widget",
    description="Fully refund the Pro Widget charge",
    instruction=(
        "A customer asked for a full refund on their 'Pro Widget' purchase. "
        "Part of it was already refunded. Refund the remaining amount via the API."
    ),
    category="capability",
    tags=["refunds"],
))

register_task(CapturePendingHoldTask(
    name="capture-pending-hold",
    description="Capture the uncaptured equipment-rental hold",
    instruction=(
        "There is an uncaptured PaymentIntent for an equipment rental hold. "
        "Capture the full amount."
    ),
    category="capability",
    tags=["payment_intents", "capture"],
))
