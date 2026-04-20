from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID
from datetime import datetime, date, timedelta, timezone
from pydantic import BaseModel

from app.db.database import get_db
from app.models.models import AssetRequest, UserAccount, SystemAccess, Employee, EmployeeDocument, Role
from app.core.deps import get_current_user, is_hr_or_admin, is_superadmin, can_manage_employees
from app.core.security import get_password_hash
from app.services.email_service import send_asset_allocation_email
from app.core.config import settings

router = APIRouter(prefix="/iam", tags=["iam"])


class SystemAccessCreate(BaseModel):
    role_id: UUID
    system_name: str
    access_level: str


class SystemAccessOut(BaseModel):
    id: UUID
    role_id: UUID
    system_name: str
    access_level: str
    is_active: bool
    model_config = {"from_attributes": True}


class ResetPasswordRequest(BaseModel):
    new_password: str


class VerifyDocumentRequest(BaseModel):
    is_verified: bool


# ── System Accesses ───────────────────────────────────────────────────────────

@router.get("/system-accesses", response_model=List[SystemAccessOut])
async def list_system_accesses(
    role_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    query = select(SystemAccess).where(SystemAccess.is_active == True)
    # Non-admin: only see own role's accesses
    if not is_hr_or_admin(current_user):
        if current_user.role_id:
            query = query.where(SystemAccess.role_id == current_user.role_id)
        else:
            return []
    elif role_id:
        query = query.where(SystemAccess.role_id == role_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/system-accesses", response_model=SystemAccessOut)
async def create_system_access(
    data: SystemAccessCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    if not is_hr_or_admin(current_user):
        raise HTTPException(403, "Insufficient permissions")
    sa = SystemAccess(**data.model_dump())
    db.add(sa)
    await db.flush()
    await db.refresh(sa)
    return sa


@router.delete("/system-accesses/{sa_id}", status_code=204)
async def delete_system_access(
    sa_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    if not is_hr_or_admin(current_user):
        raise HTTPException(403, "Insufficient permissions")
    result = await db.execute(select(SystemAccess).where(SystemAccess.id == sa_id))
    sa = result.scalar_one_or_none()
    if not sa:
        raise HTTPException(404, "Not found")
    await db.delete(sa)


# ── User Accounts ──────────────────────────────────────────────────────────────

@router.get("/accounts")
async def list_user_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    if not is_hr_or_admin(current_user):
        raise HTTPException(403, "Insufficient permissions")
    result = await db.execute(
        select(UserAccount, Employee)
        .join(Employee, UserAccount.employee_id == Employee.id)
        .options(selectinload(Employee.role), selectinload(Employee.department))
    )
    rows = result.all()
    return [
        {
            "id": str(a.id),
            "username": a.username,
            "is_active": a.is_active,
            "last_login": a.last_login,
            "is_superadmin": a.is_superadmin,
            "employee_id": str(e.id),
            "employee_name": f"{e.first_name} {e.last_name}",
            "department": e.department.name if e.department else None,
            "role": e.role.name if e.role else None,
        }
        for a, e in rows
    ]


@router.put("/accounts/{account_id}/toggle")
async def toggle_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    if not is_hr_or_admin(current_user):
        raise HTTPException(403, "Insufficient permissions")
    result = await db.execute(select(UserAccount).where(UserAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Account not found")
    account.is_active = not account.is_active
    await db.flush()
    return {"is_active": account.is_active}


@router.put("/accounts/{account_id}/reset-password")
async def reset_password(
    account_id: UUID,
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    if not is_hr_or_admin(current_user):
        raise HTTPException(403, "Insufficient permissions")
    result = await db.execute(select(UserAccount).where(UserAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Account not found")
    account.hashed_password = get_password_hash(data.new_password)
    await db.flush()
    return {"message": "Password reset successfully"}


# ── Document Verification ─────────────────────────────────────────────────────

@router.put("/documents/{doc_id}/verify")
async def verify_document(
    doc_id: UUID,
    data: VerifyDocumentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    if not is_hr_or_admin(current_user):
        raise HTTPException(403, "Only HR/Admin can verify documents")
    from app.models.models import EmployeeDocument
    result = await db.execute(select(EmployeeDocument).where(EmployeeDocument.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    doc.is_verified = data.is_verified
    doc.verified_at = datetime.now(timezone.utc)
    doc.verified_by = current_user.id
    await db.flush()
    return {"message": "Document verification updated", "is_verified": doc.is_verified}


# ── Assets (Devices, ID Card, etc.) ──────────────────────────────────────────

ASSET_TYPES = [
    {"id": "laptop", "label": "Laptop", "icon": "💻"},
    {"id": "mobile", "label": "Mobile Phone", "icon": "📱"},
    {"id": "id_card", "label": "ID Card", "icon": "🪪"},
    {"id": "access_card", "label": "Access Card", "icon": "🔑"},
    {"id": "fingerprint", "label": "Fingerprint Access", "icon": "👆"},
    {"id": "mouse_keyboard", "label": "Mouse & Keyboard", "icon": "🖱"},
    {"id": "headset", "label": "Headset", "icon": "🎧"},
    {"id": "monitor", "label": "External Monitor", "icon": "🖥"},
    {"id": "sim_card", "label": "SIM Card", "icon": "📡"},
]


@router.get("/asset-types")
async def get_asset_types(_=Depends(get_current_user)):
    return ASSET_TYPES


@router.post("/asset-requests/joining/{employee_id}")
async def send_joining_asset_email(
    employee_id: UUID,
    assets: List[str],
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    if not can_manage_employees(current_user):
        raise HTTPException(403, "Insufficient permissions")
    result = await db.execute(
        select(Employee).options(selectinload(Employee.role), selectinload(Employee.department))
        .where(Employee.id == employee_id)
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Employee not found")
    asset_labels = [a["label"] for a in ASSET_TYPES if a["id"] in assets]
    try:
        primary = settings.HR_NOTIFICATION_EMAIL or settings.SMTP_FROM
        # CC: onboarding HR if exists
        cc = []
        if emp.onboarded_by_email and emp.onboarded_by_email != primary:
            cc.append(emp.onboarded_by_email)
        send_asset_allocation_email(
            primary, emp.first_name + " " + emp.last_name,
            emp.employee_id, "allocate", asset_labels,
            cc_emails=cc,
            department=emp.department.name if emp.department else "",
            joining_date=str(emp.joining_date) if emp.joining_date else "",
        )
    except Exception as e:
        raise HTTPException(500, f"Email failed: {e}")
    return {"message": f"Asset allocation email sent for {emp.first_name}"}


@router.post("/asset-requests/relieving/{employee_id}")
async def send_relieving_asset_email(
    employee_id: UUID,
    assets: List[str],
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    if not can_manage_employees(current_user):
        raise HTTPException(403, "Insufficient permissions")
    result = await db.execute(
        select(Employee).options(selectinload(Employee.role), selectinload(Employee.department))
        .where(Employee.id == employee_id)
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Employee not found")
    asset_labels = [a["label"] for a in ASSET_TYPES if a["id"] in assets]
    try:
        primary = settings.HR_NOTIFICATION_EMAIL or settings.SMTP_FROM
        cc = []
        if emp.onboarded_by_email and emp.onboarded_by_email != primary:
            cc.append(emp.onboarded_by_email)
        send_asset_allocation_email(
            primary, emp.first_name + " " + emp.last_name,
            emp.employee_id, "collect", asset_labels,
            cc_emails=cc,
            department=emp.department.name if emp.department else "",
        )
    except Exception as e:
        raise HTTPException(500, f"Email failed: {e}")
    return {"message": f"Asset collection email sent for {emp.first_name}"}


# ── Upcoming Relieving Alert ──────────────────────────────────────────────────

@router.get("/upcoming-relieving")
async def upcoming_relieving(
    days: int = 7,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    if not is_hr_or_admin(current_user):
        raise HTTPException(403, "Insufficient permissions")
    from sqlalchemy import and_
    today = date.today()
    future = today + timedelta(days=days)
    result = await db.execute(
        select(Employee)
        .options(selectinload(Employee.role), selectinload(Employee.department))
        .where(and_(
            Employee.relieving_date >= today,
            Employee.relieving_date <= future,
            Employee.status == "active"
        ))
    )
    employees = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "name": f"{e.first_name} {e.last_name}",
            "employee_id": e.employee_id,
            "relieving_date": str(e.relieving_date),
            "department": e.department.name if e.department else None,
            "role": e.role.name if e.role else None,
            "days_left": (e.relieving_date - today).days,
        }
        for e in employees
    ]


# ── Employee Asset Tracker ────────────────────────────────────────────────────

from sqlalchemy import update as sa_update
import json

@router.get("/my-assets")
async def get_my_assets(
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    """Get assets allocated to the current user"""
    result = await db.execute(
        select(AssetRequest)
        .where(AssetRequest.employee_id == current_user.id)
        .order_by(AssetRequest.created_at.desc())
    )
    requests = result.scalars().all()

    # Build asset status: latest action per asset_type wins
    asset_status = {}
    for req in reversed(requests):  # oldest first
        asset_status[req.asset_type] = {
            "action": req.action.value,
            "date": str(req.created_at.date()),
            "notes": req.notes,
        }

    all_assets = []
    for asset in ASSET_TYPES:
        status = asset_status.get(asset["id"])
        all_assets.append({
            "id": asset["id"],
            "label": asset["label"],
            "icon": asset["icon"],
            "status": "allocated" if status and status["action"] == "allocate" else
                      "collected" if status and status["action"] == "collect" else
                      "not_assigned",
            "date": status["date"] if status else None,
        })
    return all_assets


@router.get("/employee-assets/{employee_id}")
async def get_employee_assets(
    employee_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    """HR/Admin: get assets for any employee"""
    if str(current_user.id) != str(employee_id) and not is_hr_or_admin(current_user):
        raise HTTPException(403, "Access denied")

    result = await db.execute(
        select(AssetRequest)
        .where(AssetRequest.employee_id == employee_id)
        .order_by(AssetRequest.created_at.desc())
    )
    requests = result.scalars().all()

    asset_status = {}
    for req in reversed(requests):
        asset_status[req.asset_type] = {
            "action": req.action.value,
            "date": str(req.created_at.date()),
        }

    all_assets = []
    for asset in ASSET_TYPES:
        status = asset_status.get(asset["id"])
        all_assets.append({
            "id": asset["id"],
            "label": asset["label"],
            "icon": asset["icon"],
            "status": "allocated" if status and status["action"] == "allocate" else
                      "collected" if status and status["action"] == "collect" else
                      "not_assigned",
            "date": status["date"] if status else None,
        })
    return all_assets


@router.post("/record-asset/{employee_id}")
async def record_asset_action(
    employee_id: UUID,
    asset_id: str,
    action: str,  # allocate or collect
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    """Record an asset allocation/collection in DB"""
    if not can_manage_employees(current_user):
        raise HTTPException(403, "Insufficient permissions")
    from app.models.models import AssetRequest, AssetAction
    record = AssetRequest(
        employee_id=employee_id,
        action=AssetAction.ALLOCATE if action == "allocate" else AssetAction.COLLECT,
        asset_type=asset_id,
        email_sent=True,
        email_sent_at=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.flush()
    return {"message": "Asset recorded"}
