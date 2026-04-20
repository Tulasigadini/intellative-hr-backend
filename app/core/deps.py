from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.db.database import get_db
from app.models.models import UserAccount, Employee, Role
from app.core.security import decode_token

bearer_scheme = HTTPBearer()

# ── Role code sets ─────────────────────────────────────────────────────────────
# Roles that can VIEW all employees (read-only access to employee list)
VIEW_ALL_EMPLOYEES_CODES = {
    "IT-CTO", "IT-VPE", "IT-EM", "IT-TL", "IT-PM", "IT-SM",
    "OPS-MGR", "OPS-DM", "SAL-MGR", "MKT-MGR", "FIN-MGR", "ADM-MGR",
}
VIEW_ALL_PREFIXES = ["HR-", "ADM-"]

# Roles that can ONBOARD / CREATE / ACTIVATE employees
ONBOARD_CODES = {"IT-CTO", "IT-VPE", "IT-EM"}
ONBOARD_PREFIXES = ["HR-", "ADM-"]
ONBOARD_DEPT_NAMES = {"Operations"}   # Operations dept managers can onboard

# Roles that can EDIT employee details — HR & Operations dept + Superadmin only
EDIT_EMPLOYEE_CODES = set()
EDIT_EMPLOYEE_PREFIXES = ["HR-", "ADM-"]
EDIT_EMPLOYEE_DEPT_NAMES = {"Operations"}  # HR & Operations can edit

# Roles that can VIEW any employee detail page (read-only)
VIEW_EMPLOYEE_DETAIL_PREFIXES = ["HR-", "ADM-"]
VIEW_EMPLOYEE_DETAIL_DEPT_NAMES = {"Operations"}

# Roles that have IAM admin access
IAM_ADMIN_PREFIXES = ["HR-"]
IAM_ADMIN_CODES = {"IT-CTO", "IT-VPE", "IT-EM"}


async def get_current_user_account(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> UserAccount:
    token = credentials.credentials
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = payload.get("sub")
    result = await db.execute(select(UserAccount).where(UserAccount.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Employee:
    token = credentials.credentials
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = payload.get("sub")
    result = await db.execute(select(UserAccount).where(UserAccount.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    emp_result = await db.execute(
        select(Employee)
        .options(selectinload(Employee.role), selectinload(Employee.department))
        .where(Employee.id == user.employee_id)
    )
    employee = emp_result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Employee not found")
    employee._user_account = user
    return employee


def is_superadmin(employee: Employee) -> bool:
    return bool(getattr(employee, '_user_account', None) and employee._user_account.is_superadmin)


def _role_code(employee: Employee) -> str:
    return employee.role.code if employee.role else ""


def _dept_name(employee: Employee) -> str:
    return employee.department.name if employee.department else ""


def can_view_all_employees(employee: Employee) -> bool:
    """Can see all employees list (read only)"""
    if is_superadmin(employee):
        return True
    code = _role_code(employee)
    return (
        any(code.startswith(p) for p in VIEW_ALL_PREFIXES)
        or code in VIEW_ALL_EMPLOYEES_CODES
    )


def can_onboard_employees(employee: Employee) -> bool:
    """Can create/onboard new employees"""
    if is_superadmin(employee):
        return True
    code = _role_code(employee)
    dept = _dept_name(employee)
    return (
        any(code.startswith(p) for p in ONBOARD_PREFIXES)
        or code in ONBOARD_CODES
        or dept in ONBOARD_DEPT_NAMES
    )


def can_view_employee_detail(employee: Employee, target_employee_id=None) -> bool:
    """Can view any employee detail page. Always True for self."""
    if is_superadmin(employee):
        return True
    if target_employee_id and str(employee.id) == str(target_employee_id):
        return True
    code = _role_code(employee)
    dept = _dept_name(employee)
    return (
        any(code.startswith(p) for p in VIEW_EMPLOYEE_DETAIL_PREFIXES)
        or dept in VIEW_EMPLOYEE_DETAIL_DEPT_NAMES
    )


def can_edit_employees(employee: Employee) -> bool:
    """Can edit employee details, activate, relieve — HR, Operations dept, Superadmin"""
    if is_superadmin(employee):
        return True
    code = _role_code(employee)
    dept = _dept_name(employee)
    return (
        any(code.startswith(p) for p in EDIT_EMPLOYEE_PREFIXES)
        or code in EDIT_EMPLOYEE_CODES
        or dept in EDIT_EMPLOYEE_DEPT_NAMES
    )


def can_manage_employees(employee: Employee) -> bool:
    """Backward compat — use can_edit_employees"""
    return can_edit_employees(employee)


def is_hr_or_admin(employee: Employee) -> bool:
    """HR dept or IT top management"""
    if is_superadmin(employee):
        return True
    code = _role_code(employee)
    return (
        any(code.startswith(p) for p in ["HR-", "ADM-"])
        or code in {"IT-CTO", "IT-VPE", "IT-EM"}
    )


def can_manage_iam(employee: Employee) -> bool:
    """Full IAM admin"""
    if is_superadmin(employee):
        return True
    code = _role_code(employee)
    return (
        any(code.startswith(p) for p in IAM_ADMIN_PREFIXES)
        or code in IAM_ADMIN_CODES
    )


async def require_hr_or_admin(employee: Employee = Depends(get_current_user)) -> Employee:
    if not is_hr_or_admin(employee):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return employee


async def require_superadmin(employee: Employee = Depends(get_current_user)) -> Employee:
    if not is_superadmin(employee):
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return employee
