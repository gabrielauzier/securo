"""Shared setup for the `settlement` accounting mode tests (BREP-01, BREP-02).

The reference case of BREP AC 5-7: the 2026-09 bill of a card with close
day 5 and due day 12 (period 2026-08-05..2026-09-04, effective due date
2026-09-14) holds two August purchases, 600.00 in Mercado and 400.00 in
Restaurantes, for a 1,000.00 bill paid from a checking account.
"""

import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from app.core import app_clock
from app.models.account import Account
from app.models.category import Category
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.services import admin_service, bill_payment_service, bill_service
from app.services.credit_card_service import bill_period_for_month

AUG = date(2026, 8, 1)
SEP = date(2026, 9, 1)
OCT = date(2026, 10, 1)


def freeze_today(monkeypatch, today: date) -> None:
    """Pin `app_today` in every app module that imported it (again when re-pinned)."""

    def fake_today() -> date:
        return today

    fake_today.frozen = True  # type: ignore[attr-defined]
    original = app_clock.app_today
    for name, module in list(sys.modules.items()):
        if not name.startswith("app."):
            continue
        current = getattr(module, "app_today", None)
        if current is original or getattr(current, "frozen", False):
            monkeypatch.setattr(module, "app_today", fake_today)


async def set_mode(session, mode: str) -> None:
    await admin_service.set_app_setting(session, "credit_card_accounting_mode", mode)


def tx(account: Account, on: date, amount: str, *, type_="debit", **extra) -> Transaction:
    return Transaction(
        id=uuid.uuid4(), user_id=account.user_id, workspace_id=account.workspace_id,
        account_id=account.id, description=extra.pop("description", "row"),
        amount=Decimal(amount), amount_primary=Decimal(amount), currency="BRL",
        date=on, effective_date=extra.pop("effective_date", on), type=type_,
        source="manual", status="posted", created_at=datetime.now(timezone.utc), **extra,
    )


@dataclass
class Reference:
    card: Account
    checking: Account
    bill: CreditCardBill
    market: Category
    restaurants: Category
    market_purchase: Transaction
    restaurant_purchase: Transaction


async def seed_reference(session, user, workspace) -> Reference:
    market = Category(id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id, name="Mercado")
    restaurants = Category(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id, name="Restaurantes"
    )
    card = Account(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id,
        name="Cartão de Crédito Nubank", type="credit_card", currency="BRL",
        statement_close_day=5, payment_due_day=12,
    )
    checking = Account(
        id=uuid.uuid4(), user_id=user.id, workspace_id=workspace.id,
        name="Nubank", type="checking", currency="BRL",
    )
    session.add_all([market, restaurants, card, checking])
    await session.flush()
    bill, _ = await bill_service.get_or_create_bill(
        session, card, bill_period_for_month(SEP, 5, 12)
    )
    # accrual buckets by the nominal due date stamped on the row.
    due = date(2026, 9, 12)
    market_purchase = tx(
        card, date(2026, 8, 10), "600.00", category_id=market.id, bill_id=bill.id,
        effective_date=due,
    )
    restaurant_purchase = tx(
        card, date(2026, 8, 20), "400.00", category_id=restaurants.id, bill_id=bill.id,
        effective_date=due,
    )
    session.add_all([market_purchase, restaurant_purchase])
    await bill_service.refresh_bills(session, [bill.id])
    await session.commit()
    return Reference(
        card, checking, bill, market, restaurants, market_purchase, restaurant_purchase
    )


async def pay(session, ref: Reference, amount: str, on: date) -> Transaction:
    """Link a checking-account payment to the reference bill."""
    payment = tx(ref.checking, on, amount, description="Pagamento de fatura")
    session.add(payment)
    await session.flush()
    await bill_payment_service.link_payment(session, ref.checking.workspace_id, payment.id, ref.bill.id)
    await session.commit()
    await session.refresh(ref.bill)
    return payment


async def unpay(session, ref: Reference, payment: Transaction) -> None:
    await bill_payment_service.unlink_payment(session, ref.checking.workspace_id, payment.id)
    await session.commit()
    await session.refresh(ref.bill)
