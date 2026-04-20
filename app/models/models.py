import uuid
from datetime import datetime, date, timezone
from typing import Optional, List
from sqlalchemy import (
    String, Boolean, DateTime, Date, ForeignKey, Text,
    Enum as SAEnum, Integer, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.database import Base
import enum


def aware_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EmployeeType(str, enum.Enum):
    NEW = "new"
    REJOINING = "rejoining"


class EmployeeStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
    RELIEVED = "relieved"
    SUSPENDED = "suspended"


class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class DocumentType(str, enum.Enum):
    AADHAR = "aadhar"
    PAN = "pan"
    VOTER_ID = "voter_id"
    DRIVING_LICENSE = "driving_license"
    PASSPORT_PHOTO = "passport_photo"
    UTILITY_BILL = "utility_bill"
    RENTAL_AGREEMENT = "rental_agreement"
    BANK_STATEMENT_ADDRESS = "bank_statement_address"
    MARKS_10TH = "marks_10th"
    MARKS_12TH = "marks_12th"
    GRADUATION_CERTIFICATE = "graduation_certificate"
    POSTGRADUATION_CERTIFICATE = "postgraduation_certificate"
    CONSOLIDATED_MARKS = "consolidated_marks"
    RELIEVING_LETTER = "relieving_letter"
    EXPERIENCE_CERTIFICATE = "experience_certificate"
    PAYSLIPS = "payslips"
    FORM_16 = "form_16"
    PF_SERVICE_HISTORY = "pf_service_history"
    BANK_STATEMENT_SALARY = "bank_statement_salary"
    PASSPORT = "passport"
    DEGREE = "degree"
    EXPERIENCE_LETTER = "experience_letter"
    OFFER_LETTER = "offer_letter"
    JOINING_LETTER = "joining_letter"
    OTHER = "other"


class AssetAction(str, enum.Enum):
    ALLOCATE = "allocate"
    COLLECT = "collect"


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=aware_utc_now)

    roles: Mapped[List["Role"]] = relationship("Role", back_populates="department")
    employees: Mapped[List["Employee"]] = relationship("Employee", back_populates="department")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    department_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"))
    parent_role_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    level: Mapped[int] = mapped_column(Integer, default=1)
    permissions: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=aware_utc_now)

    department: Mapped["Department"] = relationship("Department", back_populates="roles")
    parent_role: Mapped[Optional["Role"]] = relationship("Role", remote_side="Role.id", back_populates="sub_roles")
    sub_roles: Mapped[List["Role"]] = relationship("Role", back_populates="parent_role")
    employees: Mapped[List["Employee"]] = relationship("Employee", back_populates="role")
    system_accesses: Mapped[List["SystemAccess"]] = relationship("SystemAccess", back_populates="role")


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    personal_email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    alternate_phone: Mapped[Optional[str]] = mapped_column(String(20))
    gender: Mapped[Optional[Gender]] = mapped_column(SAEnum(Gender))
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date)
    address: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(String(100))
    pincode: Mapped[Optional[str]] = mapped_column(String(10))
    emergency_contact_name: Mapped[Optional[str]] = mapped_column(String(200))
    emergency_contact_phone: Mapped[Optional[str]] = mapped_column(String(20))
    pan_number: Mapped[Optional[str]] = mapped_column(String(20))
    uan_number: Mapped[Optional[str]] = mapped_column(String(30))
    pf_number: Mapped[Optional[str]] = mapped_column(String(30))

    department_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"))
    role_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"))
    reporting_manager_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))

    employee_type: Mapped[EmployeeType] = mapped_column(SAEnum(EmployeeType), default=EmployeeType.NEW)
    status: Mapped[EmployeeStatus] = mapped_column(SAEnum(EmployeeStatus), default=EmployeeStatus.PENDING)
    joining_date: Mapped[Optional[date]] = mapped_column(Date)
    relieving_date: Mapped[Optional[date]] = mapped_column(Date)
    probation_end_date: Mapped[Optional[date]] = mapped_column(Date)

    profile_picture: Mapped[Optional[str]] = mapped_column(String(500))
    is_profile_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    is_email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    onboarded_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    onboarded_by_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    previous_employee_id: Mapped[Optional[str]] = mapped_column(String(20))
    previous_joining_date: Mapped[Optional[date]] = mapped_column(Date)
    previous_relieving_date: Mapped[Optional[date]] = mapped_column(Date)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=aware_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=aware_utc_now, onupdate=aware_utc_now
    )

    department: Mapped[Optional["Department"]] = relationship("Department", back_populates="employees")
    role: Mapped[Optional["Role"]] = relationship("Role", back_populates="employees")
    reporting_manager: Mapped[Optional["Employee"]] = relationship(
        "Employee", foreign_keys="[Employee.reporting_manager_id]", remote_side="Employee.id"
    )

    # FIXED: Explicitly specify foreign_keys to avoid ambiguity
    documents: Mapped[List["EmployeeDocument"]] = relationship(
        "EmployeeDocument",
        back_populates="employee",
        foreign_keys="[EmployeeDocument.employee_id]"   # ← This fixes the error
    )

    user_account: Mapped[Optional["UserAccount"]] = relationship("UserAccount", back_populates="employee", uselist=False)
    asset_requests: Mapped[List["AssetRequest"]] = relationship("AssetRequest", back_populates="employee")

    salary: Mapped[Optional["EmployeeSalary"]] = relationship("EmployeeSalary", back_populates="employee", uselist=False)
    bank_details: Mapped[Optional["EmployeeBankDetails"]] = relationship("EmployeeBankDetails", primaryjoin="Employee.id == EmployeeBankDetails.employee_id", uselist=False)

    __table_args__ = (
        Index("idx_employee_status", "status"),
        Index("idx_employee_dept", "department_id"),
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class EmployeeDocument(Base):
    __tablename__ = "employee_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    document_type: Mapped[DocumentType] = mapped_column(SAEnum(DocumentType, values_callable=lambda x: [e.value for e in x]))
    document_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=aware_utc_now)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))

    # Back reference - use the same explicit foreign key
    employee: Mapped["Employee"] = relationship(
        "Employee", 
        back_populates="documents",
        foreign_keys="[EmployeeDocument.employee_id]"
    )


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), unique=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    password_reset_token: Mapped[Optional[str]] = mapped_column(String(255))
    password_reset_expires: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=aware_utc_now)

    employee: Mapped["Employee"] = relationship("Employee", back_populates="user_account")


class SystemAccess(Base):
    __tablename__ = "system_accesses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"))
    system_name: Mapped[str] = mapped_column(String(100))
    access_level: Mapped[str] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    role: Mapped["Role"] = relationship("Role", back_populates="system_accesses")


class AssetRequest(Base):
    __tablename__ = "asset_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))
    action: Mapped[AssetAction] = mapped_column(SAEnum(AssetAction))
    asset_type: Mapped[str] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    email_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=aware_utc_now)

    employee: Mapped["Employee"] = relationship("Employee", back_populates="asset_requests")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    performed_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[Optional[str]] = mapped_column(String(100))
    details: Mapped[Optional[dict]] = mapped_column(JSONB)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=aware_utc_now)


class WorkHistory(Base):
    __tablename__ = "work_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    company_name: Mapped[str] = mapped_column(String(200))
    designation: Mapped[Optional[str]] = mapped_column(String(200))
    department: Mapped[Optional[str]] = mapped_column(String(200))
    from_date: Mapped[Optional[date]] = mapped_column(Date)
    to_date: Mapped[Optional[date]] = mapped_column(Date)
    reason_for_leaving: Mapped[Optional[str]] = mapped_column(String(500))
    last_ctc: Mapped[Optional[str]] = mapped_column(String(50))
    is_intellativ: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=aware_utc_now)

    @property
    def is_current(self) -> bool:
        return self.to_date is None


class InsuranceInfo(Base):
    __tablename__ = "insurance_info"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), unique=True)

    smoking_status: Mapped[Optional[str]] = mapped_column(String(20))
    nominee_name: Mapped[Optional[str]] = mapped_column(String(200))
    nominee_relation: Mapped[Optional[str]] = mapped_column(String(100))
    nominee_dob: Mapped[Optional[date]] = mapped_column(Date)
    nominee_phone: Mapped[Optional[str]] = mapped_column(String(20))
    blood_group: Mapped[Optional[str]] = mapped_column(String(10))
    pre_existing_conditions: Mapped[Optional[str]] = mapped_column(Text)

    spouse_name: Mapped[Optional[str]] = mapped_column(String(200))
    spouse_dob: Mapped[Optional[date]] = mapped_column(Date)
    spouse_gender: Mapped[Optional[str]] = mapped_column(String(20))
    children: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)

    insurance_email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    insurance_email_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    submitted: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=aware_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=aware_utc_now, onupdate=aware_utc_now
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    notification_type: Mapped[str] = mapped_column(String(50))
    related_employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    action_url: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=aware_utc_now)


class OnboardingStep(Base):
    __tablename__ = "onboarding_steps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    step_name: Mapped[str] = mapped_column(String(100))
    step_code: Mapped[str] = mapped_column(String(50))
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=aware_utc_now)


class EmployeeBankDetails(Base):
    __tablename__ = "employee_bank_details"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), unique=True)
    bank_name: Mapped[Optional[str]] = mapped_column(String(100))
    account_holder_name: Mapped[Optional[str]] = mapped_column(String(200))
    account_number: Mapped[Optional[str]] = mapped_column(String(50))
    ifsc_code: Mapped[Optional[str]] = mapped_column(String(20))
    branch_name: Mapped[Optional[str]] = mapped_column(String(200))
    account_type: Mapped[Optional[str]] = mapped_column(String(30))
    # HDFC-specific optional fields
    hdfc_customer_id: Mapped[Optional[str]] = mapped_column(String(50))
    hdfc_netbanking_id: Mapped[Optional[str]] = mapped_column(String(50))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=aware_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=aware_utc_now, onupdate=aware_utc_now)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    task_type: Mapped[str] = mapped_column(String(50), default="general")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))
    assigned_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))
    related_employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=aware_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=aware_utc_now, onupdate=aware_utc_now
    )


class EmployeeSalary(Base):
    __tablename__ = "employee_salary"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), unique=True)
    
    ctc: Mapped[Optional[str]] = mapped_column(String(50))
    basic: Mapped[Optional[str]] = mapped_column(String(50))
    hra: Mapped[Optional[str]] = mapped_column(String(50))
    special_allowance: Mapped[Optional[str]] = mapped_column(String(50))
    pf_contribution: Mapped[Optional[str]] = mapped_column(String(50))
    bonus: Mapped[Optional[str]] = mapped_column(String(50))
    in_hand_salary: Mapped[Optional[str]] = mapped_column(String(50))
    
    effective_date: Mapped[Optional[date]] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=aware_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=aware_utc_now, onupdate=aware_utc_now
    )

    employee: Mapped["Employee"] = relationship("Employee")