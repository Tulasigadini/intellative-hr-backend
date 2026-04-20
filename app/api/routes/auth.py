from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timezone
from pydantic import BaseModel

from app.db.database import get_db
from app.models.models import UserAccount, Employee, Role
from app.schemas.schemas import LoginRequest, TokenResponse, RefreshRequest
from app.core.security import verify_password, get_password_hash, create_access_token, create_refresh_token, decode_token
from app.core.deps import (
    get_current_user, is_hr_or_admin, is_superadmin,
    can_onboard_employees, can_edit_employees, can_view_all_employees, can_manage_iam,
    can_view_employee_detail
)
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/auth", tags=["auth"])


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class AdminChangePasswordRequest(BaseModel):
    new_password: str


# @router.post("/login", response_model=TokenResponse)
# async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
#     result = await db.execute(select(UserAccount).where(UserAccount.username == data.username))
#     user = result.scalar_one_or_none()
#     if not user or not verify_password(data.password, user.hashed_password):
#         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
#     if not user.is_active:
#         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
#     await db.execute(update(UserAccount).where(UserAccount.id == user.id).values(last_login=datetime.now(timezone.utc)))

#     # Get employee + role info
#     emp_result = await db.execute(
#         select(Employee)
#         .options(selectinload(Employee.role), selectinload(Employee.department))
#         .where(Employee.id == user.employee_id)
#     )
#     emp = emp_result.scalar_one_or_none()

#     token_data = {"sub": str(user.id)}
#     return TokenResponse(
#         access_token=create_access_token(token_data),
#         refresh_token=create_refresh_token(token_data),
#     )

@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    search_username = data.username.strip().lower()
    print(f"DEBUG: Login attempt for username: {search_username}")
    
    result = await db.execute(select(UserAccount).where(UserAccount.username == search_username))
    user = result.scalar_one_or_none()
    
    if not user:
        print(f"DEBUG: Login failed - User not found: {search_username}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    print(f"DEBUG: Login - Found user ID: {user.id}, Username: {user.username}")
    
    if not verify_password(data.password, user.hashed_password):
        print(f"DEBUG: Login failed - Incorrect password for user ID: {user.id}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
    if not user.is_active:
        print(f"DEBUG: Login failed - Account disabled for user ID: {user.id}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    # FIXED: Use naive datetime to match your current column type
    now_naive = datetime.utcnow()

    await db.execute(
        update(UserAccount)
        .where(UserAccount.id == user.id)
        .values(last_login=now_naive)
    )

    # Get employee + role info
    emp_result = await db.execute(
        select(Employee)
        .options(selectinload(Employee.role), selectinload(Employee.department))
        .where(Employee.id == user.employee_id)
    )
    emp = emp_result.scalar_one_or_none()

    token_data = {"sub": str(user.id)}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )

@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user_id = payload.get("sub")
    result = await db.execute(select(UserAccount).where(UserAccount.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    token_data = {"sub": str(user.id)}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@router.get("/me")
async def get_me(db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    """Return current user profile with role and permissions"""
    user_account = current_user._user_account
    permissions = {
        "is_superadmin": is_superadmin(current_user),
        "can_view_all_employees": can_view_all_employees(current_user),
        "can_view_employee_detail": can_view_employee_detail(current_user),
        "can_view_dashboard": is_hr_or_admin(current_user),
        "can_onboard_employees": can_onboard_employees(current_user),
        "can_edit_employees": can_edit_employees(current_user),
        "can_manage_employees": can_edit_employees(current_user),
        "can_manage_roles": is_superadmin(current_user) or (current_user.role and current_user.role.code in {"IT-CTO", "IT-VPE", "HR-MGR"}),
        "can_manage_departments": is_superadmin(current_user) or (current_user.role and current_user.role.code in {"IT-CTO", "HR-MGR"}),
        "can_view_iam": True,
        "can_manage_iam": can_manage_iam(current_user),
    }
    return {
        "id": str(current_user.id),
        "employee_id": current_user.employee_id,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "email": current_user.email,
        "username": user_account.username,
        "is_superadmin": user_account.is_superadmin,
        "department": current_user.department.name if current_user.department else None,
        "role": current_user.role.name if current_user.role else None,
        "role_code": current_user.role.code if current_user.role else None,
        "role_level": current_user.role.level if current_user.role else None,
        "permissions": permissions,
    }


@router.post("/change-password")
async def change_own_password(
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    """Any logged-in user can change their own password"""
    user_account = current_user._user_account
    if not verify_password(data.old_password, user_account.hashed_password):
        raise HTTPException(status_code=400, detail="Old password is incorrect")
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    user_account.hashed_password = get_password_hash(data.new_password)
    await db.flush()
    return {"message": "Password changed successfully"}


@router.post("/admin/change-password/{employee_id}")
async def admin_change_password(
    employee_id: str,
    data: AdminChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    """HR/Admin can change any user's password"""
    if not is_hr_or_admin(current_user):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    result = await db.execute(select(UserAccount).where(UserAccount.employee_id == employee_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="User account not found")
    account.hashed_password = get_password_hash(data.new_password)
    await db.flush()
    return {"message": "Password changed successfully"}


 