import asyncio
from sqlalchemy import select, or_
from app.db.database import AsyncSessionLocal
from app.models.models import UserAccount, Employee

async def check_anomalies():
    async with AsyncSessionLocal() as db:
        # 1. Find all UserAccounts where username matches someone else's personal_email or email
        result = await db.execute(
            select(UserAccount, Employee)
            .outerjoin(Employee, UserAccount.employee_id == Employee.id)
        )
        all_accounts = result.all()
        
        print(f"Total Accounts: {len(all_accounts)}")
        for acc, emp in all_accounts:
            print(f"Acc ID: {acc.id} | Username: {acc.username} | Emp Email: {emp.email if emp else 'N/A'} | Pers Email: {emp.personal_email if emp else 'N/A'}")
            
            # Check if this username is used as an email elsewhere
            check_result = await db.execute(
                select(Employee).where(or_(Employee.email == acc.username, Employee.personal_email == acc.username))
            )
            others = check_result.scalars().all()
            for other in others:
                if str(other.id) != str(acc.employee_id):
                    print(f"  [!] ANOMALY: Username '{acc.username}' matches Email of different Employee ID: {other.id}")

if __name__ == "__main__":
    asyncio.run(check_anomalies())
