"""CLI commands for managing the application."""
import asyncio
import sys
import uuid

from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.user import User


async def generate_recurring() -> None:
    """Generate pending recurring transactions for all users."""
    from app.core.app_clock import use_timezone
    from app.models.user import User as UserModel
    from app.services import recurring_transaction_service

    async with async_session_maker() as session, use_timezone(session, fresh=True):
        result = await session.execute(select(UserModel))
        users = result.scalars().all()
        total = 0
        for user in users:
            count = await recurring_transaction_service.generate_pending(session, user.id)
            if count > 0:
                print(f"Generated {count} transactions for {user.email}")
                total += count
        print(f"Total generated: {total}")


async def rebuild_bills(workspace_id: uuid.UUID | None = None) -> None:
    """Relink every credit card's transactions to their bills and recompute
    the stored bill aggregates; repairs drift left by a missed write path."""
    from app.models.account import Account
    from app.models.credit_card_bill import CreditCardBill
    from app.services import bill_service

    async with async_session_maker() as session:
        query = select(Account).where(Account.type == "credit_card")
        if workspace_id is not None:
            query = query.where(Account.workspace_id == workspace_id)
        cards = (await session.execute(query)).scalars().all()
        linked = created = 0
        for card in cards:
            summary = await bill_service.link_account_transactions(session, card)
            linked += summary.linked
            created += summary.bills_created
        bill_ids = list(
            (
                await session.execute(
                    select(CreditCardBill.id).where(
                        CreditCardBill.account_id.in_([card.id for card in cards])
                    )
                )
            ).scalars()
        )
        await bill_service.refresh_bills(session, bill_ids)
        await session.commit()
        print(
            f"Rebuilt bills for {len(cards)} cards: {linked} transactions linked, "
            f"{created} bills created, {len(bill_ids)} bills refreshed"
        )


async def create_user(email: str, password: str) -> None:
    """Create a new user with the given email and password."""
    from pwdlib import PasswordHash

    hasher = PasswordHash.recommended()

    async with async_session_maker() as session:
        # Check if user already exists
        result = await session.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()
        if existing:
            print(f"Error: User with email '{email}' already exists.")
            sys.exit(1)

        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=hasher.hash(password),
            is_active=True,
            is_superuser=False,
            is_verified=True,
            preferences={
                "language": "pt-BR",
                "date_format": "DD/MM/YYYY",
                "timezone": "America/Sao_Paulo",
                "currency_display": "USD",
            },
        )
        session.add(user)
        await session.commit()
        print(f"User created successfully: {email}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m app.cli create-user <email> <password>")
        print("  python -m app.cli generate-recurring")
        print("  python -m app.cli rebuild-bills [--workspace <id>]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "create-user":
        if len(sys.argv) != 4:
            print("Usage: python -m app.cli create-user <email> <password>")
            sys.exit(1)
        email, password = sys.argv[2], sys.argv[3]
        asyncio.run(create_user(email, password))
    elif command == "generate-recurring":
        asyncio.run(generate_recurring())
    elif command == "rebuild-bills":
        args = sys.argv[2:]
        if args and not (len(args) == 2 and args[0] == "--workspace"):
            print("Usage: python -m app.cli rebuild-bills [--workspace <id>]")
            sys.exit(1)
        asyncio.run(rebuild_bills(uuid.UUID(args[1]) if args else None))
    else:
        print(f"Unknown command: {command}")
        print("Available commands: create-user, generate-recurring, rebuild-bills")
        sys.exit(1)


if __name__ == "__main__":
    main()
