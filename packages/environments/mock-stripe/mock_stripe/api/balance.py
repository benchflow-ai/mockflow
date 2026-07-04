"""Balance + BalanceTransactions.

Balance is computed from balance transactions: available = sum(net) per
currency. The mock makes funds available immediately (no pending window),
so `pending` is always 0 per currency — documented in API_NOTES.md.
"""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from mock_stripe.models import BalanceTransaction

from .deps import get_db, require_api_key
from .errors import resource_missing
from .forms import parse_query
from .pagination import apply_created_filter, paginate
from .serializers import balance_transaction_to_dict

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/v1/balance")
def get_balance(db: Session = Depends(get_db)):
    txns = db.query(BalanceTransaction).all()
    per_currency: dict[str, int] = defaultdict(int)
    for t in txns:
        per_currency[t.currency] += t.net
    currencies = sorted(per_currency) or ["usd"]
    return {
        "object": "balance",
        "available": [
            {
                "amount": per_currency[c],
                "currency": c,
                "source_types": {"card": per_currency[c]},
            }
            for c in currencies
        ],
        "connect_reserved": [{"amount": 0, "currency": c} for c in currencies],
        "livemode": False,
        "pending": [
            {"amount": 0, "currency": c, "source_types": {"card": 0}}
            for c in currencies
        ],
    }


@router.get("/v1/balance_transactions")
def list_balance_transactions(request: Request, db: Session = Depends(get_db)):
    params = parse_query(request)
    items = db.query(BalanceTransaction).order_by(BalanceTransaction.seq.desc()).all()
    if params.get("type"):
        items = [t for t in items if t.type == params["type"]]
    if params.get("currency"):
        items = [t for t in items if t.currency == str(params["currency"]).lower()]
    if params.get("source"):
        items = [t for t in items if t.source_id == params["source"]]
    items = apply_created_filter(items, params)
    return paginate(
        items, params, "/v1/balance_transactions",
        balance_transaction_to_dict, kind="balance_transaction",
    )


@router.get("/v1/balance_transactions/{txn_id}")
def get_balance_transaction(txn_id: str, db: Session = Depends(get_db)):
    txn = db.get(BalanceTransaction, txn_id)
    if txn is None:
        raise resource_missing("balance_transaction", txn_id)
    return balance_transaction_to_dict(txn)
