"""Stripe documented test cards and virtual PaymentMethod tokens.

Sources: https://docs.stripe.com/testing (decline tables copied verbatim into
the ground-truth report). Virtual tokens like `pm_card_visa` are usable
anywhere a payment method is expected without prior creation — the mock
materializes a fresh concrete `pm_...` row when one is referenced.
"""

from __future__ import annotations

import hashlib

# number -> (brand, funding)
_SUCCESS_CARDS: dict[str, tuple[str, str]] = {
    "4242424242424242": ("visa", "credit"),
    "4000056655665556": ("visa", "debit"),
    "5555555555554444": ("mastercard", "credit"),
    "2223003122003222": ("mastercard", "credit"),
    "5200828282828210": ("mastercard", "debit"),
    "5105105105105100": ("mastercard", "prepaid"),
    "378282246310005": ("amex", "credit"),
    "371449635398431": ("amex", "credit"),
    "6011111111111117": ("discover", "credit"),
    "3056930009020004": ("diners", "credit"),
    "3566002020360505": ("jcb", "credit"),
    "6200000000000005": ("unionpay", "credit"),
}

# Decline card numbers: number -> (failure_code, decline_code|None, message)
# These create fine but fail when used to confirm a PaymentIntent.
_DECLINE_CARDS: dict[str, tuple[str, str | None, str]] = {
    "4000000000000002": ("card_declined", "generic_decline", "Your card was declined."),
    "4000000000009995": ("card_declined", "insufficient_funds", "Your card has insufficient funds."),
    "4000000000009987": ("card_declined", "lost_card", "Your card was declined."),
    "4000000000009979": ("card_declined", "stolen_card", "Your card was declined."),
    "4000000000000069": ("expired_card", None, "Your card has expired."),
    "4000000000000127": ("incorrect_cvc", None, "Your card's security code is incorrect."),
    "4000000000000119": (
        "processing_error",
        None,
        "An error occurred while processing your card. Try again in a little bit.",
    ),
    "4000000000006975": (
        "card_declined",
        "card_velocity_exceeded",
        "Your card was declined for making repeated attempts too frequently or exceeding its amount limit.",
    ),
    # Attach succeeds, charges fail (generic decline at charge time).
    "4000000000000341": ("card_declined", "generic_decline", "Your card was declined."),
}

# Card number that fails at PaymentMethod creation time.
INCORRECT_NUMBER = "4242424242424241"

# 3DS/SCA cards (docs.stripe.com/testing "Test 3D Secure authentication"):
# confirming a PaymentIntent with one of these yields status=requires_action
# with a populated next_action; nothing is charged until authentication
# completes (mock: POST /v1/payment_intents/{id}/_complete_authentication).
# 4000002500003155 is "authenticate unless set up" — the mock has no
# SetupIntents, so it always requires authentication (documented divergence).
_AUTH_REQUIRED_CARDS: set[str] = {
    "4000002760003184",  # always requires authentication
    "4000002500003155",  # requires authentication unless set up for future payments
}

# Virtual PaymentMethod tokens -> backing card number.
PM_TOKENS: dict[str, str] = {
    "pm_card_visa": "4242424242424242",
    "pm_card_visa_debit": "4000056655665556",
    "pm_card_mastercard": "5555555555554444",
    "pm_card_mastercard_debit": "5200828282828210",
    "pm_card_mastercard_prepaid": "5105105105105100",
    "pm_card_amex": "378282246310005",
    "pm_card_discover": "6011111111111117",
    "pm_card_diners": "3056930009020004",
    "pm_card_jcb": "3566002020360505",
    "pm_card_unionpay": "6200000000000005",
    # Declines — current docs spell most with a `_visa_` infix; older docs used
    # bare `pm_card_chargeDeclined*`. Both spellings are accepted.
    "pm_card_chargeDeclined": "4000000000000002",
    "pm_card_visa_chargeDeclined": "4000000000000002",
    "pm_card_chargeDeclinedInsufficientFunds": "4000000000009995",
    "pm_card_visa_chargeDeclinedInsufficientFunds": "4000000000009995",
    "pm_card_chargeDeclinedLostCard": "4000000000009987",
    "pm_card_visa_chargeDeclinedLostCard": "4000000000009987",
    "pm_card_chargeDeclinedStolenCard": "4000000000009979",
    "pm_card_visa_chargeDeclinedStolenCard": "4000000000009979",
    "pm_card_chargeDeclinedExpiredCard": "4000000000000069",
    "pm_card_chargeDeclinedIncorrectCvc": "4000000000000127",
    "pm_card_chargeDeclinedProcessingError": "4000000000000119",
    "pm_card_visa_chargeDeclinedVelocityLimitExceeded": "4000000000006975",
    "pm_card_chargeCustomerFail": "4000000000000341",
    # 3DS / SCA (docs: "Always authenticate" / "Authenticate unless set up")
    "pm_card_authenticationRequired": "4000002760003184",
    "pm_card_authenticationRequiredOnSetup": "4000002500003155",
}

# Legacy `tok_` tokens accepted in card[token]= — same backing numbers.
TOK_TOKENS: dict[str, str] = {
    "tok_visa": "4242424242424242",
    "tok_visa_debit": "4000056655665556",
    "tok_mastercard": "5555555555554444",
    "tok_mastercard_debit": "5200828282828210",
    "tok_mastercard_prepaid": "5105105105105100",
    "tok_amex": "378282246310005",
    "tok_discover": "6011111111111117",
    "tok_diners": "3056930009020004",
    "tok_jcb": "3566002020360505",
    "tok_unionpay": "6200000000000005",
    "tok_visa_chargeDeclined": "4000000000000002",
    "tok_visa_chargeDeclinedInsufficientFunds": "4000000000009995",
    "tok_visa_chargeDeclinedLostCard": "4000000000009987",
    "tok_visa_chargeDeclinedStolenCard": "4000000000009979",
    "tok_chargeDeclinedExpiredCard": "4000000000000069",
    "tok_chargeDeclinedIncorrectCvc": "4000000000000127",
    "tok_chargeDeclinedProcessingError": "4000000000000119",
    "tok_visa_chargeDeclinedVelocityLimitExceeded": "4000000000006975",
}


def fingerprint_for(number: str) -> str:
    """Deterministic 16-char alnum fingerprint per card number (like Stripe's)."""
    digest = hashlib.sha256(number.encode()).hexdigest()
    return digest[:16]


def brand_for(number: str) -> str:
    """Infer brand from the leading digits (good enough for test cards)."""
    if number.startswith("4"):
        return "visa"
    if number[:2] in {"51", "52", "53", "54", "55"} or number[:2] in {"22", "23", "24", "25", "26", "27"}:
        return "mastercard"
    if number[:2] in {"34", "37"}:
        return "amex"
    if number.startswith("6011") or number.startswith("65"):
        return "discover"
    if number[:2] in {"30", "36", "38"}:
        return "diners"
    if number.startswith("35"):
        return "jcb"
    if number.startswith("62"):
        return "unionpay"
    return "unknown"


def spec_for_number(number: str) -> dict:
    """Full card spec for a number: brand/funding/last4/fingerprint + decline behavior."""
    if number in _SUCCESS_CARDS:
        brand, funding = _SUCCESS_CARDS[number]
        failure = None
    elif number in _DECLINE_CARDS:
        brand, funding = brand_for(number), "credit"
        failure = _DECLINE_CARDS[number]
    else:
        brand, funding = brand_for(number), "credit"
        failure = None
    spec = {
        "brand": brand,
        "funding": funding,
        "last4": number[-4:],
        "fingerprint": fingerprint_for(number),
        "country": "US",
        "failure_code": None,
        "decline_code": None,
        "failure_message": None,
        "authentication_required": number in _AUTH_REQUIRED_CARDS,
    }
    if failure:
        spec["failure_code"], spec["decline_code"], spec["failure_message"] = failure
    return spec


def spec_for_token(token: str) -> dict | None:
    """Spec for a virtual pm_/tok_ token, or None if unknown."""
    number = PM_TOKENS.get(token) or TOK_TOKENS.get(token)
    if number is None:
        return None
    return spec_for_number(number)


def is_virtual_pm(pm_id: str) -> bool:
    return pm_id in PM_TOKENS
