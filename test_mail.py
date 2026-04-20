"""
Test if a user account exists and password works.
Run: python test_login.py
"""
import asyncio
from sqlalchemy import select
from app.db.database import AsyncSessionLocal, create_tables
from app.models.models import UserAccount, Employee
from app.core.security import verify_password

async def check():
    async with AsyncSessionLocal() as db:
        # List all user accounts
        result = await db.execute(select(UserAccount))
        accounts = result.scalars().all()
        print(f"\n{'='*50}")
        print(f"Total user accounts: {len(accounts)}")
        print(f"{'='*50}")
        for acc in accounts:
            emp_result = await db.execute(select(Employee).where(Employee.id == acc.employee_id))
            emp = emp_result.scalar_one_or_none()
            print(f"\nUsername : {acc.username}")
            print(f"Employee : {emp.first_name} {emp.last_name if emp else 'N/A'}")
            print(f"Active   : {acc.is_active}")
            print(f"Last login: {acc.last_login or 'Never'}")

asyncio.run(check())