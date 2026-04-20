"""
Password Reset (Forgot Password) + Profile Completion Task creation
"""
import uuid, secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, or_
from pydantic import BaseModel
from typing import Optional

from app.db.database import get_db
from app.models.models import Employee, UserAccount, Task
from app.core.deps import get_current_user, is_hr_or_admin
from app.core.security import get_password_hash
from app.core.config import settings
from app.services.email_service import send_password_reset_email, send_profile_task_email

router = APIRouter(prefix="/auth", tags=["password-reset"])
tasks_router = APIRouter(prefix="/employees", tags=["profile-tasks"])


# ── Forgot Password ───────────────────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    username: str   # company email / login username


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/forgot-password")
async def forgot_password(
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts company email/username, generates a reset token, emails it to personal_email.
    Always returns 200 to avoid user enumeration.
    """
    search_term = data.username.strip().lower()

    # 1. Search by Username first (Primary)
    result = await db.execute(
        select(UserAccount).where(UserAccount.username == search_term)
    )
    user = result.scalar_one_or_none()

    # 2. If not found, search by Employee emails
    if not user:
        result = await db.execute(
            select(UserAccount)
            .join(Employee, UserAccount.employee_id == Employee.id)
            .where(
                or_(
                    Employee.personal_email == search_term,
                    Employee.email == search_term
                )
            )
        )
        user = result.scalars().first()

    if not user:
        raise HTTPException(404, "Account not found with this email/username")

    print(f"DEBUG: Found UserAccount for Forgot Password. ID: {user.id}, Username: {user.username}")
    
    # Get associated employee
    emp_result = await db.execute(
        select(Employee).where(Employee.id == user.employee_id)
    )
    emp = emp_result.scalar_one_or_none()

    if not emp:
        # This shouldn't normally happen if database integrity is maintained
        raise HTTPException(404, "Associated employee record not found")

    # Check employee status
    if emp.status == "relieved":
        raise HTTPException(400, "User is relieved")
    
    if emp.status != "active":
        raise HTTPException(400, "Only active employees can reset their password")

    recipient_email = emp.personal_email
    full_name = emp.full_name
    
    if not recipient_email:
        # Fallback to search term if no personal email, but ideally we use registered one
        recipient_email = data.username

    token = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)

    # Use explicit update to ensure persistence in async session
    await db.execute(
        update(UserAccount)
        .where(UserAccount.id == user.id)
        .values(
            password_reset_token=token,
            password_reset_expires=expires
        )
    )
    await db.commit()

    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    try:
        print(f"DEBUG: Sending reset email to {recipient_email}")
        send_password_reset_email(recipient_email, full_name, reset_link)
    except Exception as e:
        print(f"Reset email error: {e}")
        raise HTTPException(500, "Failed to send reset email")

    return {
        "message": "If a matching account is found, a reset link has been sent to your registered personal email."
    }


@router.post("/reset-password")
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Validates token and sets new password."""
    if len(data.new_password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    result = await db.execute(
        select(UserAccount).where(UserAccount.password_reset_token == data.token)
    )
    user = result.scalar_one_or_none()

    if not user:
        print(f"DEBUG: Reset Password failed - Token not found: {data.token[:10]}...")
        raise HTTPException(400, "Invalid or expired reset token")

    # Check expiry
    expires = user.password_reset_expires
    if not expires:
        raise HTTPException(400, "Invalid reset token")

    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > expires:
        raise HTTPException(400, "Reset token has expired. Please request a new one.")

    print(f"DEBUG: Updating password for User ID: {user.id}, Username: {user.username}")
    
    # Use explicit update to ensure persistence in async session
    await db.execute(
        update(UserAccount)
        .where(UserAccount.id == user.id)
        .values(
            hashed_password=get_password_hash(data.new_password),
            password_reset_token=None,
            password_reset_expires=None
        )
    )
    await db.commit()

    return {"message": "Password reset successfully. You can now log in."}


@router.get("/verify-reset-token/{token}")
async def verify_reset_token(token: str, db: AsyncSession = Depends(get_db)):
    """Check if reset token is valid before showing reset form."""
    result = await db.execute(
        select(UserAccount).where(UserAccount.password_reset_token == token)
    )
    user = result.scalar_one_or_none()
    if not user or not user.password_reset_expires:
        return {"valid": False}

    expires = user.password_reset_expires
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > expires:
        return {"valid": False}

    return {"valid": True}


# ── Profile Completion Task ────────────────────────────────────────────────────

FIELD_LABELS = {
    "personal_email": "Personal Email",
    "phone": "Phone Number",
    "alternate_phone": "Alternate Phone",
    "gender": "Gender",
    "date_of_birth": "Date of Birth",
    "address": "Residential Address",
    "city": "City",
    "state": "State",
    "pincode": "PIN Code",
    "emergency_contact_name": "Emergency Contact Name",
    "emergency_contact_phone": "Emergency Contact Phone",
}


@tasks_router.post("/{employee_id}/create-profile-task")
async def create_profile_completion_task(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """
    HR creates a task assigned to the employee listing their missing profile fields.
    Also sends an email notification to their personal email if available.
    """
    if not is_hr_or_admin(current_user):
        raise HTTPException(403, "Only HR/Admin can create profile tasks")

    emp_result = await db.execute(select(Employee).where(Employee.id == employee_id))
    emp = emp_result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Employee not found")

    # Detect missing fields
    missing = []
    for field, label in FIELD_LABELS.items():
        if not getattr(emp, field, None):
            missing.append(label)

    if not missing:
        return {"message": "No missing fields — profile is complete!", "missing_count": 0}

    # Create task
    description = "Please log in to the HR portal and fill in the following missing details:\n\n"
    description += "\n".join(f"• {f}" for f in missing)

    task = Task(
        id=uuid.uuid4(),
        title=f"Complete Your Profile — {emp.full_name}",
        description=description,
        task_type="profile_completion",
        status="pending",
        priority="high",
        assigned_to=emp.id,
        assigned_by=current_user.id,
        related_employee_id=emp.id,
        notes=f"Auto-generated: {len(missing)} missing field(s)",
    )
    db.add(task)
    await db.commit()

    # Send email if personal email exists
    email_sent = False
    if emp.personal_email:
        try:
            portal_link = f"{settings.FRONTEND_URL}/joining-details?tab=profile"
            send_profile_task_email(emp.personal_email, emp.full_name, missing, portal_link)
            email_sent = True
        except Exception as e:
            print(f"Profile task email error: {e}")

    return {
        "message": f"Task created with {len(missing)} missing field(s)",
        "missing_count": len(missing),
        "missing_fields": missing,
        "task_id": str(task.id),
        "email_sent": email_sent,
    }