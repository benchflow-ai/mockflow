"""Minimal web dashboard: customers + recent payments table at /."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from mock_stripe.api.deps import get_db
from mock_stripe.models import BalanceTransaction, Charge, Customer, PaymentIntent

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _fmt_amount(amount: int, currency: str) -> str:
    return f"{amount / 100:.2f} {currency.upper()}"


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    customers = db.query(Customer).filter(Customer.deleted == False).order_by(Customer.seq.desc()).all()  # noqa: E712
    if not customers and db.query(PaymentIntent).count() == 0:
        return HTMLResponse(
            "<h1>Mock Stripe</h1><p>No data. Run <code>mock-stripe seed</code> first.</p>"
        )
    intents = db.query(PaymentIntent).order_by(PaymentIntent.seq.desc()).limit(20).all()
    charges = db.query(Charge).order_by(Charge.seq.desc()).limit(20).all()
    available = sum(t.net for t in db.query(BalanceTransaction).all())
    customer_names = {c.id: (c.name or c.email or c.id) for c in customers}
    return templates.TemplateResponse(
        request,
        "index.html",
        context={
            "customers": customers,
            "intents": intents,
            "charges": charges,
            "available": available,
            "customer_names": customer_names,
            "fmt": _fmt_amount,
        },
    )
