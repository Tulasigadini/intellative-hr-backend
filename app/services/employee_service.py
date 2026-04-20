import uuid
import shortuuid
from typing import Optional, List
from datetime import datetime, date, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload

from app.models.models import Employee, Department, Role, EmployeeStatus, EmployeeType, WorkHistory
from app.schemas.schemas import EmployeeCreate, EmployeeUpdate
from app.core.config import settings


def generate_employee_id(department_code: str = "IT") -> str:
    year = datetime.now(timezone.utc).strftime("%y")
    uid = shortuuid.ShortUUID().random(length=4).upper()
    return f"INT{year}{department_code[:2].upper()}{uid}"


def generate_company_email(first_name: str, last_name: str, existing_emails: List[str]) -> str:
    clean_first = first_name.lower().replace(" ", "").replace(".", "")
    clean_last = last_name.lower().replace(" ", "").replace(".", "")
    base = f"{clean_first}.{clean_last}"
    email = f"{base}@{settings.COMPANY_DOMAIN}"
    if email not in existing_emails:
        return email
    counter = 1
    while f"{base}{counter}@{settings.COMPANY_DOMAIN}" in existing_emails:
        counter += 1
    return f"{base}{counter}@{settings.COMPANY_DOMAIN}"


async def create_employee(db: AsyncSession, data: EmployeeCreate, onboarded_by_id=None, onboarded_by_email=None) -> Employee:
    result = await db.execute(select(Employee.email))
    existing_emails = [row[0] for row in result.fetchall()]

    dept_code = "GEN"
    if data.department_id:
        dept_result = await db.execute(select(Department).where(Department.id == data.department_id))
        dept = dept_result.scalar_one_or_none()
        if dept:
            dept_code = dept.code[:3].upper()

    employee_id = generate_employee_id(dept_code)
    company_email = generate_company_email(data.first_name, data.last_name, existing_emails)

    employee = Employee(
        employee_id=employee_id,
        email=company_email,
        onboarded_by=onboarded_by_id,
        onboarded_by_email=onboarded_by_email,
        **data.model_dump(exclude_none=True)
    )
    db.add(employee)
    await db.flush()
    await db.refresh(employee)
    return employee


async def get_employee(db: AsyncSession, employee_id: uuid.UUID) -> Optional[Employee]:
    result = await db.execute(
        select(Employee)
        .options(
            selectinload(Employee.department), 
            selectinload(Employee.role),
            selectinload(Employee.salary),
            selectinload(Employee.bank_details)
        )
        .where(Employee.id == employee_id)
    )
    return result.scalar_one_or_none()


async def get_employees(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    search: Optional[str] = None,
    status: Optional[EmployeeStatus] = None,
    department_id: Optional[uuid.UUID] = None,
    employee_type: Optional[EmployeeType] = None,
    only_employee_id: Optional[str] = None,
):
    query = select(Employee).options(
        selectinload(Employee.department),
        selectinload(Employee.role),
        selectinload(Employee.salary),
        selectinload(Employee.bank_details)
    )
    filters = []
    if only_employee_id:
        # Filter to just this one employee by UUID
        try:
            filters.append(Employee.id == uuid.UUID(only_employee_id))
        except Exception:
            pass
    else:
        if search:
            filters.append(or_(
                Employee.first_name.ilike(f"%{search}%"),
                Employee.last_name.ilike(f"%{search}%"),
                Employee.email.ilike(f"%{search}%"),
                Employee.employee_id.ilike(f"%{search}%"),
            ))
        if status:
            filters.append(Employee.status == status)
        if department_id:
            filters.append(Employee.department_id == department_id)
        if employee_type:
            filters.append(Employee.employee_type == employee_type)

    if filters:
        query = query.where(and_(*filters))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    query = query.offset((page - 1) * size).limit(size).order_by(Employee.created_at.desc())
    result = await db.execute(query)
    items = result.scalars().all()
    return items, total


async def update_employee(db: AsyncSession, employee_id: uuid.UUID, data: EmployeeUpdate) -> Optional[Employee]:
    employee = await get_employee(db, employee_id)
    if not employee:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(employee, field, value)
    employee.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(employee)
    return employee


async def activate_employee(db: AsyncSession, employee_id: uuid.UUID) -> Optional[Employee]:
    employee = await get_employee(db, employee_id)
    if not employee:
        return None
    employee.status = EmployeeStatus.ACTIVE
    employee.is_profile_complete = True
    employee.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return employee


async def relieve_employee(db: AsyncSession, employee_id: uuid.UUID, relieving_date: date) -> Optional[Employee]:
    employee = await get_employee(db, employee_id)
    if not employee:
        return None

    # ARCHIVE: Before relieving, create a WorkHistory entry for the current (now ending) tenure
    # This ensures we have a record of every "joining -> relieving" cycle
    history_entry = WorkHistory(
        employee_id=employee.id,
        company_name="Intellativ",
        designation=employee.role.name if employee.role else "General",
        department=employee.department.name if employee.department else None,
        from_date=employee.joining_date,
        to_date=relieving_date,
        is_intellativ=True,
        reason_for_leaving="Relieved / End of Tenure"
    )
    db.add(history_entry)

    # Update the "previous history" fields on the employee model to match the tenure just ended
    # This facilitates easy "Previous Employee ID" display during re-onboarding
    employee.previous_employee_id = employee.employee_id
    employee.previous_joining_date = employee.joining_date
    employee.previous_relieving_date = relieving_date

    employee.status = EmployeeStatus.RELIEVED
    employee.relieving_date = relieving_date
    employee.updated_at = datetime.now(timezone.utc)
    
    await db.flush()
    return employee


async def get_dashboard_stats(db: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total = (await db.execute(select(func.count(Employee.id)))).scalar()
    active = (await db.execute(select(func.count(Employee.id)).where(Employee.status == EmployeeStatus.ACTIVE))).scalar()
    pending = (await db.execute(select(func.count(Employee.id)).where(Employee.status == EmployeeStatus.PENDING))).scalar()
    relieved = (await db.execute(
        select(func.count(Employee.id)).where(
            and_(Employee.status == EmployeeStatus.RELIEVED, Employee.relieving_date >= month_start.date())
        )
    )).scalar()
    new_joinings = (await db.execute(
        select(func.count(Employee.id)).where(Employee.joining_date >= month_start.date())
    )).scalar()
    depts = (await db.execute(select(func.count(Department.id)).where(Department.is_active == True))).scalar()
    roles = (await db.execute(select(func.count(Role.id)).where(Role.is_active == True))).scalar()

    return {
        "total_employees": total,
        "active_employees": active,
        "pending_onboarding": pending,
        "relieved_this_month": relieved,
        "new_joinings_this_month": new_joinings,
        "departments_count": depts,
        "roles_count": roles,
    }


async def check_and_complete_profile_tasks(db: AsyncSession, employee_id: uuid.UUID):
    from app.models.models import Task, EmployeeDocument, InsuranceInfo, WorkHistory
    emp = await get_employee(db, employee_id)
    if not emp: return
    
    missing = False
    FLABELS = {
        "personal_email": "Personal Email", "phone": "Phone Number", "date_of_birth": "Date of Birth",
        "gender": "Gender", "address": "Address", "emergency_contact_phone": "Emergency Contact"
    }
    for f in FLABELS:
        if not getattr(emp, f, None): missing = True
            
    doc_cnt = (await db.execute(select(func.count(EmployeeDocument.id)).where(EmployeeDocument.employee_id == employee_id))).scalar()
    if doc_cnt < 2: missing = True
        
    ins = (await db.execute(select(InsuranceInfo).where(InsuranceInfo.employee_id == employee_id))).scalar_one_or_none()
    if not ins or not ins.nominee_name: missing = True
        
    wh_cnt = (await db.execute(select(func.count(WorkHistory.id)).where(WorkHistory.employee_id == employee_id))).scalar()
    if wh_cnt == 0: missing = True
    
    if not missing:
        # Auto-complete pending profile completion tasks
        result = await db.execute(select(Task).where(
            Task.related_employee_id == employee_id,
            Task.task_type == "profile_completion",
            Task.status == "pending"
        ))
        for t in result.scalars().all():
            t.status = "completed"
            t.completed_at = datetime.now(timezone.utc)
        await db.flush()
