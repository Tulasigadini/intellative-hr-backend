import asyncio
from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.models.models import UserAccount, Employee

async def check_specific_accounts():
    async with AsyncSessionLocal() as db:
        # Search for the two IDs we saw in the logs
        ids = ['d0e54cb9-bf1b-46ea-ac0c-83e5aee154cf', '72289c72-d664-47af-b664-304e52095cd5']
        
        for uid in ids:
            result = await db.execute(
                select(UserAccount, Employee)
                .outerjoin(Employee, UserAccount.employee_id == Employee.id)
                .where(UserAccount.id == uid)
            )
            row = result.first()
            if row:
                acc, emp = row
                print(f"ID: {uid}")
                print(f"  Username: {acc.username}")
                if emp:
                    print(f"  Work Email: {emp.email}")
                    print(f"  Personal Email: {emp.personal_email}")
                print("-" * 30)

if __name__ == "__main__":
    asyncio.run(check_specific_accounts())
