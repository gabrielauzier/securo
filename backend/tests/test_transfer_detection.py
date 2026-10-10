"""Service-level tests for transfer_detection_service.

Tests: detect_transfer_pairs, unlink_transfer_pair.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import Transaction
from sqlalchemy import select

from app.models.reconciliation import ReconciliationSuggestion
from app.services import reconciliation_policy
from app.services import reconciliation_rule_service as rule_service
from app.services.transfer_detection_service import (
    apply_pairs,
    detect_transfer_pairs,
    propose_pairs,
    unlink_transfer_pair,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_account(
    session: AsyncSession, user_id: uuid.UUID, name: str,
) -> Account:
    account = Account(
        id=uuid.uuid4(), user_id=user_id, name=name,
        type="checking", balance=Decimal("0.00"), currency="BRL",
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


async def _add_txn(
    session: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID,
    amount: float, txn_type: str, txn_date: date,
    source: str = "manual",
) -> Transaction:
    from datetime import datetime, timezone
    txn = Transaction(
        id=uuid.uuid4(), user_id=user_id, account_id=account_id,
        description=f"Transfer {txn_type} {amount}",
        amount=Decimal(str(amount)), date=txn_date, type=txn_type,
        source=source, currency="BRL",
        created_at=datetime.now(timezone.utc),
    )
    session.add(txn)
    await session.commit()
    await session.refresh(txn)
    return txn


# ---------------------------------------------------------------------------
# detect_transfer_pairs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_basic_pair(session: AsyncSession, test_user, test_workspace):
    """Detects a simple debit-credit pair across two accounts."""
    acc1 = await _make_account(session, test_user.id, "Account A")
    acc2 = await _make_account(session, test_user.id, "Account B")
    today = date.today()

    debit = await _add_txn(session, test_user.id, acc1.id, 500, "debit", today)
    credit = await _add_txn(session, test_user.id, acc2.id, 500, "credit", today)

    pairs_created = await detect_transfer_pairs(session, test_workspace.id)
    await session.commit()
    assert pairs_created == 1

    # Reload and verify
    await session.refresh(debit)
    await session.refresh(credit)
    assert debit.transfer_pair_id is not None
    assert debit.transfer_pair_id == credit.transfer_pair_id


@pytest.mark.asyncio
async def test_detect_with_candidate_ids(session: AsyncSession, test_user, test_workspace):
    """Only considers candidate debits when candidate_ids is provided."""
    acc1 = await _make_account(session, test_user.id, "Cand A")
    acc2 = await _make_account(session, test_user.id, "Cand B")
    today = date.today()

    debit1 = await _add_txn(session, test_user.id, acc1.id, 100, "debit", today)
    debit2 = await _add_txn(session, test_user.id, acc1.id, 200, "debit", today)
    await _add_txn(session, test_user.id, acc2.id, 100, "credit", today)
    await _add_txn(session, test_user.id, acc2.id, 200, "credit", today)

    # Only consider debit1 as candidate
    pairs = await detect_transfer_pairs(session, test_workspace.id, candidate_ids=[debit1.id])
    await session.commit()
    assert pairs == 1

    await session.refresh(debit1)
    await session.refresh(debit2)
    assert debit1.transfer_pair_id is not None
    assert debit2.transfer_pair_id is None


@pytest.mark.asyncio
async def test_detect_no_debits(session: AsyncSession, test_user, test_workspace):
    """Returns 0 when there are no debits."""
    acc = await _make_account(session, test_user.id, "No Debits")
    await _add_txn(session, test_user.id, acc.id, 100, "credit", date.today())

    pairs = await detect_transfer_pairs(session, test_workspace.id)
    assert pairs == 0


@pytest.mark.asyncio
async def test_detect_no_credits(session: AsyncSession, test_user, test_workspace):
    """Returns 0 when there are no credits."""
    acc = await _make_account(session, test_user.id, "No Credits")
    await _add_txn(session, test_user.id, acc.id, 100, "debit", date.today())

    pairs = await detect_transfer_pairs(session, test_workspace.id)
    assert pairs == 0


@pytest.mark.asyncio
async def test_detect_respects_date_tolerance(session: AsyncSession, test_user, test_workspace):
    """Only pairs transactions inside the window the rules ask for.

    The window used to be an argument to this function and is now a
    condition on a rule somebody can read and change. Two days is what
    ships, and what this asserts, because the point of moving it was to
    keep the behaviour and expose the number.
    """
    acc1 = await _make_account(session, test_user.id, "Tol A")
    acc2 = await _make_account(session, test_user.id, "Tol B")
    today = date.today()

    await _add_txn(session, test_user.id, acc1.id, 300, "debit", today)
    # Credit too far away (5 days)
    await _add_txn(session, test_user.id, acc2.id, 300, "credit", today + timedelta(days=5))

    pairs = await detect_transfer_pairs(session, test_workspace.id)
    assert pairs == 0


@pytest.mark.asyncio
async def test_detect_within_tolerance(session: AsyncSession, test_user, test_workspace):
    """Pairs transactions within tolerance."""
    acc1 = await _make_account(session, test_user.id, "In Tol A")
    acc2 = await _make_account(session, test_user.id, "In Tol B")
    today = date.today()

    debit = await _add_txn(session, test_user.id, acc1.id, 400, "debit", today)
    credit = await _add_txn(session, test_user.id, acc2.id, 400, "credit", today + timedelta(days=1))

    pairs = await detect_transfer_pairs(session, test_workspace.id)
    await session.commit()
    assert pairs == 1

    await session.refresh(debit)
    await session.refresh(credit)
    assert debit.transfer_pair_id == credit.transfer_pair_id


@pytest.mark.asyncio
async def test_detect_ignores_same_account(session: AsyncSession, test_user, test_workspace):
    """Does not pair debit and credit in the same account."""
    acc = await _make_account(session, test_user.id, "Same Acc")
    today = date.today()

    await _add_txn(session, test_user.id, acc.id, 100, "debit", today)
    await _add_txn(session, test_user.id, acc.id, 100, "credit", today)

    pairs = await detect_transfer_pairs(session, test_workspace.id)
    assert pairs == 0


@pytest.mark.asyncio
async def test_detect_different_amounts_no_pair(session: AsyncSession, test_user, test_workspace):
    """Does not pair transactions with different amounts."""
    acc1 = await _make_account(session, test_user.id, "Diff A")
    acc2 = await _make_account(session, test_user.id, "Diff B")
    today = date.today()

    await _add_txn(session, test_user.id, acc1.id, 100, "debit", today)
    await _add_txn(session, test_user.id, acc2.id, 200, "credit", today)

    pairs = await detect_transfer_pairs(session, test_workspace.id)
    assert pairs == 0


@pytest.mark.asyncio
async def test_detect_excludes_opening_balance(session: AsyncSession, test_user, test_workspace):
    """Opening balance transactions are excluded from pairing."""
    acc1 = await _make_account(session, test_user.id, "OB A")
    acc2 = await _make_account(session, test_user.id, "OB B")
    today = date.today()

    await _add_txn(session, test_user.id, acc1.id, 1000, "debit", today, source="opening_balance")
    await _add_txn(session, test_user.id, acc2.id, 1000, "credit", today)

    pairs = await detect_transfer_pairs(session, test_workspace.id)
    assert pairs == 0


@pytest.mark.asyncio
async def test_detect_greedy_closest_date(session: AsyncSession, test_user, test_workspace):
    """Greedy matching picks the closest date first."""
    acc1 = await _make_account(session, test_user.id, "Greedy A")
    acc2 = await _make_account(session, test_user.id, "Greedy B")
    today = date.today()

    debit = await _add_txn(session, test_user.id, acc1.id, 500, "debit", today)
    await _add_txn(session, test_user.id, acc2.id, 500, "credit", today + timedelta(days=2))
    close_credit = await _add_txn(session, test_user.id, acc2.id, 500, "credit", today)

    pairs = await detect_transfer_pairs(session, test_workspace.id)
    await session.commit()
    assert pairs == 1

    await session.refresh(debit)
    await session.refresh(close_credit)
    assert debit.transfer_pair_id == close_credit.transfer_pair_id


# ---------------------------------------------------------------------------
# unlink_transfer_pair
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unlink_transfer_pair(session: AsyncSession, test_user, test_workspace):
    """Unlinks a transfer pair, clearing transfer_pair_id on both."""
    acc1 = await _make_account(session, test_user.id, "Unlink A")
    acc2 = await _make_account(session, test_user.id, "Unlink B")
    today = date.today()

    debit = await _add_txn(session, test_user.id, acc1.id, 250, "debit", today)
    credit = await _add_txn(session, test_user.id, acc2.id, 250, "credit", today)

    await detect_transfer_pairs(session, test_workspace.id)
    await session.commit()
    await session.refresh(debit)
    pair_id = debit.transfer_pair_id
    assert pair_id is not None

    unlinked = await unlink_transfer_pair(session, test_workspace.id,pair_id)
    await session.commit()
    assert unlinked == 2

    await session.refresh(debit)
    await session.refresh(credit)
    assert debit.transfer_pair_id is None
    assert credit.transfer_pair_id is None


@pytest.mark.asyncio
async def test_unlink_nonexistent_pair(session: AsyncSession, test_user, test_workspace):
    """Unlinking a nonexistent pair returns 0."""
    unlinked = await unlink_transfer_pair(session, test_workspace.id,uuid.uuid4())
    assert unlinked == 0


# ---------------------------------------------------------------------------
# Reverse-direction candidate_ids detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_candidate_credit_matches_existing_debit(session: AsyncSession, test_user, test_workspace):
    """When candidate_ids contains only a credit, it pairs with an existing debit.

    Simulates: Account A synced first (debit already exists), then Account B
    syncs and imports the matching credit.
    """
    acc1 = await _make_account(session, test_user.id, "Rev A")
    acc2 = await _make_account(session, test_user.id, "Rev B")
    today = date.today()

    # Existing debit (from a previous sync)
    debit = await _add_txn(session, test_user.id, acc1.id, 750, "debit", today)

    # New credit just imported
    credit = await _add_txn(session, test_user.id, acc2.id, 750, "credit", today)

    # Only the credit is in candidate_ids (second sync)
    pairs = await detect_transfer_pairs(session, test_workspace.id, candidate_ids=[credit.id])
    await session.commit()
    assert pairs == 1

    await session.refresh(debit)
    await session.refresh(credit)
    assert debit.transfer_pair_id is not None
    assert debit.transfer_pair_id == credit.transfer_pair_id


@pytest.mark.asyncio
async def test_candidate_debit_matches_existing_credit(session: AsyncSession, test_user, test_workspace):
    """When candidate_ids contains only a debit, it pairs with an existing credit.

    Simulates: Account B synced first (credit already exists), then Account A
    syncs and imports the matching debit.
    """
    acc1 = await _make_account(session, test_user.id, "Fwd A")
    acc2 = await _make_account(session, test_user.id, "Fwd B")
    today = date.today()

    # Existing credit (from a previous sync)
    credit = await _add_txn(session, test_user.id, acc2.id, 600, "credit", today)

    # New debit just imported
    debit = await _add_txn(session, test_user.id, acc1.id, 600, "debit", today)

    # Only the debit is in candidate_ids (second sync)
    pairs = await detect_transfer_pairs(session, test_workspace.id, candidate_ids=[debit.id])
    await session.commit()
    assert pairs == 1

    await session.refresh(debit)
    await session.refresh(credit)
    assert debit.transfer_pair_id is not None
    assert debit.transfer_pair_id == credit.transfer_pair_id


@pytest.mark.asyncio
async def test_reverse_detection_does_not_pair_two_old_transactions(session: AsyncSession, test_user, test_workspace):
    """Reverse detection must not pair two transactions that are both outside candidate_ids."""
    acc1 = await _make_account(session, test_user.id, "Guard A")
    acc2 = await _make_account(session, test_user.id, "Guard B")
    acc3 = await _make_account(session, test_user.id, "Guard C")
    today = date.today()

    # Two old unpaired transactions that could match each other
    old_debit = await _add_txn(session, test_user.id, acc1.id, 300, "debit", today)
    old_credit = await _add_txn(session, test_user.id, acc2.id, 300, "credit", today)

    # A new unrelated credit (different amount) triggers detection
    new_credit = await _add_txn(session, test_user.id, acc3.id, 999, "credit", today)

    pairs = await detect_transfer_pairs(session, test_workspace.id, candidate_ids=[new_credit.id])
    await session.commit()
    assert pairs == 0

    # Old transactions must remain unpaired
    await session.refresh(old_debit)
    await session.refresh(old_credit)
    assert old_debit.transfer_pair_id is None
    assert old_credit.transfer_pair_id is None


@pytest.mark.asyncio
async def test_both_sides_imported_together(session: AsyncSession, test_user, test_workspace):
    """When both debit and credit are new (same sync), both are in candidate_ids."""
    acc1 = await _make_account(session, test_user.id, "Both A")
    acc2 = await _make_account(session, test_user.id, "Both B")
    today = date.today()

    debit = await _add_txn(session, test_user.id, acc1.id, 200, "debit", today)
    credit = await _add_txn(session, test_user.id, acc2.id, 200, "credit", today)

    pairs = await detect_transfer_pairs(
        session, test_workspace.id, candidate_ids=[debit.id, credit.id],
    )
    await session.commit()
    assert pairs == 1

    await session.refresh(debit)
    await session.refresh(credit)
    assert debit.transfer_pair_id == credit.transfer_pair_id


# ---------------------------------------------------------------------------
# propose_pairs (TRF-01 ACs 1, 2, 5, 7; BTR-01 ACs 2-5)
# ---------------------------------------------------------------------------


async def _suggestion_count(session: AsyncSession) -> int:
    return len((await session.execute(select(ReconciliationSuggestion))).scalars().all())


@pytest.mark.asyncio
async def test_propose_rule_wide_lists_the_mutual_pair_and_writes_nothing(
    session: AsyncSession, test_user, test_workspace
):
    acc1 = await _make_account(session, test_user.id, "Prop A")
    acc2 = await _make_account(session, test_user.id, "Prop B")
    today = date.today()
    debit = await _add_txn(session, test_user.id, acc1.id, 500, "debit", today)
    credit = await _add_txn(session, test_user.id, acc2.id, 500, "credit", today)

    result = await propose_pairs(session, test_workspace.id)

    assert len(result.pairs) == 1
    assert {result.pairs[0].a.id, result.pairs[0].b.id} == {debit.id, credit.id}
    await session.refresh(debit)
    await session.refresh(credit)
    assert debit.transfer_pair_id is None
    assert credit.transfer_pair_id is None
    assert await _suggestion_count(session) == 0


@pytest.mark.asyncio
async def test_propose_pair_carries_both_legs_and_the_strategy(
    session: AsyncSession, test_user, test_workspace
):
    acc1 = await _make_account(session, test_user.id, "Legs A")
    acc2 = await _make_account(session, test_user.id, "Legs B")
    today = date.today()
    debit = await _add_txn(session, test_user.id, acc1.id, 500, "debit", today)
    credit = await _add_txn(session, test_user.id, acc2.id, 500, "credit", today)

    pair = (await propose_pairs(session, test_workspace.id)).pairs[0]

    assert (pair.a.id, pair.a.date, pair.a.account_id, pair.a.account_name) == (
        debit.id, today, acc1.id, "Legs A",
    )
    assert (pair.b.id, pair.b.date, pair.b.account_id, pair.b.account_name) == (
        credit.id, today, acc2.id, "Legs B",
    )
    assert pair.a.description == debit.description
    assert pair.a.amount == Decimal("500")
    assert pair.b.amount == Decimal("500")
    assert pair.strategy in {
        s["id"] for s in reconciliation_policy.MATCH_TRANSFER["strategies"]
    }


@pytest.mark.asyncio
async def test_propose_rule_wide_skips_ambiguous_and_records_no_suggestion(
    session: AsyncSession, test_user, test_workspace
):
    acc1 = await _make_account(session, test_user.id, "Amb A")
    acc2 = await _make_account(session, test_user.id, "Amb B")
    acc3 = await _make_account(session, test_user.id, "Amb C")
    today = date.today()
    await _add_txn(session, test_user.id, acc1.id, 80, "debit", today)
    await _add_txn(session, test_user.id, acc2.id, 80, "debit", today)
    await _add_txn(session, test_user.id, acc3.id, 80, "credit", today)

    result = await propose_pairs(session, test_workspace.id)

    assert result.pairs == []
    assert await _suggestion_count(session) == 0


@pytest.mark.asyncio
async def test_propose_returns_empty_when_every_strategy_is_disabled(
    session: AsyncSession, test_user, test_workspace
):
    node = reconciliation_policy.MATCH_TRANSFER["node"]
    for strategy in reconciliation_policy.MATCH_TRANSFER["strategies"]:
        await rule_service.upsert_override(
            session, test_workspace.id, test_user.id, node, strategy["id"],
            {"enabled": False},
        )
    await session.commit()
    acc1 = await _make_account(session, test_user.id, "Off A")
    acc2 = await _make_account(session, test_user.id, "Off B")
    today = date.today()
    debit = await _add_txn(session, test_user.id, acc1.id, 50, "debit", today)
    credit = await _add_txn(session, test_user.id, acc2.id, 50, "credit", today)

    for restrict in (None, {debit.id, credit.id}):
        result = await propose_pairs(session, test_workspace.id, restrict)
        assert (result.pairs, result.ambiguous, result.unmatched, result.already_linked) == (
            [], [], [], [],
        )


@pytest.mark.asyncio
async def test_propose_restricted_pairs_the_selection_and_reports_the_stray(
    session: AsyncSession, test_user, test_workspace
):
    acc1 = await _make_account(session, test_user.id, "Sel A")
    acc2 = await _make_account(session, test_user.id, "Sel B")
    today = date.today()
    debit = await _add_txn(session, test_user.id, acc1.id, 120, "debit", today)
    credit = await _add_txn(session, test_user.id, acc2.id, 120, "credit", today)
    stray = await _add_txn(session, test_user.id, acc1.id, 999, "debit", today)

    result = await propose_pairs(
        session, test_workspace.id, {debit.id, credit.id, stray.id}
    )

    assert len(result.pairs) == 1
    assert {result.pairs[0].a.id, result.pairs[0].b.id} == {debit.id, credit.id}
    assert result.unmatched == [stray.id]
    assert result.ambiguous == []
    assert result.already_linked == []


@pytest.mark.asyncio
async def test_propose_restricted_does_not_pair_selected_rows_outside_the_rule_window(
    session: AsyncSession, test_user, test_workspace
):
    """BTR AC1: the window comes from the transfer rule, also for a selection (2 days ships)."""
    acc1 = await _make_account(session, test_user.id, "Win A")
    acc2 = await _make_account(session, test_user.id, "Win B")
    today = date.today()
    debit = await _add_txn(session, test_user.id, acc1.id, 300, "debit", today)
    credit = await _add_txn(session, test_user.id, acc2.id, 300, "credit", today + timedelta(days=5))

    result = await propose_pairs(session, test_workspace.id, {debit.id, credit.id})

    assert result.pairs == []
    assert set(result.unmatched) == {debit.id, credit.id}


@pytest.mark.asyncio
async def test_propose_restricted_does_not_pair_selected_rows_outside_the_amount_tolerance(
    session: AsyncSession, test_user, test_workspace
):
    """BTR AC1: the amount tolerance comes from the transfer rule, also for a selection."""
    acc1 = await _make_account(session, test_user.id, "Amt A")
    acc2 = await _make_account(session, test_user.id, "Amt B")
    today = date.today()
    debit = await _add_txn(session, test_user.id, acc1.id, 100, "debit", today)
    credit = await _add_txn(session, test_user.id, acc2.id, 150, "credit", today)

    result = await propose_pairs(session, test_workspace.id, {debit.id, credit.id})

    assert result.pairs == []
    assert set(result.unmatched) == {debit.id, credit.id}


@pytest.mark.asyncio
async def test_propose_restricted_never_uses_a_counterpart_outside_the_selection(
    session: AsyncSession, test_user, test_workspace
):
    acc1 = await _make_account(session, test_user.id, "Out A")
    acc2 = await _make_account(session, test_user.id, "Out B")
    today = date.today()
    debit = await _add_txn(session, test_user.id, acc1.id, 70, "debit", today)
    await _add_txn(session, test_user.id, acc2.id, 70, "credit", today)

    result = await propose_pairs(session, test_workspace.id, {debit.id})

    assert result.pairs == []
    assert result.unmatched == [debit.id]


@pytest.mark.asyncio
async def test_propose_restricted_reports_a_contested_counterpart_as_ambiguous(
    session: AsyncSession, test_user, test_workspace
):
    acc1 = await _make_account(session, test_user.id, "Con A")
    acc2 = await _make_account(session, test_user.id, "Con B")
    acc3 = await _make_account(session, test_user.id, "Con C")
    today = date.today()
    d1 = await _add_txn(session, test_user.id, acc1.id, 90, "debit", today)
    d2 = await _add_txn(session, test_user.id, acc2.id, 90, "debit", today)
    credit = await _add_txn(session, test_user.id, acc3.id, 90, "credit", today)

    result = await propose_pairs(
        session, test_workspace.id, {d1.id, d2.id, credit.id}
    )

    assert result.pairs == []
    assert set(result.ambiguous) == {d1.id, d2.id, credit.id}
    assert result.unmatched == []


@pytest.mark.asyncio
async def test_propose_restricted_lists_already_linked_rows_and_leaves_them(
    session: AsyncSession, test_user, test_workspace
):
    acc1 = await _make_account(session, test_user.id, "Lnk A")
    acc2 = await _make_account(session, test_user.id, "Lnk B")
    today = date.today()
    debit = await _add_txn(session, test_user.id, acc1.id, 60, "debit", today)
    credit = await _add_txn(session, test_user.id, acc2.id, 60, "credit", today)
    pair_id = uuid.uuid4()
    debit.transfer_pair_id = pair_id
    credit.transfer_pair_id = pair_id
    await session.commit()

    result = await propose_pairs(session, test_workspace.id, {debit.id, credit.id})

    assert set(result.already_linked) == {debit.id, credit.id}
    assert result.pairs == []
    assert result.unmatched == []
    await session.refresh(debit)
    assert debit.transfer_pair_id == pair_id


# ---------------------------------------------------------------------------
# apply_pairs (TRF-01 ACs 3, 4, 7; BTR-01 AC 6)
# ---------------------------------------------------------------------------


async def _mirrored(session, user, name: str, amount: float = 100):
    acc1 = await _make_account(session, user.id, f"{name} A")
    acc2 = await _make_account(session, user.id, f"{name} B")
    today = date.today()
    debit = await _add_txn(session, user.id, acc1.id, amount, "debit", today)
    credit = await _add_txn(session, user.id, acc2.id, amount, "credit", today)
    return debit, credit


@pytest.mark.asyncio
async def test_apply_links_the_requested_pairs_and_returns_the_count(
    session: AsyncSession, test_user, test_workspace
):
    d1, c1 = await _mirrored(session, test_user, "Ap1", 100)
    d2, c2 = await _mirrored(session, test_user, "Ap2", 250)

    result = await apply_pairs(
        session, test_workspace.id, [(d1.id, c1.id), (d2.id, c2.id)]
    )
    await session.commit()

    assert result.linked == 2
    assert result.skipped == []
    for tx in (d1, c1, d2, c2):
        await session.refresh(tx)
    assert d1.transfer_pair_id is not None
    assert d1.transfer_pair_id == c1.transfer_pair_id
    assert d2.transfer_pair_id == c2.transfer_pair_id
    assert d1.transfer_pair_id != d2.transfer_pair_id


@pytest.mark.asyncio
async def test_apply_links_a_rule_wide_pair_even_if_an_unselected_row_now_contests_a_leg(
    session: AsyncSession, test_user, test_workspace
):
    """Documented rule (spec Assumptions, "Rule-wide apply revalidation"): apply only
    revalidates against the posted ids, so a row added after the preview that also
    mirrors a leg does not block a pair the user confirmed."""
    debit, credit = await _mirrored(session, test_user, "Contest", 100)
    other = await _make_account(session, test_user.id, "Contest C")
    contender = await _add_txn(session, test_user.id, other.id, 100, "debit", date.today())

    result = await apply_pairs(session, test_workspace.id, [(debit.id, credit.id)])
    await session.commit()

    assert result.linked == 1
    assert result.skipped == []
    await session.refresh(debit)
    await session.refresh(credit)
    await session.refresh(contender)
    assert debit.transfer_pair_id is not None
    assert debit.transfer_pair_id == credit.transfer_pair_id
    assert contender.transfer_pair_id is None


@pytest.mark.asyncio
async def test_apply_skips_a_pair_whose_leg_was_linked_since_the_preview(
    session: AsyncSession, test_user, test_workspace
):
    debit, credit = await _mirrored(session, test_user, "Stale")
    elsewhere = uuid.uuid4()
    credit.transfer_pair_id = elsewhere
    await session.commit()

    result = await apply_pairs(session, test_workspace.id, [(debit.id, credit.id)])
    await session.commit()

    assert result.linked == 0
    assert [(s.a, s.b) for s in result.skipped] == [(debit.id, credit.id)]
    await session.refresh(debit)
    await session.refresh(credit)
    assert debit.transfer_pair_id is None
    assert credit.transfer_pair_id == elsewhere


@pytest.mark.asyncio
async def test_apply_skips_a_pair_whose_leg_was_deleted_since_the_preview(
    session: AsyncSession, test_user, test_workspace
):
    d1, c1 = await _mirrored(session, test_user, "Del1", 100)
    d2, c2 = await _mirrored(session, test_user, "Del2", 300)
    await session.delete(c1)
    await session.commit()

    result = await apply_pairs(
        session, test_workspace.id, [(d1.id, c1.id), (d2.id, c2.id)]
    )
    await session.commit()

    assert result.linked == 1
    assert [(s.a, s.b) for s in result.skipped] == [(d1.id, c1.id)]
    await session.refresh(d2)
    assert d2.transfer_pair_id is not None


@pytest.mark.asyncio
async def test_apply_rejects_a_forged_pair_the_rule_would_not_propose(
    session: AsyncSession, test_user, test_workspace
):
    d1, _c1 = await _mirrored(session, test_user, "Forge1", 100)
    _d2, c2 = await _mirrored(session, test_user, "Forge2", 777)

    result = await apply_pairs(session, test_workspace.id, [(d1.id, c2.id)])
    await session.commit()

    assert result.linked == 0
    assert [(s.a, s.b, s.reason) for s in result.skipped] == [
        (d1.id, c2.id, "not_proposed")
    ]
    await session.refresh(d1)
    await session.refresh(c2)
    assert d1.transfer_pair_id is None
    assert c2.transfer_pair_id is None


@pytest.mark.asyncio
async def test_apply_records_no_suggestions(
    session: AsyncSession, test_user, test_workspace
):
    d1, c1 = await _mirrored(session, test_user, "NoSug1", 100)
    acc3 = await _make_account(session, test_user.id, "NoSug3")
    # A second credit of the same size makes the first pair contested
    # elsewhere, which is exactly what would be recorded as a suggestion
    # by the detector.
    await _add_txn(session, test_user.id, acc3.id, 100, "credit", date.today())

    await apply_pairs(session, test_workspace.id, [(d1.id, c1.id)])
    await session.commit()

    assert await _suggestion_count(session) == 0


@pytest.mark.asyncio
async def test_apply_links_a_leg_only_once_when_requested_twice(
    session: AsyncSession, test_user, test_workspace
):
    debit, credit = await _mirrored(session, test_user, "Twice")

    result = await apply_pairs(
        session, test_workspace.id,
        [(debit.id, credit.id), (credit.id, debit.id)],
    )
    await session.commit()

    assert result.linked == 1
    assert len(result.skipped) == 1
