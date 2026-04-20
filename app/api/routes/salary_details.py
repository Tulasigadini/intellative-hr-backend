import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional

from app.db.database import get_db
from app.models.models import Employee, EmployeeSalary
from app.schemas.schemas import EmployeeSalaryCreate, EmployeeSalaryUpdate, EmployeeSalaryOut
from app.core.deps import get_current_user, is_hr_or_admin

router = APIRouter(prefix="/employees", tags=["salary-details"])


@router.get("/{employee_id}/salary", response_model=Optional[EmployeeSalaryOut])
async def get_salary_details(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    # Only self (if allowed) or HR/Admin can view salary
    is_self = str(current_user.id) == str(employee_id)
    if not is_self and not is_hr_or_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to salary information"
        )

    result = await db.execute(
        select(EmployeeSalary).where(EmployeeSalary.employee_id == employee_id)
    )
    salary = result.scalar_one_or_none()
    return salary


@router.post("/{employee_id}/salary", response_model=EmployeeSalaryOut)
async def save_salary_details(
    employee_id: uuid.UUID,
    data: EmployeeSalaryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    is_self = str(current_user.id) == str(employee_id)
    # Employee can save their own extracted salary (from Form 16) during onboarding
    # HR/Admin can always update any employee
    if not is_self and not is_hr_or_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only HR/Admin can update salary information"
        )

    # Check if exists
    result = await db.execute(
        select(EmployeeSalary).where(EmployeeSalary.employee_id == employee_id)
    )
    existing = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if existing:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(existing, field, value)
        existing.updated_at = now
    else:
        existing = EmployeeSalary(
            employee_id=employee_id,
            **data.model_dump(exclude_unset=True)
        )
        db.add(existing)

    await db.commit()
    await db.refresh(existing)
    return existing