from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from uuid import UUID

from app.db.database import get_db
from app.models.models import Department, Role
from app.schemas.schemas import (
    DepartmentCreate, DepartmentUpdate, DepartmentOut,
    RoleCreate, RoleUpdate, RoleOut, RoleTree
)
from app.core.deps import get_current_user

dept_router = APIRouter(prefix="/departments", tags=["departments"])
role_router = APIRouter(prefix="/roles", tags=["roles"])


# ── Departments ───────────────────────────────────────────────────────────────

@dept_router.get("", response_model=List[DepartmentOut])
async def list_departments(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Department).order_by(Department.name))
    return result.scalars().all()


@dept_router.post("", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
async def create_department(data: DepartmentCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    existing = await db.execute(select(Department).where(Department.code == data.code))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Department code already exists")
    dept = Department(**data.model_dump())
    db.add(dept)
    await db.flush()
    await db.refresh(dept)
    return dept


@dept_router.put("/{dept_id}", response_model=DepartmentOut)
async def update_department(dept_id: UUID, data: DepartmentUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Department).where(Department.id == dept_id))
    dept = result.scalar_one_or_none()
    if not dept:
        raise HTTPException(404, "Department not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(dept, k, v)
    await db.flush()
    await db.refresh(dept)
    return dept


@dept_router.delete("/{dept_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_department(dept_id: UUID, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Department).where(Department.id == dept_id))
    dept = result.scalar_one_or_none()
    if not dept:
        raise HTTPException(404, "Department not found")
    await db.delete(dept)


# ── Roles ─────────────────────────────────────────────────────────────────────

@role_router.get("", response_model=List[RoleOut])
async def list_roles(
    department_id: UUID = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user)
):
    query = select(Role).options(selectinload(Role.department))
    if department_id:
        query = query.where(Role.department_id == department_id)
    result = await db.execute(query.order_by(Role.level, Role.name))
    return result.scalars().all()


@role_router.get("/tree")
async def roles_tree(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Return flat list of roles; frontend builds the tree."""
    result = await db.execute(
        select(Role)
        .options(selectinload(Role.department))
        .where(Role.is_active == True)
        .order_by(Role.level, Role.name)
    )
    roles = result.scalars().all()
    # Build tree manually without lazy-loading sub_roles
    role_dicts = []
    for r in roles:
        role_dicts.append({
            "id": str(r.id),
            "name": r.name,
            "code": r.code,
            "level": r.level,
            "department_id": str(r.department_id),
            "department_name": r.department.name if r.department else None,
            "parent_role_id": str(r.parent_role_id) if r.parent_role_id else None,
            "is_active": r.is_active,
            "description": r.description,
        })
    return role_dicts


@role_router.post("", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
async def create_role(data: RoleCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    existing = await db.execute(select(Role).where(Role.code == data.code))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Role code already exists")
    role = Role(**data.model_dump())
    db.add(role)
    await db.flush()
    result = await db.execute(
        select(Role).options(selectinload(Role.department)).where(Role.id == role.id)
    )
    return result.scalar_one()


@role_router.put("/{role_id}", response_model=RoleOut)
async def update_role(role_id: UUID, data: RoleUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Role).options(selectinload(Role.department)).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(404, "Role not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(role, k, v)
    await db.flush()
    await db.refresh(role)
    return role


@role_router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(role_id: UUID, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(404, "Role not found")
    await db.delete(role)
