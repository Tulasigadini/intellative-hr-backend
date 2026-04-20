"""
Final Fixed Seed Script for Intellativ HR System
Run: python -m app.utils.seed
"""

import asyncio
from datetime import datetime, date
import uuid

from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.models.models import (
    Department, Role, Employee, UserAccount,
    EmployeeStatus, EmployeeType, Gender
)
from app.core.security import get_password_hash


# Use naive datetime consistently to match your current models
NOW = datetime.utcnow()


DEPARTMENTS = [
    {"name": "HR & Operations", "code": "HR", "description": "Human Resources and Operations department"},
    {"name": "Information Technology", "code": "IT", "description": "Software engineering and technology department"},
]

HR_ROLES = [
    ("HR and Operation Manager",    "HR-OPS-MGR", 1, None),
    ("Talent Acquisition Manager",  "HR-TA-MGR",  2, "HR-OPS-MGR"),
    ("Talent Acquisition Lead",     "HR-TA-LEAD", 3, "HR-TA-MGR"),
    ("Vendor Manager",              "HR-VENDOR-MGR", 2, "HR-OPS-MGR"),
]

IT_ROLES = [
    ("Associate",                           "IT-ASSOC",      1, None),
    ("Senior Associate",                    "IT-SR-ASSOC",   2, "IT-ASSOC"),
    ("Lead Associate",                      "IT-LEAD-ASSOC", 3, "IT-SR-ASSOC"),
    ("Senior Software Engineer",            "IT-SSE",        3, "IT-SR-ASSOC"),
    ("Senior Pega Developer",               "IT-PEGA-SR",    3, "IT-SR-ASSOC"),
    ("System Engineer",                     "IT-SYS-ENG",    3, "IT-SR-ASSOC"),
    ("Senior Associate QA",                 "IT-SR-QA",      3, "IT-SR-ASSOC"),
    ("Manager",                             "IT-MGR",        4, "IT-SSE"),
    ("Lead Software Engineer",              "IT-LSE",        4, "IT-SSE"),
    ("Senior Manager",                      "IT-SR-MGR",     5, "IT-MGR"),
    ("Principal Software Engineer",         "IT-PSE",        5, "IT-LSE"),
    ("Associate Vice President",            "IT-AVP",        6, "IT-SR-MGR"),
    ("Senior Principal Software Engineer",  "IT-SR-PSE",     6, "IT-PSE"),
    ("Vice President",                      "IT-VP",         7, "IT-AVP"),
    ("Architect / Distinguished Engineer",  "IT-ARCH",       7, "IT-SR-PSE"),
    ("Senior Vice President",               "IT-SVP",        8, "IT-VP"),
    ("Executive Vice President",            "IT-EVP",        9, "IT-SVP"),
    ("C-Level",                             "IT-CLEVEL",    10, "IT-EVP"),
]


async def seed():
    async with AsyncSessionLocal() as db:
        async with db.begin():

            # ====================== DEPARTMENTS ======================
            dept_map = {}
            for d in DEPARTMENTS:
                result = await db.execute(select(Department).where(Department.code == d["code"]))
                dept = result.scalar_one_or_none()
                if not dept:
                    dept = Department(name=d["name"], code=d["code"], description=d["description"], created_at=NOW)
                    db.add(dept)
                    await db.flush()
                    print(f"✅ Created Department: {d['name']}")
                else:
                    print(f"⏭️  Department already exists: {d['name']}")
                dept_map[d["code"]] = dept

            # ====================== ROLES ======================
            print("\n── Seeding Roles ──")
            role_map = {}

            all_roles = [("HR", r) for r in HR_ROLES] + [("IT", r) for r in IT_ROLES]

            # Pass 1: Create roles
            for dept_code, (name, code, level, parent_code) in all_roles:
                result = await db.execute(select(Role).where(Role.code == code))
                role = result.scalar_one_or_none()
                if not role:
                    role = Role(
                        name=name,
                        code=code,
                        level=level,
                        department_id=dept_map[dept_code].id,
                        parent_role_id=None,
                        created_at=NOW,
                    )
                    db.add(role)
                    await db.flush()
                    print(f"    + Created Role: {code}")
                role_map[code] = role

            # Pass 2: Set parents
            for dept_code, (name, code, level, parent_code) in all_roles:
                if parent_code and parent_code in role_map:
                    role_map[code].parent_role_id = role_map[parent_code].id

            print("✅ Roles seeded with hierarchy.")

            # ====================== SUPER ADMIN ======================
            print("\n── Creating Super Admin ──")

            result = await db.execute(select(Employee).where(Employee.email == "admin@intellativ.com"))
            admin_emp = result.scalar_one_or_none()

            if not admin_emp:
                admin_emp = Employee(
                    employee_id="INT-ADMIN-001",
                    first_name="Super",
                    last_name="Admin",
                    email="admin@intellativ.com",
                    personal_email="admin@intellativ.com",
                    phone="9999999999",
                    gender=Gender.OTHER,
                    department_id=dept_map["IT"].id,
                    role_id=role_map.get("IT-CLEVEL").id,
                    employee_type=EmployeeType.NEW,
                    status=EmployeeStatus.ACTIVE,
                    joining_date=date.today(),
                    is_profile_complete=True,
                    created_at=NOW,
                    updated_at=NOW,
                )
                db.add(admin_emp)
                await db.flush()
                print("✅ Super Admin Employee created")
            else:
                print("⏭️  Super Admin employee already exists")

            result = await db.execute(select(UserAccount).where(UserAccount.username == "admin@intellativ.com"))
            if not result.scalar_one_or_none():
                admin_user = UserAccount(
                    employee_id=admin_emp.id,
                    username="admin@intellativ.com",
                    hashed_password=get_password_hash("Admin@123"),
                    is_active=True,
                    is_superadmin=True,
                    created_at=NOW,
                )
                db.add(admin_user)
                print("✅ Super Admin Account created → admin@intellativ.com / Admin@123")

            # ====================== SAMPLE EMPLOYEES (Fixed) ======================
            print("\n── Adding Sample Employees ──")
            samples = [
                ("Priya", "Sharma", "priya.sharma@intellativ.com", "HR-TA-MGR", "HR"),
                ("Arjun", "Reddy", "arjun.reddy@intellativ.com", "IT-SSE", "IT"),
                ("Sneha", "Patel", "sneha.patel@intellativ.com", "IT-LSE", "IT"),
            ]

            for first, last, email, role_code, dept_code in samples:
                result = await db.execute(select(Employee).where(Employee.email == email))
                if result.scalar_one_or_none():
                    print(f"    ⏭️  Employee exists: {email}")
                    continue

                role = role_map.get(role_code)
                emp = Employee(
                    employee_id=f"EMP{str(uuid.uuid4())[:8].upper()}",
                    first_name=first,
                    last_name=last,
                    email=email,
                    gender=Gender.FEMALE if first in ["Priya", "Sneha"] else Gender.MALE,
                    department_id=dept_map[dept_code].id,
                    role_id=role.id if role else None,
                    status=EmployeeStatus.ACTIVE,
                    employee_type=EmployeeType.NEW,
                    joining_date=date(2025, 1, 10),
                    is_profile_complete=True,
                    created_at=NOW,
                    updated_at=NOW,          # ← Fixed: using naive datetime
                )
                db.add(emp)
                print(f"    + Created: {first} {last}")

        print("\n🎉 Seeding completed successfully!")
        print("   Admin Login:")
        print("   Email    : admin@intellativ.com")
        print("   Password : Admin@123")


if __name__ == "__main__":
    asyncio.run(seed())