"""
Unified Onboarding Route — handles new + rejoining employees,
step-by-step emails, notifications, insurance, work history,
and AUTO-TASK CREATION for Insurance, IT, Admin, HR teams.
"""
import uuid
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.db.database import get_db
from app.models.models import (
    Employee, Department, Role, UserAccount, EmployeeStatus, 
    EmployeeType, EmployeeSalary, EmployeeBankDetails, WorkHistory,
    InsuranceInfo, Notification, Task
)
from app.services.employee_service import (
    create_employee, get_employee, activate_employee, check_and_complete_profile_tasks
)
from app.services.email_service import (
    send_welcome_email, send_step_notification,
    send_insurance_request, send_email_setup_request,
    send_asset_allocation_email, send_joining_details_email
)
from app.core.deps import get_current_user, can_onboard_employees, is_hr_or_admin, can_view_employee_detail, can_edit_employees
from app.core.security import get_password_hash
from app.core.config import settings
from app.schemas.schemas import EmployeeCreate

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

# ── Schemas ───────────────────────────────────────────────────────────────────

class CheckEmployeeRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    personal_email: Optional[str] = None
    phone: Optional[str] = None

class WorkHistoryCreate(BaseModel):
    company_name: str
    designation: Optional[str] = None
    department: Optional[str] = None
    from_date: date
    to_date: Optional[date] = None
    is_current: bool = False
    is_intellativ: bool = False
    reason_for_leaving: Optional[str] = None
    last_ctc: Optional[str] = None

class ChildInfo(BaseModel):
    name: str
    dob: Optional[date] = None
    gender: Optional[str] = None

class InsuranceInfoCreate(BaseModel):
    # Employee insurance details
    smoking_status: Optional[str] = None  # "smoker" | "non_smoker"
    # Nominee
    nominee_name: str
    nominee_relation: str
    nominee_dob: Optional[date] = None
    nominee_phone: Optional[str] = None
    blood_group: Optional[str] = None
    pre_existing_conditions: Optional[str] = None
    # Spouse (optional)
    spouse_name: Optional[str] = None
    spouse_dob: Optional[date] = None
    spouse_gender: Optional[str] = None
    # Children (optional)
    children: Optional[List[ChildInfo]] = None

class StepEmailRequest(BaseModel):
    employee_id: uuid.UUID
    step: int
    note: Optional[str] = None

class AssetAllocateRequest(BaseModel):
    employee_id: uuid.UUID
    assets: List[str]

# ── Team prefixes ─────────────────────────────────────────────────────────────
TEAM_PREFIXES = {
    "hr":        ["HR-"],
    "it":        ["IT-"],
    "insurance": ["INS-", "FIN-"],
    "admin":     ["ADM-"],
    "finance":   ["FIN-"],
}

# ── Helpers ───────────────────────────────────────────────────────────────────

async def create_notification(db, recipient_id, title, message, notif_type, related_emp_id=None, action_url=None):
    notif = Notification(
        recipient_employee_id=recipient_id, title=title, message=message,
        notification_type=notif_type, related_employee_id=related_emp_id, action_url=action_url,
    )
    db.add(notif)

async def get_team_employees(db: AsyncSession, team: str) -> List[Employee]:
    prefixes = TEAM_PREFIXES.get(team, [])
    result = await db.execute(
        select(Employee).options(selectinload(Employee.role)).where(Employee.status == EmployeeStatus.ACTIVE)
    )
    all_emps = result.scalars().all()
    return [e for e in all_emps if e.role and any(e.role.code.startswith(p) for p in prefixes)]

async def get_hr_employees(db):
    return await get_team_employees(db, "hr")

async def notify_all_hr(db, title, message, notif_type, related_emp_id=None, action_url=None):
    for hr in await get_hr_employees(db):
        await create_notification(db, hr.id, title, message, notif_type, related_emp_id, action_url)

async def notify_team(db, team, title, message, notif_type, related_emp_id=None, action_url=None):
    for m in await get_team_employees(db, team):
        await create_notification(db, m.id, title, message, notif_type, related_emp_id, action_url)

async def create_team_task(db, team, title, description, task_type, related_employee_id,
                            assigned_by_id, priority="high", due_days=3, notes=None):
    members = await get_team_employees(db, team)
    if not members:
        return None
    due_date = date.today() + timedelta(days=due_days)
    team_tag = f"[team:{team}]"
    full_notes = f"{team_tag} {notes or ''}".strip()
    task = Task(
        title=title, description=description, task_type=task_type,
        status="pending", priority=priority,
        assigned_to=None, assigned_by=assigned_by_id,
        related_employee_id=related_employee_id, due_date=due_date, notes=full_notes,
    )
    db.add(task)
    await db.flush()
    for m in members:
        await create_notification(db, m.id, f"New Team Task: {title}",
            f"A task assigned to {team.upper()} team: {description[:100]}",
            "task_assigned", related_employee_id, "/tasks")
    return task

async def create_hr_fallback_task(db, skipped_step, employee, assigned_by_id):
    await create_team_task(
        db=db, team="hr",
        title=f"Complete Skipped Step: {skipped_step} — {employee.full_name}",
        description=(f"The onboarding step '{skipped_step}' was skipped for "
                     f"{employee.full_name} ({employee.employee_id}). HR must ensure this is completed."),
        task_type="onboarding", related_employee_id=employee.id,
        assigned_by_id=assigned_by_id, priority="high", due_days=2,
        notes=f"Skipped step during onboarding. Employee: {employee.employee_id}",
    )

# ── Check existing employee ───────────────────────────────────────────────────

@router.post("/check-existing")
async def check_existing_employee(data: CheckEmployeeRequest, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    from sqlalchemy import and_, func
    if not (data.first_name and data.last_name):
        return {"found": False, "employee": None, "message": "Full name required"}
    fn = data.first_name.strip().lower()
    ln = data.last_name.strip().lower()
    
    stmt = select(Employee).options(
        selectinload(Employee.salary),
        selectinload(Employee.bank_details),
        selectinload(Employee.department),
        selectinload(Employee.role)
    ).where(
        and_(func.lower(Employee.first_name)==fn, func.lower(Employee.last_name)==ln)
    )
    
    if data.personal_email:
        stmt = stmt.where(func.lower(Employee.personal_email)==data.personal_email.strip().lower())
    elif data.phone:
        stmt = stmt.where(Employee.phone==data.phone.strip())
    else:
        return {"found": False, "employee": None, "message": "Email or phone required"}
        
    result = await db.execute(stmt)
    candidates = result.scalars().all()
    
    if not candidates:
        return {"found": False, "employee": None, "message": "No existing employee found"}
    emp = candidates[0]
    # Fetch additional related data for pre-fill
    await db.refresh(emp, ["salary", "bank_details"])
    
    # Fetch Insurance
    ins_result = await db.execute(select(InsuranceInfo).where(InsuranceInfo.employee_id == emp.id))
    ins = ins_result.scalar_one_or_none()
    
    # Fetch Documents (verified)
    from app.models.models import EmployeeDocument
    doc_result = await db.execute(select(EmployeeDocument.document_type).where(EmployeeDocument.employee_id == emp.id))
    verified_docs = [row[0] for row in doc_result.fetchall()]

    wh_result = await db.execute(select(WorkHistory).where(WorkHistory.employee_id == emp.id))
    wh_list = wh_result.scalars().all()

    return {"found": True, "employee": {
        "id": str(emp.id), "employee_id": emp.employee_id, "name": emp.full_name,
        "first_name": emp.first_name, "last_name": emp.last_name,
        "email": emp.email, "personal_email": emp.personal_email, "phone": emp.phone,
        "gender": emp.gender,
        "date_of_birth": str(emp.date_of_birth) if emp.date_of_birth else None,
        "address": emp.address, "city": emp.city, "state": emp.state, "pincode": emp.pincode,
        "emergency_contact_name": emp.emergency_contact_name, "emergency_contact_phone": emp.emergency_contact_phone,
        "pan_number": emp.pan_number, "uan_number": emp.uan_number, "pf_number": emp.pf_number,
        "status": emp.status, "department": emp.department.name if emp.department else None,
        "role": emp.role.name if emp.role else None,
        "joining_date": str(emp.joining_date) if emp.joining_date else None,
        "relieving_date": str(emp.relieving_date) if emp.relieving_date else None,
        "previous_employee_id": emp.previous_employee_id,
        "previous_joining_date": str(emp.previous_joining_date) if emp.previous_joining_date else None,
        "previous_relieving_date": str(emp.previous_relieving_date) if emp.previous_relieving_date else None,
        # Salary pre-fill
        "salary": {
            "ctc": emp.salary.ctc, "basic": emp.salary.basic, "hra": emp.salary.hra,
            "special_allowance": emp.salary.special_allowance, "pf_contribution": emp.salary.pf_contribution,
            "bonus": emp.salary.bonus, "in_hand_salary": emp.salary.in_hand_salary
        } if emp.salary else None,
        # Bank pre-fill
        "bank": {
            "bank_name": emp.bank_details.bank_name, "account_holder_name": emp.bank_details.account_holder_name,
            "account_number": emp.bank_details.account_number, "ifsc_code": emp.bank_details.ifsc_code,
            "branch_name": emp.bank_details.branch_name, "account_type": emp.bank_details.account_type,
            "hdfc_customer_id": emp.bank_details.hdfc_customer_id, "hdfc_netbanking_id": emp.bank_details.hdfc_netbanking_id
        } if emp.bank_details else None,
        # Work History pre-fill
        "work_history": [
            {
                "company_name": wh.company_name, "designation": wh.designation, "department": wh.department,
                "from_date": str(wh.from_date) if wh.from_date else None,
                "to_date": str(wh.to_date) if wh.to_date else None,
                "is_current": wh.is_current, "is_intellativ": wh.is_intellativ,
                "reason_for_leaving": wh.reason_for_leaving, "last_ctc": wh.last_ctc
            } for wh in wh_list if not wh.is_intellativ
        ],
        # Insurance pre-fill
        "insurance": {
            "smoking_status": ins.smoking_status,
            "nominee_name": ins.nominee_name, "nominee_relation": ins.nominee_relation,
            "nominee_dob": str(ins.nominee_dob) if ins.nominee_dob else None,
            "nominee_phone": ins.nominee_phone, "blood_group": ins.blood_group,
            "pre_existing_conditions": ins.pre_existing_conditions,
            "spouse_name": ins.spouse_name, "spouse_dob": str(ins.spouse_dob) if ins.spouse_dob else None,
            "spouse_gender": ins.spouse_gender,
            "children": ins.children or [],
        } if ins else None,
        # Verified documents
        "verified_document_types": verified_docs
    }}

@router.post("/reactivate/{employee_id}")
async def reactivate_employee(employee_id: uuid.UUID, joining_date: date,
                               db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    if not can_onboard_employees(current_user):
        raise HTTPException(403, "Insufficient permissions")
    emp = await get_employee(db, employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")
    if emp.status not in [EmployeeStatus.RELIEVED, EmployeeStatus.INACTIVE]:
        raise HTTPException(400, f"Employee is {emp.status}, cannot reactivate")
    emp.status = EmployeeStatus.PENDING
    emp.joining_date = joining_date
    emp.relieving_date = None
    emp.employee_type = EmployeeType.REJOINING
    emp.updated_at = datetime.now(timezone.utc)
    ua_result = await db.execute(select(UserAccount).where(UserAccount.employee_id == emp.id))
    ua = ua_result.scalar_one_or_none()
    if ua:
        ua.is_active = True
    await db.flush()
    await notify_all_hr(db, f"Rejoining: {emp.full_name}", f"{emp.full_name} ({emp.employee_id}) is rejoining on {joining_date}", "onboarding", emp.id, f"/employees/{emp.id}")
    return {"message": "Employee reactivated", "employee_id": str(emp.id), "status": "pending"}

@router.post("/step-email")
async def send_step_email(data: StepEmailRequest, db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    if not can_onboard_employees(current_user):
        raise HTTPException(403, "Insufficient permissions")
    emp = await get_employee(db, data.employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")
    step_map = {
        1: ("Personal Info Captured", "personal details have been recorded"),
        2: ("Job Details Assigned", "department and role have been assigned"),
        3: ("Documents Uploaded", "documents have been uploaded and are pending verification"),
        4: ("Account Activated", "account has been activated and credentials sent"),
    }
    title, desc = step_map.get(data.step, ("Onboarding Update", "onboarding step completed"))
    try:
        send_step_notification(hr_email=current_user.email, employee_name=emp.full_name,
            employee_id=emp.employee_id, step=data.step, step_title=title, step_desc=desc, note=data.note)
    except Exception as e:
        print(f"Step email error: {e}")
    await notify_all_hr(db, f"Step {data.step}: {title}", f"{emp.full_name} — {desc}", "onboarding", emp.id, f"/employees/{emp.id}")
    await db.flush()
    return {"message": f"Step {data.step} notification sent"}

# ── Auto-task creation endpoints ──────────────────────────────────────────────

@router.post("/create-onboarding-tasks/{employee_id}")
async def create_onboarding_tasks(
    employee_id: uuid.UUID,
    skipped_insurance: bool = False,
    skipped_docs: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """Create all onboarding tasks for relevant teams after profile creation.
    Idempotent: skips task types that already exist for this employee to prevent duplicates.
    """
    if not can_onboard_employees(current_user):
        raise HTTPException(403, "Insufficient permissions")
    emp = await get_employee(db, employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")

    emp_name = emp.full_name
    emp_id_str = emp.employee_id
    dept = emp.department.name if emp.department else "Unknown Dept"
    tasks_created = []

    # ── Deduplication guard ─────────────────────────────────────────────────
    # Fetch all existing task titles for this employee so we never create duplicates
    existing_res = await db.execute(
        select(Task.title).where(Task.related_employee_id == employee_id)
    )
    existing_titles = {row[0] for row in existing_res.fetchall()}

    async def create_if_new(team, title, **kwargs):
        if title in existing_titles:
            return None  # already exists, skip
        t = await create_team_task(db=db, team=team, title=title, **kwargs)
        if t:
            existing_titles.add(title)  # prevent same-request duplicates too
        return t
    # ────────────────────────────────────────────────────────────────────────

    # ── IT Tasks ────────────────────────────────────────────────────────────
    # Only create "Create Email" task if New employee. For Rejoining, create "Re-enable Email"
    if emp.employee_type == EmployeeType.REJOINING:
        t = await create_if_new("it",
            title=f"Re-enable Company Email: {emp_name}",
            description=(f"Verify and re-enable company email for REJOINING employee {emp_name} ({emp_id_str}).\n"
                         f"• Existing Email: {emp.email}\n"
                         f"• Dept: {dept} | Re-joining: {emp.joining_date or 'TBD'}\n"
                         f"Reset credentials if needed and notify: {emp.personal_email or 'N/A'}"),
            task_type="onboarding", related_employee_id=emp.id, assigned_by_id=current_user.id,
            priority="urgent", due_days=1, notes=f"Reactivate email: {emp.email}")
        if t: tasks_created.append({"team": "IT", "task": "Re-enable Company Email", "id": str(t.id)})
    else:
        # IT: Create company email
        t = await create_if_new("it",
            title=f"Create Company Email: {emp_name}",
            description=(f"Set up company email for {emp_name} ({emp_id_str}).\n"
                         f"• Suggested: {emp.email or f'{emp.first_name.lower()}.{emp.last_name.lower()}@company.com'}\n"
                         f"• Dept: {dept} | Joining: {emp.joining_date or 'TBD'}\n"
                         f"Send credentials to: {emp.personal_email or 'N/A'}"),
            task_type="onboarding", related_employee_id=emp.id, assigned_by_id=current_user.id,
            priority="urgent", due_days=1, notes=f"Company email: {emp.email}")
        if t: tasks_created.append({"team": "IT", "task": "Create Company Email", "id": str(t.id)})

    # IT: Assign laptop & peripherals
    t = await create_if_new("it",
        title=f"Assign Laptop & Peripherals: {emp_name}",
        description=(f"Allocate laptop and peripherals for {emp_name} ({emp_id_str}).\n"
                     f"• Dept: {dept} | Joining: {emp.joining_date or 'TBD'}\n"
                     f"Standard kit: Laptop, Charger, Mouse, Keyboard, Headset.\n"
                     f"Update asset register after allocation."),
        task_type="asset", related_employee_id=emp.id, assigned_by_id=current_user.id,
        priority="high", due_days=2, notes="Assets: Laptop, Mouse, Keyboard, Charger, Headset")
    if t: tasks_created.append({"team": "IT", "task": "Assign Laptop & Peripherals", "id": str(t.id)})

    # IT: System access setup
    t = await create_if_new("it",
        title=f"Setup System Access: {emp_name}",
        description=(f"Configure system access for {emp_name} ({emp_id_str}).\n"
                     f"• Dept: {dept} | Role: {emp.role.name if emp.role else 'TBD'}\n"
                     f"• Add to Slack channels, Jira, GitHub org\n"
                     f"• VPN credentials • Role-based permissions"),
        task_type="onboarding", related_employee_id=emp.id, assigned_by_id=current_user.id,
        priority="high", due_days=3, notes="System: Slack, Jira, GitHub, VPN, permissions")
    if t: tasks_created.append({"team": "IT", "task": "Setup System Access", "id": str(t.id)})

    # HR: Verify documents
    t = await create_if_new("hr",
        title=f"Verify Documents: {emp_name}",
        description=(f"Verify all uploaded documents for {emp_name} ({emp_id_str}).\n"
                     f"Required: Aadhar Card ✓, PAN Card ✓\n"
                     f"Optional: Passport, Degree, Experience Letter\n"
                     f"Mark verified in employee profile."),
        task_type="document", related_employee_id=emp.id, assigned_by_id=current_user.id,
        priority="high", due_days=3, notes="Docs: Aadhar, PAN, Passport, Degree, Experience Letter")
    if t: tasks_created.append({"team": "HR", "task": "Verify Documents", "id": str(t.id)})

    # HR: Onboarding checklist
    t = await create_if_new("hr",
        title=f"Complete Onboarding Checklist: {emp_name}",
        description=(f"Complete HR onboarding checklist for {emp_name} ({emp_id_str}).\n"
                     f"• Offer letter signed • NDA signed • Payroll setup\n"
                     f"• Attendance system • Schedule induction training"),
        task_type="onboarding", related_employee_id=emp.id, assigned_by_id=current_user.id,
        priority="high", due_days=3, notes="HR checklist: payroll, attendance, induction, policies")
    if t: tasks_created.append({"team": "HR", "task": "Complete Onboarding Checklist", "id": str(t.id)})

    # Admin: ID card & welcome kit
    t = await create_if_new("admin",
        title=f"Print ID Card & Welcome Kit: {emp_name}",
        description=(f"Prepare ID card and welcome kit for {emp_name} ({emp_id_str}).\n"
                     f"• Print & laminate employee ID card\n"
                     f"• Welcome kit (stationary, swag) • Assign desk • Visitor access"),
        task_type="onboarding", related_employee_id=emp.id, assigned_by_id=current_user.id,
        priority="medium", due_days=3, notes="Admin: ID card, welcome kit, seating, access card")
    if t: tasks_created.append({"team": "Admin", "task": "Print ID Card & Welcome Kit", "id": str(t.id)})

    # Skipped step fallbacks
    if skipped_insurance:
        await create_hr_fallback_task(db, "Insurance Information", emp, current_user.id)
        tasks_created.append({"team": "HR", "task": "Follow up: Skipped Insurance Step", "id": "fallback"})
    if skipped_docs:
        await create_hr_fallback_task(db, "Document Upload", emp, current_user.id)
        tasks_created.append({"team": "HR", "task": "Follow up: Skipped Document Upload", "id": "fallback"})

    await db.flush()
    return {"message": f"Created {len(tasks_created)} onboarding tasks across teams", "tasks": tasks_created}


@router.post("/create-activation-tasks/{employee_id}")
async def create_activation_tasks(employee_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                                   current_user: Employee = Depends(get_current_user)):
    if not can_onboard_employees(current_user):
        raise HTTPException(403, "Insufficient permissions")
    emp = await get_employee(db, employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")
    tasks_created = []

    # Deduplication guard
    existing_res = await db.execute(
        select(Task.title).where(Task.related_employee_id == employee_id)
    )
    existing_titles = {row[0] for row in existing_res.fetchall()}

    async def create_if_new(team, title, **kwargs):
        if title in existing_titles:
            return None
        t = await create_team_task(db=db, team=team, title=title, **kwargs)
        if t: existing_titles.add(title)
        return t

    t = await create_if_new("it",
        title=f"Final IT Setup Check: {emp.full_name}",
        description=(f"Confirm all IT setup complete for {emp.full_name} ({emp.employee_id}).\n"
                     f"• Company email active ✓ • Laptop configured ✓\n"
                     f"• All system accesses working ✓ • VPN configured ✓"),
        task_type="onboarding", related_employee_id=emp.id, assigned_by_id=current_user.id,
        priority="high", due_days=1)
    if t: tasks_created.append({"team": "IT", "task": "Final IT Setup Check"})
    t = await create_if_new("admin",
        title=f"Office Induction: {emp.full_name}",
        description=(f"Conduct office induction for {emp.full_name} ({emp.employee_id}).\n"
                     f"• Office tour • Meet team • Access card • Safety briefing"),
        task_type="onboarding", related_employee_id=emp.id, assigned_by_id=current_user.id,
        priority="medium", due_days=1)
    if t: tasks_created.append({"team": "Admin", "task": "Office Induction"})

    # Check for pending items to assign to the EMPLOYEE
    from sqlalchemy import func as sqlfunc
    from app.models.models import EmployeeDocument, InsuranceInfo, WorkHistory
    missing = []
    FLABELS = {
        "personal_email": "Personal Email", "phone": "Phone Number", "date_of_birth": "Date of Birth",
        "gender": "Gender", "address": "Address", "emergency_contact_phone": "Emergency Contact"
    }
    for f, lab in FLABELS.items():
        if not getattr(emp, f, None):
            missing.append(lab)
            
    doc_cnt = (await db.execute(select(sqlfunc.count(EmployeeDocument.id)).where(EmployeeDocument.employee_id == employee_id))).scalar()
    if doc_cnt < 2:
        missing.append("Upload Mandatory Documents (ID & Address Proof)")
        
    ins = (await db.execute(select(InsuranceInfo).where(InsuranceInfo.employee_id == employee_id))).scalar_one_or_none()
    if not ins or not ins.nominee_name:
        missing.append("Insurance Nominee Details")
        
    wh_cnt = (await db.execute(select(sqlfunc.count(WorkHistory.id)).where(WorkHistory.employee_id == employee_id))).scalar()
    if wh_cnt == 0:
        missing.append("Work History")

    if missing:
        desc = "Please log in and fill in the following pending details:\n\n" + "\n".join(f"• {m}" for m in missing)
        ptask = Task(
            title=f"Complete Your Profile — {emp.full_name}",
            description=desc, task_type="profile_completion", status="pending",
            priority="high", assigned_to=emp.id, assigned_by=current_user.id,
            related_employee_id=emp.id, due_date=date.today() + timedelta(days=3),
            notes="Auto-assigned pending tasks at activation"
        )
        db.add(ptask)
        tasks_created.append({"team": "Employee", "task": "Complete Profile"})

    await db.flush()
    return {"message": f"Created {len(tasks_created)} activation tasks", "tasks": tasks_created}


# ── Team Tasks view ───────────────────────────────────────────────────────────

@router.get("/team-tasks")
async def get_team_tasks(db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    """Return tasks for the current user's team, showing who is working on each."""
    if not current_user.role:
        return []
    user_code = current_user.role.code
    team_tag = None
    for team, prefixes in TEAM_PREFIXES.items():
        if any(user_code.startswith(p) for p in prefixes):
            team_tag = team
            break
    if not team_tag:
        return []
    result = await db.execute(
        select(Task).where(Task.notes.contains(f"[team:{team_tag}]")).order_by(Task.created_at.desc())
    )
    tasks = result.scalars().all()
    emp_ids = list(set(filter(None, [t.assigned_to for t in tasks] + [t.related_employee_id for t in tasks] + [t.assigned_by for t in tasks])))
    emp_map = {}
    if emp_ids:
        er = await db.execute(select(Employee).where(Employee.id.in_(emp_ids)))
        for e in er.scalars().all():
            emp_map[e.id] = e
    return [{
        "id": str(t.id), "title": t.title, "description": t.description,
        "task_type": t.task_type, "status": t.status, "priority": t.priority,
        "assigned_to": str(t.assigned_to) if t.assigned_to else None,
        "assigned_to_name": f"{emp_map[t.assigned_to].first_name} {emp_map[t.assigned_to].last_name}" if t.assigned_to and t.assigned_to in emp_map else None,
        "assigned_by": str(t.assigned_by) if t.assigned_by else None,
        "assigned_by_name": f"{emp_map[t.assigned_by].first_name} {emp_map[t.assigned_by].last_name}" if t.assigned_by and t.assigned_by in emp_map else None,
        "related_employee_id": str(t.related_employee_id) if t.related_employee_id else None,
        "related_employee_name": f"{emp_map[t.related_employee_id].first_name} {emp_map[t.related_employee_id].last_name}" if t.related_employee_id and t.related_employee_id in emp_map else None,
        "due_date": str(t.due_date) if t.due_date else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "notes": t.notes, "created_at": t.created_at.isoformat(),
        "is_team_task": True, "team": team_tag,
    } for t in tasks]

# ── Work History ──────────────────────────────────────────────────────────────

@router.get("/work-history/{employee_id}")
async def get_work_history(employee_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    is_self = str(current_user.id) == str(employee_id)
    if not is_self and not can_view_employee_detail(current_user, employee_id):
        raise HTTPException(403, "Access denied")
    result = await db.execute(
        select(WorkHistory)
        .where(WorkHistory.employee_id == employee_id)
        .order_by(WorkHistory.is_intellativ.desc(), WorkHistory.from_date.desc())
    )
    rows = result.scalars().all()
    return [{
        "id": str(r.id),
        "company_name": r.company_name,
        "designation": r.designation,
        "department": r.department,
        "start_date": str(r.from_date) if r.from_date else None,
        "end_date": str(r.to_date) if r.to_date else None,
        "is_current": r.is_current,
        "is_intellativ": r.is_intellativ,
        "reason_for_leaving": r.reason_for_leaving,
        "salary": r.last_ctc,
    } for r in rows]

@router.post("/work-history/{employee_id}")
async def add_work_history(employee_id: uuid.UUID, data: WorkHistoryCreate, db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    is_self = str(current_user.id) == str(employee_id)
    is_privileged = is_hr_or_admin(current_user)

    if not is_self and not is_privileged:
        raise HTTPException(403, "Access denied")

    payload = data.model_dump()
    is_current = payload.pop("is_current", False)
    is_intellativ_entry = payload.pop("is_intellativ", False)

    # Self can only add past (external) work history — not internal company records
    if is_self and not is_privileged:
        if is_intellativ_entry:
            raise HTTPException(403, "You cannot add internal company work history records")
        # Self cannot mark a record as current for intellativ
        is_intellativ_entry = False

    wh = WorkHistory(
        employee_id=employee_id,
        company_name=payload["company_name"],
        designation=payload.get("designation"),
        department=payload.get("department"),
        from_date=payload["from_date"],
        to_date=None if is_current else payload.get("to_date"),
        reason_for_leaving=payload.get("reason_for_leaving"),
        last_ctc=payload.get("last_ctc"),
        is_intellativ=is_intellativ_entry,
    )
    db.add(wh)
    await db.flush()
    await db.refresh(wh)
    
    await check_and_complete_profile_tasks(db, employee_id)
    return {"id": str(wh.id), "message": "Work history added"}


@router.put("/work-history/{wh_id}")
async def update_work_history(wh_id: uuid.UUID, data: WorkHistoryCreate, db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    result = await db.execute(select(WorkHistory).where(WorkHistory.id == wh_id))
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(404, "Not found")

    is_self = str(current_user.id) == str(wh.employee_id)
    is_privileged = is_hr_or_admin(current_user)

    if not is_self and not is_privileged:
        raise HTTPException(403, "Access denied")

    # Self cannot edit intellativ (current company) records — only HR/superadmin can
    if is_self and not is_privileged and wh.is_intellativ:
        raise HTTPException(403, "You cannot edit current company work history. Contact HR.")

    payload = data.model_dump()
    is_current = payload.pop("is_current", False)
    payload.pop("is_intellativ", None)  # Don't allow changing is_intellativ via update

    wh.company_name = payload["company_name"]
    wh.designation = payload.get("designation")
    wh.department = payload.get("department")
    wh.from_date = payload["from_date"]
    wh.to_date = None if is_current else payload.get("to_date")
    wh.reason_for_leaving = payload.get("reason_for_leaving")
    wh.last_ctc = payload.get("last_ctc")
    await db.flush()
    
    await check_and_complete_profile_tasks(db, wh.employee_id)
    return {"message": "Work history updated"}

@router.delete("/work-history/{wh_id}")
async def delete_work_history(wh_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    result = await db.execute(select(WorkHistory).where(WorkHistory.id == wh_id))
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(404, "Not found")

    is_self = str(current_user.id) == str(wh.employee_id)
    is_privileged = is_hr_or_admin(current_user)

    if not is_self and not is_privileged:
        raise HTTPException(403, "Access denied")

    # Self cannot delete intellativ (current company) records
    if is_self and not is_privileged and wh.is_intellativ:
        raise HTTPException(403, "You cannot delete current company work history. Contact HR.")

    await db.delete(wh)
    await db.flush()
    
    await check_and_complete_profile_tasks(db, wh.employee_id)
    return {"message": "Deleted"}

# ── Insurance ─────────────────────────────────────────────────────────────────

@router.get("/insurance/{employee_id}")
async def get_insurance(employee_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    is_self = str(current_user.id) == str(employee_id)
    if not is_self and not can_view_employee_detail(current_user, employee_id):
        raise HTTPException(403, "Access denied")
    result = await db.execute(select(InsuranceInfo).where(InsuranceInfo.employee_id == employee_id))
    ins = result.scalar_one_or_none()
    if not ins:
        return None
    return {
        "id": str(ins.id),
        "smoking_status": ins.smoking_status,
        "nominee_name": ins.nominee_name,
        "nominee_relation": ins.nominee_relation,
        "nominee_dob": str(ins.nominee_dob) if ins.nominee_dob else None,
        "nominee_phone": ins.nominee_phone,
        "blood_group": ins.blood_group,
        "pre_existing_conditions": ins.pre_existing_conditions,
        "spouse_name": ins.spouse_name,
        "spouse_dob": str(ins.spouse_dob) if ins.spouse_dob else None,
        "spouse_gender": ins.spouse_gender,
        "children": ins.children or [],
        "submitted": ins.submitted,
        "submitted_at": str(ins.submitted_at) if ins.submitted_at else None,
    }


@router.post("/insurance/{employee_id}")
async def save_insurance(
    employee_id: uuid.UUID,
    data: InsuranceInfoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    if str(current_user.id) != str(employee_id) and not is_hr_or_admin(current_user):
        raise HTTPException(403, "Access denied")

    result = await db.execute(select(InsuranceInfo).where(InsuranceInfo.employee_id == employee_id))
    ins = result.scalar_one_or_none()

    payload = data.model_dump(exclude_unset=True)  # Optional: cleaner

    # Normalize phone
    if payload.get("nominee_phone") == "":
        payload["nominee_phone"] = None

    # Fix dates in children for JSONB compatibility
    if payload.get("children"):
        children_list = []
        for c in payload["children"]:
            child_dict = c if isinstance(c, dict) else c.model_dump()
            if child_dict.get("dob") and isinstance(child_dict["dob"], (date, datetime)):
                child_dict["dob"] = child_dict["dob"].isoformat()  # "2026-03-30"
            children_list.append(child_dict)
        payload["children"] = children_list
    else:
        payload["children"] = []

    if ins:
        for k, v in payload.items():
            setattr(ins, k, v)
        ins.updated_at = datetime.now(timezone.utc)
    else:
        ins = InsuranceInfo(employee_id=employee_id, **payload)
        db.add(ins)

    await db.flush()          # This is where the error was raised
    await db.refresh(ins)

    await check_and_complete_profile_tasks(db, employee_id)

    return {"message": "Insurance info saved", "id": str(ins.id)}

@router.post("/insurance/{employee_id}/submit")
async def submit_insurance(employee_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                            current_user: Employee = Depends(get_current_user)):
    emp = await get_employee(db, employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")
    result = await db.execute(select(InsuranceInfo).where(InsuranceInfo.employee_id==employee_id))
    ins = result.scalar_one_or_none()
    if not ins:
        raise HTTPException(400, "Fill insurance info first")
    ins.submitted = True
    ins.submitted_at = datetime.now(timezone.utc)
    await db.flush()
    insurance_email = settings.INSURANCE_TEAM_EMAIL or settings.HR_NOTIFICATION_EMAIL or settings.SMTP_FROM

    # Build children summary for email and task
    children_list = ins.children or []
    if children_list:
        children_lines = "\n".join(
            f"  • Child {i+1}: {c.get('name','N/A')} | DOB: {c.get('dob','N/A')} | Gender: {c.get('gender','N/A')}"
            for i, c in enumerate(children_list)
        )
    else:
        children_lines = "  None"

    try:
        send_insurance_request(
            to_email=insurance_email,
            employee_name=emp.full_name,
            employee_id=emp.employee_id,
            department=emp.department.name if emp.department else "",
            joining_date=str(emp.joining_date) if emp.joining_date else "",
            blood_group=ins.blood_group or "",
            pre_existing=ins.pre_existing_conditions or "",
            smoking_status=ins.smoking_status or "",
            nominee_name=ins.nominee_name or "",
            nominee_relation=ins.nominee_relation or "",
            nominee_dob=ins.nominee_dob or "",
            nominee_phone=ins.nominee_phone or "",
            spouse_name=ins.spouse_name or "",
            spouse_dob=ins.spouse_dob or "",
            spouse_gender=ins.spouse_gender or "",
            children_info=children_lines,
        )
    except Exception as e:
        print(f"Insurance email error: {e}")

    # Insurance team: process enrollment
    await create_team_task(db=db, team="insurance",
        title=f"Enroll in Group Insurance: {emp.full_name}",
        description=(
            f"Process group insurance enrollment for {emp.full_name} ({emp.employee_id}).\n"
            f"• Dept: {emp.department.name if emp.department else 'N/A'} | Joining: {emp.joining_date or 'TBD'}\n"
            f"• Blood Group: {ins.blood_group or 'Not specified'} | Smoking: {ins.smoking_status or 'N/A'}\n"
            f"• Pre-existing Conditions: {ins.pre_existing_conditions or 'None'}\n"
            f"\nNominee Details:\n"
            f"  • Name: {ins.nominee_name or 'N/A'} | Relation: {ins.nominee_relation or 'N/A'}\n"
            f"  • DOB: {ins.nominee_dob or 'N/A'} | Phone: {ins.nominee_phone or 'N/A'}\n"
            f"\nSpouse Details:\n"
            f"  • Name: {ins.spouse_name or 'N/A'} | DOB: {ins.spouse_dob or 'N/A'} | Gender: {ins.spouse_gender or 'N/A'}\n"
            f"\nChildren:\n{children_lines}\n"
            f"\nCollect enrollment form, assign policy number, confirm coverage."
        ),
        task_type="insurance", related_employee_id=emp.id, assigned_by_id=current_user.id,
        priority="high", due_days=5,
        notes=f"Nominee: {ins.nominee_name} ({ins.nominee_relation}). Blood group: {ins.blood_group}. Children: {len(children_list)}")

    # HR: collect insurance documents
    await create_team_task(db=db, team="hr",
        title=f"Collect Insurance Documents: {emp.full_name}",
        description=(f"Collect and file insurance documents for {emp.full_name} ({emp.employee_id}).\n"
                     f"• Nominee ID proof\n• Signed insurance nomination form\n"
                     f"• Medical history declaration (if pre-existing conditions)\n"
                     f"File originals in employee folder."),
        task_type="insurance", related_employee_id=emp.id, assigned_by_id=current_user.id,
        priority="high", due_days=5, notes="Insurance docs: nomination form, nominee ID, medical declaration")

    await notify_all_hr(db, f"Insurance Submitted: {emp.full_name}", f"Insurance details submitted for {emp.full_name}", "insurance", emp.id)
    return {"message": "Insurance submitted, tasks created for Insurance & HR teams"}

# ── Email Setup Request ───────────────────────────────────────────────────────

@router.post("/request-email-setup/{employee_id}")
async def request_email_setup(employee_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                               current_user: Employee = Depends(get_current_user)):
    if not can_onboard_employees(current_user):
        raise HTTPException(403, "Insufficient permissions")
    emp = await get_employee(db, employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")
    it_email = settings.IT_TEAM_EMAIL or settings.HR_NOTIFICATION_EMAIL or settings.SMTP_FROM
    try:
        send_email_setup_request(to_email=it_email, employee_name=emp.full_name, employee_id=emp.employee_id,
            company_email=emp.email, department=emp.department.name if emp.department else "",
            role=emp.role.name if emp.role else "", joining_date=str(emp.joining_date) if emp.joining_date else "",
            requested_by=current_user.full_name)
    except Exception as e:
        print(f"Email setup error: {e}")
    result = await db.execute(select(Employee).options(selectinload(Employee.role)).where(Employee.status==EmployeeStatus.ACTIVE))
    all_emps = result.scalars().all()
    it_emps = [e for e in all_emps if e.role and e.role.code.startswith("IT-")]
    for it_emp in it_emps[:5]:
        await create_notification(db, it_emp.id, f"Email Setup Required: {emp.full_name}",
            f"Create company email {emp.email} for {emp.full_name} ({emp.employee_id})", "email_setup", emp.id, f"/employees/{emp.id}")
    await db.flush()
    return {"message": "Email setup request sent to IT team"}

# ── Notifications ─────────────────────────────────────────────────────────────

@router.get("/notifications")
async def get_notifications(unread_only: bool = False, db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    query = select(Notification).where(Notification.recipient_employee_id==current_user.id)
    if unread_only:
        query = query.where(Notification.is_read == False)
    query = query.order_by(Notification.created_at.desc()).limit(50)
    result = await db.execute(query)
    notifs = result.scalars().all()
    return [{"id": str(n.id), "title": n.title, "message": n.message, "type": n.notification_type,
             "is_read": n.is_read, "action_url": n.action_url, "created_at": n.created_at.isoformat()} for n in notifs]

@router.get("/notifications/count")
async def notification_count(db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    from sqlalchemy import func
    count = (await db.execute(select(func.count(Notification.id)).where(
        Notification.recipient_employee_id==current_user.id, Notification.is_read==False))).scalar()
    return {"unread": count}

@router.put("/notifications/{notif_id}/read")
async def mark_read(notif_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    result = await db.execute(select(Notification).where(Notification.id==notif_id, Notification.recipient_employee_id==current_user.id))
    n = result.scalar_one_or_none()
    if n:
        n.is_read = True
        await db.flush()
    return {"message": "Marked as read"}

@router.put("/notifications/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    await db.execute(update(Notification).where(Notification.recipient_employee_id==current_user.id, Notification.is_read==False).values(is_read=True))
    return {"message": "All marked as read"}

# ── Pending Onboarding Employees ──────────────────────────────────────────────

@router.get("/pending-employees")
async def get_pending_onboarding_employees(
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """
    Return employees who still have incomplete onboarding steps.
    Includes BOTH:
      - status=pending  (not yet activated)
      - status=active   (activated but skipped docs/insurance during onboarding)
    Completion is determined by checking actual DB records, not just flags.
    """
    from sqlalchemy import func
    from app.models.models import WorkHistory, InsuranceInfo, EmployeeDocument

    if not can_onboard_employees(current_user):
        raise HTTPException(403, "Insufficient permissions")

    # Fetch pending AND active employees (active may have skipped steps)
    result = await db.execute(
        select(Employee)
        .options(
            selectinload(Employee.department),
            selectinload(Employee.role),
            selectinload(Employee.documents),
        )
        .where(Employee.status.in_([EmployeeStatus.PENDING, EmployeeStatus.ACTIVE]))
        .order_by(Employee.created_at.desc())
    )
    employees = result.scalars().all()

    out = []
    for emp in employees:
        # Work history count
        wh_res = await db.execute(
            select(func.count()).select_from(WorkHistory).where(WorkHistory.employee_id == emp.id)
        )
        wh_count = wh_res.scalar() or 0

        # Insurance info
        ins_res = await db.execute(
            select(InsuranceInfo).where(InsuranceInfo.employee_id == emp.id)
        )
        insurance = ins_res.scalar_one_or_none()

        has_personal  = bool(emp.first_name and emp.last_name and emp.personal_email and emp.phone)
        has_job       = bool(emp.department_id and emp.joining_date)
        has_docs      = len(emp.documents) > 0
        has_wh        = wh_count > 0
        has_insurance = insurance is not None and bool(insurance.nominee_name)
        docs_verified = all(d.is_verified for d in emp.documents) if emp.documents else False
        insurance_submitted = insurance.submitted if insurance else False

        # Missing steps — what still needs to be done
        missing = []
        if not has_personal:  missing.append("Personal Info")
        if not has_job:       missing.append("Job Details")
        if not has_docs:      missing.append("Documents")
        if not has_insurance: missing.append("Insurance")

        steps_done  = sum([has_personal, has_job, has_docs, has_insurance])
        total_steps = 4

        # Only include employees who have at least one incomplete step
        if steps_done == total_steps and emp.status == EmployeeStatus.ACTIVE:
            continue  # fully complete and active — skip

        out.append({
            "id": str(emp.id),
            "employee_id": emp.employee_id,
            "name": emp.full_name,
            "first_name": emp.first_name,
            "last_name": emp.last_name,
            "personal_email": emp.personal_email,
            "phone": emp.phone,
            "gender": emp.gender,
            "date_of_birth": str(emp.date_of_birth) if emp.date_of_birth else None,
            "address": emp.address,
            "city": emp.city,
            "state": emp.state,
            "pincode": emp.pincode,
            "emergency_contact_name": emp.emergency_contact_name,
            "emergency_contact_phone": emp.emergency_contact_phone,
            "department_id": str(emp.department_id) if emp.department_id else None,
            "department": emp.department.name if emp.department else None,
            "role_id": str(emp.role_id) if emp.role_id else None,
            "role": emp.role.name if emp.role else None,
            "joining_date": str(emp.joining_date) if emp.joining_date else None,
            "employee_type": emp.employee_type,
            "employee_status": emp.status,
            "created_at": emp.created_at.isoformat(),
            "completion": {
                "has_personal_info":     has_personal,
                "has_job_details":       has_job,
                "has_documents":         has_docs,
                "has_work_history":      has_wh,
                "has_insurance":         has_insurance,
                "docs_verified":         docs_verified,
                "insurance_submitted":   insurance_submitted,
                "missing_steps":         missing,
                "steps_done":            steps_done,
                "total_steps":           total_steps,
                "percent":               int((steps_done / total_steps) * 100),
            }
        })

    return out

# ── Send Joining Details Email ────────────────────────────────────────────────

@router.post("/send-joining-details-email/{employee_id}")
async def send_joining_details_email_endpoint(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """
    Send an email to the employee's personal email with their login credentials
    and a link to complete pending documents/insurance details.
    """
    if not can_onboard_employees(current_user):
        raise HTTPException(403, "Insufficient permissions")

    emp = await get_employee(db, employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")

    if not emp.personal_email:
        raise HTTPException(400, "Employee has no personal email on record")

    # Get user account for credentials
    ua_result = await db.execute(select(UserAccount).where(UserAccount.employee_id == emp.id))
    ua = ua_result.scalar_one_or_none()
    if not ua:
        raise HTTPException(400, "Employee has no user account yet. Please activate the employee first.")

    # Determine what's missing
    from app.models.models import InsuranceInfo, EmployeeDocument
    from sqlalchemy import func as sqlfunc

    docs_result = await db.execute(
        select(EmployeeDocument).where(EmployeeDocument.employee_id == emp.id)
    )
    docs = docs_result.scalars().all()

    ins_result = await db.execute(select(InsuranceInfo).where(InsuranceInfo.employee_id == emp.id))
    ins = ins_result.scalar_one_or_none()

    missing_items = []
    if not docs:
        missing_items.append("Documents not uploaded (Aadhar, PAN, etc.)")
    elif len(docs) < 2:
        missing_items.append(f"Only {len(docs)} document(s) uploaded — please upload required documents")
    if not ins or not ins.nominee_name:
        missing_items.append("Insurance details not filled (nominee, blood group, etc.)")

    if not missing_items:
        missing_items.append("Please review and confirm your joining details")

    try:
        send_joining_details_email(
            personal_email=emp.personal_email,
            employee_name=emp.full_name,
            employee_id=emp.employee_id,
            username=ua.username,
            temp_password="[Your current password]",
            missing_items=missing_items,
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to send email: {str(e)}")

    await notify_all_hr(
        db,
        f"Joining Details Email Sent: {emp.full_name}",
        f"Email sent to {emp.personal_email} requesting completion of pending joining details.",
        "onboarding", emp.id,
    )
    await db.flush()
    return {"message": f"Joining details email sent to {emp.personal_email}", "missing_items": missing_items}


# ── Employee Self-Service: Joining Details ────────────────────────────────────

@router.get("/my-joining-status")
async def get_my_joining_status(
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """
    Returns the current employee's onboarding completion status
    along with their profile, documents, and insurance summary.
    """
    from app.models.models import InsuranceInfo, EmployeeDocument
    from sqlalchemy.orm import selectinload as sl

    emp_result = await db.execute(
        select(Employee)
        .options(sl(Employee.documents), sl(Employee.department), sl(Employee.role))
        .where(Employee.id == current_user.id)
    )
    emp = emp_result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Employee not found")

    ins_result = await db.execute(select(InsuranceInfo).where(InsuranceInfo.employee_id == emp.id))
    ins = ins_result.scalar_one_or_none()

    has_docs = len(emp.documents) > 0
    has_insurance = ins is not None and bool(ins.nominee_name)
    insurance_submitted = ins.submitted if ins else False

    return {
        "employee": {
            "id": str(emp.id),
            "employee_id": emp.employee_id,
            "name": emp.full_name,
            "first_name": emp.first_name,
            "last_name": emp.last_name,
            "email": emp.email,
            "personal_email": emp.personal_email,
            "phone": emp.phone,
            "gender": emp.gender,
            "date_of_birth": str(emp.date_of_birth) if emp.date_of_birth else None,
            "address": emp.address,
            "city": emp.city,
            "state": emp.state,
            "pincode": emp.pincode,
            "emergency_contact_name": emp.emergency_contact_name,
            "emergency_contact_phone": emp.emergency_contact_phone,
            "department": emp.department.name if emp.department else None,
            "role": emp.role.name if emp.role else None,
            "joining_date": str(emp.joining_date) if emp.joining_date else None,
            "status": emp.status,
            "employee_type": emp.employee_type,
        },
        "completion": {
            "has_documents": has_docs,
            "document_count": len(emp.documents),
            "has_insurance": has_insurance,
            "insurance_submitted": insurance_submitted,
        },
        "documents": [
            {
                "id": str(d.id),
                "document_type": d.document_type,
                "document_name": d.document_name,
                "is_verified": d.is_verified,
                "uploaded_at": d.uploaded_at.isoformat(),
            }
            for d in emp.documents
        ],
        "insurance": {
            "nominee_name": ins.nominee_name if ins else None,
            "nominee_relation": ins.nominee_relation if ins else None,
            "blood_group": ins.blood_group if ins else None,
            "smoking_status": ins.smoking_status if ins else None,
            "pre_existing_conditions": ins.pre_existing_conditions if ins else None,
            "submitted": insurance_submitted,
        } if ins else None,
    }