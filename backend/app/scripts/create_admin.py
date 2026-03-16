"""Create the initial admin user for the AML dashboard.

Usage:
    python -m app.scripts.create_admin
    # or via Docker:
    docker compose exec api python -m app.scripts.create_admin
"""

import asyncio
import getpass
import sys

from passlib.context import CryptContext
from sqlalchemy import select

from app.core.database import async_session, engine
from app.models.base import Base
from app.models.user import User, UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def create_admin():
    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("=== Create Admin User ===\n")

    username = input("Username [admin]: ").strip() or "admin"
    email = input("Email [admin@fineract-aml.local]: ").strip() or "admin@fineract-aml.local"
    full_name = input("Full name [AML Administrator]: ").strip() or "AML Administrator"
    password = getpass.getpass("Password: ")

    if not password:
        print("Error: password cannot be empty")
        sys.exit(1)

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Error: passwords do not match")
        sys.exit(1)

    async with async_session() as db:
        # Check if user exists
        existing = await db.execute(select(User).where(User.username == username))
        if existing.scalar_one_or_none():
            print(f"Error: user '{username}' already exists")
            sys.exit(1)

        user = User(
            username=username,
            email=email,
            full_name=full_name,
            hashed_password=pwd_context.hash(password),
            role=UserRole.ADMIN,
        )
        db.add(user)
        await db.commit()
        print(f"\nAdmin user '{username}' created successfully.")


if __name__ == "__main__":
    asyncio.run(create_admin())
