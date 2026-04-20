import os
import math
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select, text, insert
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import date, datetime
import aiofiles

from app.db.database import get_db
from app.models.models import Employee, UserAccount, EmployeeDocument, DocumentType, EmployeeStatus
from app.schemas.schemas import (
    EmployeeCreate, EmployeeUpdate, EmployeeOut, EmployeeListOut, PaginatedEmployees, DocumentOut
)
from app.services.employee_service import (
    create_employee, get_employee, get_employees, update_employee,
    activate_employee, relieve_employee, get_dashboard_stats,
    check_and_complete_profile_tasks
)
from app.api.routes.resume_parse import _get_text, _parse_resume, _parse_form16, _extract_bank_details, PAN_RE
from app.services.email_service import send_welcome_email, send_relieving_notification
from app.core.deps import (
    get_current_user, is_hr_or_admin, is_superadmin,
    can_manage_employees, can_onboard_employees, can_edit_employees, can_view_all_employees,
    can_view_employee_detail
)
from app.core.security import get_password_hash
from app.core.config import settings

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("/dashboard/stats")
async def dashboard_stats(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await get_dashboard_stats(db)

@router.get("/dashboard/stats")
async def dashboard_stats(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return await get_dashboard_stats(db)

@router.get("", response_model=PaginatedEmployees)
async def list_employees(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[EmployeeStatus] = None,
    department_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    # ALL employees can see the full list — action buttons restricted on frontend
    items, total = await get_employees(db, page, size, search, status, department_id)
    return PaginatedEmployees(
        items=items, total=total, page=page, size=size,
        pages=math.ceil(total / size) if total else 1
    )


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
async def create_new_employee(
    data: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    if not can_onboard_employees(current_user):
        raise HTTPException(403, "Only HR, Admin, or authorized managers can create employees")
    employee = await create_employee(db, data, onboarded_by_id=current_user.id, onboarded_by_email=current_user.email)
    return await get_employee(db, employee.id)


@router.get("/{employee_id}", response_model=EmployeeOut)
async def get_employee_detail(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    # Only self, HR/Operations, or superadmin can view employee details
    is_self = str(current_user.id) == str(employee_id)
    if not is_self and not can_view_employee_detail(current_user, employee_id):
        raise HTTPException(403, "You are not authorized to view this employee's details")
    emp = await get_employee(db, employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")
    return emp


@router.put("/{employee_id}", response_model=EmployeeOut)
async def update_employee_detail(
    employee_id: uuid.UUID,
    data: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    if not can_edit_employees(current_user):
        raise HTTPException(403, "Only HR/Admin can edit employee details")
    emp = await update_employee(db, employee_id, data)
    if not emp:
        raise HTTPException(404, "Employee not found")
        
    await check_and_complete_profile_tasks(db, employee_id)
    return emp


@router.post("/{employee_id}/activate", response_model=EmployeeOut)
async def activate(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    if not can_onboard_employees(current_user):
        raise HTTPException(403, "Only HR/Admin can activate employees")
    emp = await get_employee(db, employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")
    existing_user = await db.execute(select(UserAccount).where(UserAccount.employee_id == emp.id))
    if not existing_user.scalar_one_or_none():
        temp_password = f"Int@{uuid.uuid4().hex[:6]}"
        user = UserAccount(
            employee_id=emp.id,
            username=emp.email,
            hashed_password=get_password_hash(temp_password),
        )
        db.add(user)
        try:
            send_welcome_email(emp.personal_email or emp.email, emp.full_name, emp.email, temp_password)
        except Exception:
            pass
    activated = await activate_employee(db, employee_id)
    return activated


@router.post("/{employee_id}/relieve")
async def relieve(
    employee_id: uuid.UUID,
    relieving_date: date,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    if not can_edit_employees(current_user):
        raise HTTPException(403, "Only HR/Admin can relieve employees")
    emp = await get_employee(db, employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")
    await relieve_employee(db, employee_id, relieving_date)
    try:
        from app.models.models import UserAccount, Role
        from sqlalchemy.orm import selectinload as sil

        # Primary recipient: HR who onboarded this employee
        primary_email = emp.onboarded_by_email or settings.HR_NOTIFICATION_EMAIL or settings.SMTP_FROM

        # CC: all active HR admins (HR-* role codes)
        hr_result = await db.execute(
            select(Employee)
            .options(sil(Employee.role))
            .where(Employee.status == "active")
        )
        all_employees = hr_result.scalars().all()
        hr_cc = list(set([
            e.email for e in all_employees
            if e.role and e.role.code.startswith("HR-")
            and e.email != primary_email
            and e.email
        ]))

        # Get onboarded_by name
        onboarded_by_name = ""
        if emp.onboarded_by:
            ob_result = await db.execute(select(Employee).where(Employee.id == emp.onboarded_by))
            ob = ob_result.scalar_one_or_none()
            if ob:
                onboarded_by_name = ob.full_name

        send_relieving_notification(
            primary_email,
            emp.full_name,
            emp.employee_id,
            str(relieving_date),
            cc_emails=hr_cc,
            department=emp.department.name if emp.department else "",
            role=emp.role.name if emp.role else "",
            onboarded_by_name=onboarded_by_name,
        )
    except Exception as e:
        print(f"Relieving email error: {e}")
    return {"message": "Employee relieved successfully"}


@router.post("/{employee_id}/documents", response_model=DocumentOut)
async def upload_document(
    employee_id: uuid.UUID,
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    if str(current_user.id) != str(employee_id) and not is_hr_or_admin(current_user):
        raise HTTPException(403, "You can only upload your own documents")

    emp = await get_employee(db, employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")

    # === Strong Normalization ===
    normalized_type = (
        document_type.strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
        .replace("(", "")
        .replace(")", "")
        .replace("&", "and")
    )

    try:
        doc_enum = DocumentType(normalized_type)
    except ValueError:
        valid_types = [e.value for e in DocumentType]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document type: '{document_type}' (normalized to '{normalized_type}'). "
                   f"Valid types: {valid_types}"
        )

    # File validation
    ext = file.filename.split(".")[-1].lower()
    allowed = getattr(settings, 'allowed_extensions_list', ['pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx'])
    if ext not in allowed:
        raise HTTPException(400, f"File type .{ext} not allowed.")

    upload_dir = os.path.join(settings.UPLOAD_DIR, str(employee_id))
    os.makedirs(upload_dir, exist_ok=True)

    # Unique filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    file_name = f"{normalized_type}_{timestamp}_{uuid.uuid4().hex[:8]}.{ext}"
    file_path = os.path.join(upload_dir, file_name)

    content = await file.read()
    file_size = len(content)

    # Delete existing doc of same type using raw SQL to avoid asyncpg enum binding issue
    await db.execute(
        text(
            "DELETE FROM employee_documents "
            "WHERE employee_id = :emp_id "
            "AND document_type::text = :doc_type"
        ),
        {"emp_id": str(employee_id), "doc_type": doc_enum.value}
    )

    # Save file to disk first
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    # Insert using raw SQL — embed the enum value directly in the SQL string
    # (it is safe: doc_enum.value is validated against DocumentType enum above)
    # Avoid :param::type syntax — SQLAlchemy text() mangles it. Use CAST() instead.
    new_id = uuid.uuid4()
    from datetime import timezone
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    safe_doc_type = doc_enum.value  # e.g. "utility_bill" — already validated
    await db.execute(
        text(
            f"INSERT INTO employee_documents "
            f"(id, employee_id, document_type, document_name, file_path, file_size, is_verified, uploaded_at) "
            f"VALUES (:id, :employee_id, CAST('{safe_doc_type}' AS documenttype), :document_name, "
            f":file_path, :file_size, :is_verified, :uploaded_at)"
        ),
        {
            "id": str(new_id),
            "employee_id": str(employee_id),
            "document_name": file.filename,
            "file_path": file_path,
            "file_size": file_size,
            "is_verified": False,
            "uploaded_at": now,
        }
    )
    await db.commit()

    # Fetch and return the inserted document
    result = await db.execute(
        select(EmployeeDocument).where(EmployeeDocument.id == new_id)
    )
    doc = result.scalar_one()
    
    await check_and_complete_profile_tasks(db, employee_id)
    
    return doc

@router.get("/{employee_id}/documents", response_model=list[DocumentOut])
async def list_documents(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    result = await db.execute(
        select(EmployeeDocument).where(EmployeeDocument.employee_id == employee_id)
    )
    return result.scalars().all()


@router.get("/{employee_id}/documents/{doc_id}/download")
async def download_document(
    employee_id: uuid.UUID,
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    if str(current_user.id) != str(employee_id) and not can_view_all_employees(current_user):
        raise HTTPException(403, "Access denied")
    result = await db.execute(
        select(EmployeeDocument).where(
            EmployeeDocument.id == doc_id,
            EmployeeDocument.employee_id == employee_id
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    if not os.path.exists(doc.file_path):
        raise HTTPException(404, "File not found on server")
    return FileResponse(path=doc.file_path, filename=doc.document_name, media_type="application/octet-stream")


@router.post("/{employee_id}/profile-picture")
async def upload_profile_picture(
    employee_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    if str(current_user.id) != str(employee_id) and not is_hr_or_admin(current_user):
        raise HTTPException(403, "Access denied")
    emp = await get_employee(db, employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")
    upload_dir = os.path.join(settings.UPLOAD_DIR, str(employee_id), "profile")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"avatar.{file.filename.split('.')[-1]}")
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(await file.read())
    emp.profile_picture = file_path
    await db.flush()
    return {"profile_picture": file_path}