"""Match bill payments to bills: candidates, proposals, auto-match and dismissals."""

import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.credit_card_bill import CreditCardBill
from app.models.transaction import Transaction
from app.services import bill_service

CENT = Decimal("0.01")
# BMATCH AC 3: a payment matches a bill from its close date until 5 days after
# its effective due date.
WINDOW_AFTER_DUE = timedelta(days=5)
# BMATCH AC 15: words that mark a payment as a bill payment.
HINT_WORDS = ("fatura", "cartao")

KIND_EXACT = "exact"
KIND_PARTIAL = "partial"
KIND_OTHER = "other"

REASON_EXACT = "exact_amount"
REASON_PARTIAL = "partial_amount"
REASON_ABOVE = "amount_above_remaining"
REASON_OUTSIDE = "outside_window"


@dataclass(frozen=True)
class Candidate:
    bill: CreditCardBill
    #: `exact` or `partial` inside the match window; `other` for the rest of
    #: the unpaid bills.
    kind: str
    reason: str
    #: 1-based position in the payment's list.
    rank: int
    #: Orders candidates of different payments for the same bill: lower is better.
    sort_key: tuple


def _amount(tx: Transaction) -> Decimal:
    return abs(Decimal(tx.amount)).quantize(CENT)


def _fold(text: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", (text or "").casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _has_hint(payment: Transaction, bill_payment_categories: set[uuid.UUID]) -> bool:
    """BMATCH AC 15: an `is_bill_payment` category or "fatura"/"cartão" in the description."""
    if payment.category_id is not None and payment.category_id in bill_payment_categories:
        return True
    description = _fold(payment.description)
    return any(word in description for word in HINT_WORDS)


def in_window(payment: Transaction, bill: CreditCardBill) -> bool:
    """BMATCH AC 3: the payment date is within `[close date, effective due date + 5 days]`."""
    return bill.close_date <= payment.date <= bill.effective_due_date + WINDOW_AFTER_DUE


def _remaining(bill: CreditCardBill) -> Decimal:
    return bill_service.bill_amounts(bill).remaining.quantize(CENT)


def rank_candidates(
    payment: Transaction,
    bills: Iterable[CreditCardBill],
    *,
    hinted: bool,
    dismissed: Iterable[uuid.UUID] = (),
) -> list[Candidate]:
    """The payment's unpaid bills, candidates first, best first.

    Bills paid in full, or in another currency, are left out. A bill whose
    pair the user dismissed is never a candidate again; it stays in `other`
    so the user can still pick it."""
    amount = _amount(payment)
    dismissed = set(dismissed)
    scored = []
    for bill in bills:
        if bill.currency != payment.currency:
            continue
        remaining = _remaining(bill)
        if remaining <= 0:
            continue
        if bill.id in dismissed or not in_window(payment, bill):
            kind, reason = KIND_OTHER, REASON_OUTSIDE
        elif remaining == amount:
            kind, reason = KIND_EXACT, REASON_EXACT
        elif amount < remaining:
            kind, reason = KIND_PARTIAL, REASON_PARTIAL
        else:
            # SPEC_DEVIATION: the spec names no kind for a payment above the
            # remaining amount. Reason: AC 3 makes it a candidate, so it is
            # listed with the candidates as `partial` (not auto-linked) and
            # its reason tells it apart.
            kind, reason = KIND_PARTIAL, REASON_ABOVE
        key = (
            {KIND_EXACT: 0, KIND_PARTIAL: 1, KIND_OTHER: 2}[kind],
            abs(remaining - amount),
            abs((payment.date - bill.effective_due_date).days),
            0 if hinted else 1,
            bill.effective_due_date,
            str(bill.id),
        )
        scored.append((key, bill, kind, reason))
    scored.sort(key=lambda item: item[0])
    return [
        Candidate(bill=bill, kind=kind, reason=reason, rank=index, sort_key=key)
        for index, (key, bill, kind, reason) in enumerate(scored, start=1)
    ]


async def eligible_payments(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    ids: Sequence[uuid.UUID] | None = None,
) -> list[Transaction]:
    """Posted, not ignored, positive debits of non-card accounts that pay no bill yet."""
    query = (
        select(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .where(
            Transaction.workspace_id == workspace_id,
            Account.type != "credit_card",
            Transaction.type == "debit",
            Transaction.status == "posted",
            Transaction.is_ignored.is_(False),
            Transaction.paid_bill_id.is_(None),
            Transaction.amount > 0,
            Transaction.source != "opening_balance",
        )
        .order_by(Transaction.date, Transaction.id)
    )
    if ids is not None:
        if not ids:
            return []
        query = query.where(Transaction.id.in_(list(ids)))
    return list((await session.execute(query)).scalars().all())


async def _workspace_bills(session: AsyncSession, workspace_id: uuid.UUID) -> list[CreditCardBill]:
    return list(
        (
            await session.execute(
                select(CreditCardBill).where(CreditCardBill.workspace_id == workspace_id)
            )
        ).scalars().all()
    )


async def _bill_payment_categories(session: AsyncSession, workspace_id: uuid.UUID) -> set[uuid.UUID]:
    rows = await session.execute(
        select(Category.id).where(
            Category.workspace_id == workspace_id, Category.is_bill_payment.is_(True)
        )
    )
    return {category_id for (category_id,) in rows}


async def candidates_for(session: AsyncSession, payment: Transaction) -> list[Candidate]:
    """The bills the payment may pay: window candidates first, then the other unpaid bills."""
    bills = await _workspace_bills(session, payment.workspace_id)
    categories = await _bill_payment_categories(session, payment.workspace_id)
    return rank_candidates(payment, bills, hinted=_has_hint(payment, categories))


# --- Proposals ---------------------------------------------------------------

#: The single exact pair of BMATCH AC 4; the only kind linked automatically.
PROPOSAL_EXACT = "exact"
#: BMATCH AC 5: the payment is below the remaining amount of its only candidate.
PROPOSAL_PARTIAL = "partial"
#: BMATCH AC 6: more than one bill or more than one payment qualifies.
PROPOSAL_SUGGESTION = "suggestion"


@dataclass(frozen=True)
class Proposal:
    payment: Transaction
    bill: CreditCardBill
    kind: str
    reason: str

    @property
    def payment_id(self) -> uuid.UUID:
        return self.payment.id

    @property
    def bill_id(self) -> uuid.UUID:
        return self.bill.id


@dataclass
class ApplyResult:
    linked: int = 0
    #: `(payment_id, bill_id, reason)` of every pair that was not linked.
    failed: list[tuple[uuid.UUID, uuid.UUID, str]] = field(default_factory=list)


def _proposals_for(
    candidates: dict[uuid.UUID, list[Candidate]], payments: Sequence[Transaction]
) -> list[Proposal]:
    """Classify each payment's window candidates (BMATCH AC 4-6)."""
    exact_payments: dict[uuid.UUID, int] = {}
    for listed in candidates.values():
        for c in listed:
            if c.kind == KIND_EXACT:
                exact_payments[c.bill.id] = exact_payments.get(c.bill.id, 0) + 1
    proposals: list[tuple[tuple, Proposal]] = []
    for payment in payments:
        inside = [c for c in candidates[payment.id] if c.kind != KIND_OTHER]
        if not inside:
            continue
        exact = [c for c in inside if c.kind == KIND_EXACT]
        if len(exact) == 1 and exact_payments[exact[0].bill.id] == 1:
            chosen = [(exact[0], PROPOSAL_EXACT)]
        elif len(inside) == 1 and inside[0].reason == REASON_PARTIAL:
            chosen = [(inside[0], PROPOSAL_PARTIAL)]
        else:
            chosen = [(c, PROPOSAL_SUGGESTION) for c in inside]
        for c, kind in chosen:
            proposals.append(
                ((payment.date, c.sort_key, str(payment.id)), Proposal(payment, c.bill, kind, c.reason))
            )
    proposals.sort(key=lambda item: item[0])
    return [proposal for _, proposal in proposals]


async def _candidates_by_payment(
    session: AsyncSession, workspace_id: uuid.UUID, payments: Sequence[Transaction]
) -> dict[uuid.UUID, list[Candidate]]:
    bills = await _workspace_bills(session, workspace_id)
    categories = await _bill_payment_categories(session, workspace_id)
    return {
        payment.id: rank_candidates(payment, bills, hinted=_has_hint(payment, categories))
        for payment in payments
    }


async def propose_matches(session: AsyncSession, workspace_id: uuid.UUID) -> list[Proposal]:
    """Every payment-bill pair worth proposing, without writing anything (BMATCH AC 10)."""
    payments = await eligible_payments(session, workspace_id)
    if not payments:
        return []
    candidates = await _candidates_by_payment(session, workspace_id, payments)
    return _proposals_for(candidates, payments)


async def run_auto_match(session: AsyncSession, workspace_id: uuid.UUID) -> int:
    """Link the unambiguous exact pairs (BMATCH AC 4); returns how many were linked.

    `link_payment` commits when it pairs the payment with the card credit."""
    from app.services import bill_payment_service  # local: circular

    linked = 0
    for proposal in await propose_matches(session, workspace_id):
        if proposal.kind != PROPOSAL_EXACT:
            continue
        try:
            await bill_payment_service.link_payment(
                session, workspace_id, proposal.payment_id, proposal.bill_id
            )
        except bill_payment_service.BillPaymentError:
            continue
        linked += 1
    return linked


async def apply_matches(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    pairs: Iterable[tuple[uuid.UUID, uuid.UUID]],
) -> ApplyResult:
    """Link the `(payment_id, bill_id)` pairs the user checked (BMATCH AC 11).

    A pair that cannot be linked is reported with its reason; the others land."""
    from app.services import bill_payment_service  # local: circular

    result = ApplyResult()
    for payment_id, bill_id in pairs:
        # SPEC_DEVIATION: design.md asks for a savepoint per pair. Reason:
        # `link_payment` commits when it pairs the card credit, which would end
        # the savepoint; it validates before writing anything instead, so a
        # refused pair leaves nothing behind.
        try:
            await bill_payment_service.link_payment(session, workspace_id, payment_id, bill_id)
        except bill_payment_service.BillPaymentError as exc:
            result.failed.append((payment_id, bill_id, exc.detail))
            continue
        result.linked += 1
    return result
