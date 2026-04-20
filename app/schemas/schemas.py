from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from uuid import UUID
from app.models.models import EmployeeType, EmployeeStatus, Gender, DocumentType, AssetAction


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Department ────────────────────────────────────────────────────────────────

class DepartmentCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class DepartmentOut(BaseModel):
    id: UUID
    name: str
    code: str
    description: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Role ──────────────────────────────────────────────────────────────────────

class RoleCreate(BaseModel):
    name: str
    code: str
    department_id: UUID
    parent_role_id: Optional[UUID] = None
    description: Optional[str] = None
    level: int = 1
    permissions: Optional[Dict[str, Any]] = None


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_role_id: Optional[UUID] = None
    level: Optional[int] = None
    permissions: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class RoleOut(BaseModel):
    id: UUID
    name: str
    code: str
    department_id: UUID
    parent_role_id: Optional[UUID]
    description: Optional[str]
    level: int
    permissions: Optional[Dict[str, Any]]
    is_active: bool
    created_at: datetime
    department: Optional[DepartmentOut] = None

    model_config = {"from_attributes": True}


class RoleTree(BaseModel):
    id: UUID
    name: str
    code: str
    level: int
    sub_roles: List["RoleTree"] = []

    model_config = {"from_attributes": True}


RoleTree.model_rebuild()


# ── Employee ──────────────────────────────────────────────────────────────────

class EmployeeCreate(BaseModel):
    first_name: str
    last_name: str
    personal_email: EmailStr
    phone: str
    gender: Optional[Gender] = None
    date_of_birth: Optional[date] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    department_id: Optional[UUID] = None
    role_id: Optional[UUID] = None
    reporting_manager_id: Optional[UUID] = None
    employee_type: EmployeeType = EmployeeType.NEW
    joining_date: Optional[date] = None
    previous_employee_id: Optional[str] = None
    previous_joining_date: Optional[date] = None
    previous_relieving_date: Optional[date] = None
    pan_number: Optional[str] = None
    uan_number: Optional[str] = None
    pf_number: Optional[str] = None


class EmployeeUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[Gender] = None
    date_of_birth: Optional[date] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    department_id: Optional[UUID] = None
    role_id: Optional[UUID] = None
    reporting_manager_id: Optional[UUID] = None
    joining_date: Optional[date] = None
    relieving_date: Optional[date] = None
    status: Optional[EmployeeStatus] = None
    pan_number: Optional[str] = None
    uan_number: Optional[str] = None
    pf_number: Optional[str] = None


class EmployeeOut(BaseModel):
    id: UUID
    employee_id: str
    first_name: str
    last_name: str
    email: str
    personal_email: Optional[str]
    phone: Optional[str]
    gender: Optional[Gender]
    date_of_birth: Optional[date]
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    pincode: Optional[str]
    emergency_contact_name: Optional[str]
    emergency_contact_phone: Optional[str]
    department_id: Optional[UUID]
    role_id: Optional[UUID]
    reporting_manager_id: Optional[UUID]
    employee_type: EmployeeType
    status: EmployeeStatus
    joining_date: Optional[date]
    relieving_date: Optional[date]
    previous_employee_id: Optional[str]
    previous_joining_date: Optional[date]
    previous_relieving_date: Optional[date]
    profile_picture: Optional[str]
    is_profile_complete: bool
    created_at: datetime
    updated_at: datetime
    department: Optional[DepartmentOut] = None
    role: Optional[RoleOut] = None
    pan_number: Optional[str] = None
    uan_number: Optional[str] = None
    pf_number: Optional[str] = None
    salary: Optional["EmployeeSalaryOut"] = None
    bank_details: Optional["BankDetailsOut"] = None

    model_config = {"from_attributes": True}


class EmployeeListOut(BaseModel):
    id: UUID
    employee_id: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str]
    status: EmployeeStatus
    employee_type: EmployeeType
    joining_date: Optional[date]
    relieving_date: Optional[date]
    profile_picture: Optional[str]
    department: Optional[DepartmentOut] = None
    role: Optional[RoleOut] = None

    model_config = {"from_attributes": True}


class PaginatedEmployees(BaseModel):
    items: List[EmployeeListOut]
    total: int
    page: int
    size: int
    pages: int


# ── Document ──────────────────────────────────────────────────────────────────

class DocumentOut(BaseModel):
    id: UUID
    employee_id: UUID
    document_type: DocumentType
    document_name: str
    file_path: str
    is_verified: bool
    uploaded_at: datetime

    model_config = {"from_attributes": True}


# ── Asset Request ─────────────────────────────────────────────────────────────

class AssetRequestCreate(BaseModel):
    employee_id: UUID
    action: AssetAction
    asset_type: str
    notes: Optional[str] = None


class AssetRequestOut(BaseModel):
    id: UUID
    employee_id: UUID
    action: AssetAction
    asset_type: str
    notes: Optional[str]
    email_sent: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Dashboard ─────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_employees: int
    active_employees: int
    pending_onboarding: int
    relieved_this_month: int
    new_joinings_this_month: int
    departments_count: int
    roles_count: int


# ── Bank Details ──────────────────────────────────────────────────────────────

class BankDetailsOut(BaseModel):
    id: UUID
    employee_id: UUID
    bank_name: Optional[str]
    account_holder_name: Optional[str]
    account_number: Optional[str]
    ifsc_code: Optional[str]
    branch_name: Optional[str]
    account_type: Optional[str]
    hdfc_customer_id: Optional[str]
    hdfc_netbanking_id: Optional[str]
    is_verified: bool
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ── Employee Salary ───────────────────────────────────────────────────────────

class EmployeeSalaryCreate(BaseModel):
    employee_id: UUID
    ctc: Optional[str] = None
    basic: Optional[str] = None
    hra: Optional[str] = None
    special_allowance: Optional[str] = None
    pf_contribution: Optional[str] = None
    bonus: Optional[str] = None
    in_hand_salary: Optional[str] = None
    effective_date: Optional[date] = None

class EmployeeSalaryUpdate(BaseModel):
    ctc: Optional[str] = None
    basic: Optional[str] = None
    hra: Optional[str] = None
    special_allowance: Optional[str] = None
    pf_contribution: Optional[str] = None
    bonus: Optional[str] = None
    in_hand_salary: Optional[str] = None
    effective_date: Optional[date] = None

class EmployeeSalaryOut(BaseModel):
    id: UUID
    employee_id: UUID
    ctc: Optional[str]
    basic: Optional[str]
    hra: Optional[str]
    special_allowance: Optional[str]
    pf_contribution: Optional[str]
    bonus: Optional[str]
    in_hand_salary: Optional[str]
    effective_date: Optional[date]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

EmployeeOut.model_rebuild()