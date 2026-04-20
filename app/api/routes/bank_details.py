import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from pydantic import BaseModel
from typing import Optional

from app.db.database import get_db
from app.models.models import Employee, EmployeeBankDetails
from app.core.deps import get_current_user, is_hr_or_admin

router = APIRouter(prefix="/employees", tags=["bank-details"])


class BankDetailsCreate(BaseModel):
    bank_name: Optional[str] = None
    account_holder_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    branch_name: Optional[str] = None
    account_type: Optional[str] = None
    hdfc_customer_id: Optional[str] = None
    hdfc_netbanking_id: Optional[str] = None


@router.get("/{employee_id}/bank-details")
async def get_bank_details(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    is_self = str(current_user.id) == str(employee_id)
    if not is_self and not is_hr_or_admin(current_user):
        raise HTTPException(403, "Access denied")

    result = await db.execute(
        select(EmployeeBankDetails).where(EmployeeBankDetails.employee_id == employee_id)
    )
    details = result.scalar_one_or_none()
    if not details:
        return None
    return {
        "id": str(details.id),
        "employee_id": str(details.employee_id),
        "bank_name": details.bank_name,
        "account_holder_name": details.account_holder_name,
        "account_number": details.account_number,
        "ifsc_code": details.ifsc_code,
        "branch_name": details.branch_name,
        "account_type": details.account_type,
        "hdfc_customer_id": details.hdfc_customer_id,
        "hdfc_netbanking_id": details.hdfc_netbanking_id,
        "is_verified": details.is_verified,
        "updated_at": details.updated_at.isoformat() if details.updated_at else None,
    }


@router.post("/{employee_id}/bank-details")
async def save_bank_details(
    employee_id: uuid.UUID,
    data: BankDetailsCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    is_self = str(current_user.id) == str(employee_id)
    if not is_self and not is_hr_or_admin(current_user):
        raise HTTPException(403, "Access denied")

    result = await db.execute(
        select(EmployeeBankDetails).where(EmployeeBankDetails.employee_id == employee_id)
    )
    existing = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if existing:
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(existing, field, value)
        existing.updated_at = now
        # If HR is editing, keep verified; if employee self-edits reset to unverified
        if not is_hr_or_admin(current_user):
            existing.is_verified = False
    else:
        new_details = EmployeeBankDetails(
            id=uuid.uuid4(),
            employee_id=employee_id,
            created_at=now,
            updated_at=now,
            **data.model_dump(exclude_none=True),
        )
        db.add(new_details)

    await db.commit()
    return {"message": "Bank details saved successfully"}


@router.put("/{employee_id}/bank-details/verify")
async def verify_bank_details(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    if not is_hr_or_admin(current_user):
        raise HTTPException(403, "Only HR/Admin can verify bank details")

    result = await db.execute(
        select(EmployeeBankDetails).where(EmployeeBankDetails.employee_id == employee_id)
    )
    details = result.scalar_one_or_none()
    if not details:
        raise HTTPException(404, "Bank details not found")

    details.is_verified = True
    details.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "Bank details verified"}