"""Seed the database with sample data for development.

Usage:
    python -m app.scripts.seed_data
    # or via Docker:
    docker compose exec api python -m app.scripts.seed_data
"""

import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext
from sqlalchemy import select

from app.core.database import async_session, engine
from app.models.base import Base
from app.models.transaction import RiskLevel, Transaction, TransactionType
from app.models.user import User, UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        # Create demo users
        existing = await db.execute(select(User).where(User.username == "admin"))
        if not existing.scalar_one_or_none():
            users = [
                User(
                    username="admin",
                    email="admin@fineract-aml.local",
                    full_name="AML Administrator",
                    hashed_password=pwd_context.hash("admin123"),
                    role=UserRole.ADMIN,
                ),
                User(
                    username="analyst1",
                    email="analyst1@fineract-aml.local",
                    full_name="Jane Smith",
                    hashed_password=pwd_context.hash("analyst123"),
                    role=UserRole.ANALYST,
                ),
                User(
                    username="senior_analyst",
                    email="senior@fineract-aml.local",
                    full_name="John Davis",
                    hashed_password=pwd_context.hash("senior123"),
                    role=UserRole.SENIOR_ANALYST,
                ),
            ]
            for u in users:
                db.add(u)
            print(f"Created {len(users)} users")

        # Generate sample transactions
        rng = random.Random(42)
        now = datetime.now(timezone.utc)
        accounts = [f"ACC-{i:03d}" for i in range(1, 21)]
        clients = [f"CLI-{i:03d}" for i in range(1, 16)]
        currencies = ["USD", "EUR", "XAF"]

        transactions = []
        for i in range(500):
            tx_type = rng.choice(list(TransactionType))
            amount = round(rng.lognormvariate(6, 2), 2)  # Log-normal: mostly small, some large
            amount = min(amount, 100000)

            # Inject some suspicious patterns
            if i % 50 == 0:
                amount = rng.uniform(9500, 9999)  # Structuring
            elif i % 70 == 0:
                amount = rng.choice([5000, 10000, 20000])  # Round numbers

            hours_ago = rng.uniform(0, 720)  # Last 30 days
            tx_date = now - timedelta(hours=hours_ago)

            # Some night transactions
            if i % 30 == 0:
                tx_date = tx_date.replace(hour=rng.randint(2, 5))

            tx = Transaction(
                fineract_transaction_id=f"FIN-TX-{uuid.uuid4().hex[:10].upper()}",
                fineract_account_id=rng.choice(accounts),
                fineract_client_id=rng.choice(clients),
                transaction_type=tx_type,
                amount=round(amount, 2),
                currency=rng.choice(currencies),
                transaction_date=tx_date,
                counterparty_account_id=(
                    rng.choice(accounts) if tx_type == TransactionType.TRANSFER else None
                ),
                description=rng.choice([
                    "Salary deposit",
                    "ATM withdrawal",
                    "Wire transfer",
                    "Mobile payment",
                    "Cash deposit",
                    "Loan repayment",
                    "Utility bill",
                    None,
                ]),
            )
            transactions.append(tx)
            db.add(tx)

        await db.commit()
        print(f"Created {len(transactions)} sample transactions")

        # Now run analysis on some transactions to generate alerts
        print("\nTo generate alerts, start the Celery worker and run:")
        print("  docker compose exec api python -m app.scripts.analyze_all")
        print("\nOr test the webhook with:")
        print('  curl -X POST http://localhost:8000/api/v1/webhook/fineract \\')
        print('    -H "Content-Type: application/json" \\')
        print('    -d \'{"transaction_id":"TEST-001","account_id":"ACC-001",')
        print('          "client_id":"CLI-001","transaction_type":"deposit",')
        print('          "amount":9800,"currency":"USD",')
        print('          "transaction_date":"2025-06-15T03:00:00Z"}\'')

    print("\nSeed complete!")
    print("Login credentials:")
    print("  admin / admin123")
    print("  analyst1 / analyst123")
    print("  senior_analyst / senior123")


if __name__ == "__main__":
    asyncio.run(seed())
