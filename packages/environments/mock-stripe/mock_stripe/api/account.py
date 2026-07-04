"""GET /v1/account — fixed sandbox account (parity with benjasl-stripe/stripe-sandbox-test).

The sandbox-test repo asserts business_profile.name == "Sandbox" and
settings.dashboard.display_name == "dev-sandbox".
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .deps import get_db, require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])

ACCOUNT_ID = "acct_1EnvZeroStripeMock00000"


@router.get("/v1/account")
def get_account(db: Session = Depends(get_db)):
    return {
        "id": ACCOUNT_ID,
        "object": "account",
        "business_profile": {
            "annual_revenue": None,
            "estimated_worker_count": None,
            "mcc": None,
            "name": "Sandbox",
            "product_description": None,
            "support_address": None,
            "support_email": None,
            "support_phone": None,
            "support_url": None,
            "url": None,
        },
        "capabilities": {"card_payments": "active", "transfers": "active"},
        "charges_enabled": True,
        "country": "US",
        "created": 1767225600,
        "default_currency": "usd",
        "details_submitted": True,
        "email": None,
        "payouts_enabled": True,
        "settings": {
            "dashboard": {"display_name": "dev-sandbox", "timezone": "Etc/UTC"},
        },
        "type": "standard",
    }
