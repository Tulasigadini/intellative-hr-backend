"""
Tasks Route — supports individual and team tasks.
Team tasks: visible to all team members, anyone can claim/pick up.
Activity tracking: who did what step.
"""
import uuid
from datetime import datetime, date, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.db.database import get_db
from app.models.models import Task, Employee, EmployeeStatus
from app.core.deps import get_current_user, is_hr_or_admin, can_manage_employees

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    task_type: str = "general"
    priority: str = "medium"
    assigned_to: Optional[uuid.UUID] = None
    related_employee_id: Optional[uuid.UUID] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[uuid.UUID] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None


TEAM_PREFIXES = {
    "hr":        ["HR-"],
    "it":        ["IT-"],
    "insurance": ["INS-", "FIN-"],
    "admin":     ["ADM-"],
    "finance":   ["FIN-"],
}


def get_user_team(employee: Employee) -> Optional[str]:
    if not employee.role:
        return None
    code = employee.role.code
    for team, prefixes in TEAM_PREFIXES.items():
        if any(code.startswith(p) for p in prefixes):
            return team
    return None


def task_to_dict(t: Task, assignee: Employee = None, related: Employee = None, assigner: Employee = None):
    # Extract team tag from notes
    team = None
    if t.notes:
        import re
        m = re.search(r'\[team:(\w+)\]', t.notes)
        if m:
            team = m.group(1)

    return {
        "id": str(t.id),
        "title": t.title,
        "description": t.description,
        "task_type": t.task_type,
        "status": t.status,
        "priority": t.priority,
        "assigned_to": str(t.assigned_to) if t.assigned_to else None,
        "assigned_to_name": f"{assignee.first_name} {assignee.last_name}" if assignee else None,
        "assigned_by": str(t.assigned_by) if t.assigned_by else None,
        "assigned_by_name": f"{assigner.first_name} {assigner.last_name}" if assigner else None,
        "related_employee_id": str(t.related_employee_id) if t.related_employee_id else None,
        "related_employee_name": f"{related.first_name} {related.last_name}" if related else None,
        "due_date": str(t.due_date) if t.due_date else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "notes": t.notes,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "is_team_task": team is not None,
        "team": team,
    }


async def _build_emp_map(db, tasks):
    emp_ids = list(set(filter(None,
        [t.assigned_to for t in tasks] +
        [t.related_employee_id for t in tasks] +
        [t.assigned_by for t in tasks]
    )))
    emp_map = {}
    if emp_ids:
        er = await db.execute(select(Employee).where(Employee.id.in_(emp_ids)))
        for e in er.scalars().all():
            emp_map[e.id] = e
    return emp_map


@router.get("")
async def list_tasks(
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    assigned_to_me: bool = False,
    include_team: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """
    List tasks. For team members, includes team tasks (tagged [team:X]).
    HR/Admin can see all tasks.
    """
    # Get user's team
    user_team = get_user_team(current_user)

    if is_hr_or_admin(current_user) and not assigned_to_me:
        # HR sees everything
        query = select(Task)
        filters = []
        if status:
            filters.append(Task.status == status)
        if task_type:
            filters.append(Task.task_type == task_type)
        if filters:
            query = query.where(and_(*filters))
    elif not assigned_to_me and include_team and user_team:
        # Team tab: show ONLY team-tagged tasks for this user's team
        # (no personal tasks mixed in — keeps count badge consistent)
        query = select(Task).where(Task.notes.contains(f"[team:{user_team}]"))
        if status:
            query = query.where(Task.status == status)
        if task_type:
            query = query.where(Task.task_type == task_type)
    else:
        # My Tasks tab: tasks directly assigned to me (no team tasks)
        conditions = [Task.assigned_to == current_user.id]
        query = select(Task).where(or_(*conditions))
        if status:
            query = query.where(Task.status == status)
        if task_type:
            query = query.where(Task.task_type == task_type)

    query = query.order_by(Task.created_at.desc())
    result = await db.execute(query)
    tasks = result.scalars().all()

    emp_map = await _build_emp_map(db, tasks)
    return [task_to_dict(t, emp_map.get(t.assigned_to), emp_map.get(t.related_employee_id), emp_map.get(t.assigned_by)) for t in tasks]


@router.get("/stats")
async def task_stats(db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    user_team = get_user_team(current_user)

    def base_query():
        if is_hr_or_admin(current_user):
            return select(Task)
        conds = [Task.assigned_to == current_user.id]
        if user_team:
            conds.append(Task.notes.contains(f"[team:{user_team}]"))
        return select(Task).where(or_(*conds))

    b = base_query()
    total    = (await db.execute(select(func.count()).select_from(b.subquery()))).scalar()
    pending  = (await db.execute(select(func.count()).select_from(base_query().where(Task.status=="pending").subquery()))).scalar()
    progress = (await db.execute(select(func.count()).select_from(base_query().where(Task.status=="in_progress").subquery()))).scalar()
    done     = (await db.execute(select(func.count()).select_from(base_query().where(Task.status=="completed").subquery()))).scalar()
    urgent   = (await db.execute(select(func.count()).select_from(base_query().where(and_(Task.priority=="urgent", Task.status!="completed")).subquery()))).scalar()
    team_unassigned = 0
    if user_team:
        team_unassigned = (await db.execute(select(func.count()).select_from(
            select(Task).where(and_(Task.notes.contains(f"[team:{user_team}]"), Task.assigned_to == None)).subquery()
        ))).scalar()

    # my_tasks: tasks directly assigned to current user, active only
    my_tasks_q = select(Task).where(and_(
        Task.assigned_to == current_user.id,
        Task.status.in_(["pending", "in_progress"])
    ))
    my_tasks = (await db.execute(select(func.count()).select_from(my_tasks_q.subquery()))).scalar()

    # team_total: all non-cancelled team tasks for this user's team (matches unfiltered team tab)
    team_total = 0
    if user_team:
        team_total = (await db.execute(select(func.count()).select_from(
            select(Task).where(and_(
                Task.notes.contains(f"[team:{user_team}]"),
                Task.status != "cancelled"
            )).subquery()
        ))).scalar()

    return {"total": total, "pending": pending, "in_progress": progress, "completed": done,
            "urgent": urgent, "team_unassigned": team_unassigned,
            "my_tasks": my_tasks, "team_total": team_total}


@router.post("", status_code=201)
async def create_task(data: TaskCreate, db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    if not can_manage_employees(current_user) and not is_hr_or_admin(current_user):
        raise HTTPException(403, "Insufficient permissions")
    task = Task(**data.model_dump(exclude_none=True), assigned_by=current_user.id)
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task_to_dict(task)


@router.put("/{task_id}/claim")
async def claim_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    """
    Claim a team task — assigns it to the current user.
    Any team member can claim an unassigned team task.
    """
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")

    # Check it's a team task for the user's team
    user_team = get_user_team(current_user)
    if not task.notes or (user_team and f"[team:{user_team}]" not in task.notes):
        if not is_hr_or_admin(current_user):
            raise HTTPException(403, "Not your team's task")

    if task.assigned_to and str(task.assigned_to) != str(current_user.id):
        assignee_res = await db.execute(select(Employee).where(Employee.id == task.assigned_to))
        assignee = assignee_res.scalar_one_or_none()
        name = f"{assignee.first_name} {assignee.last_name}" if assignee else "someone"
        raise HTTPException(400, f"Task already claimed by {name}")

    task.assigned_to = current_user.id
    if task.status == "pending":
        task.status = "in_progress"
    task.updated_at = datetime.now(timezone.utc)
    await db.flush()

    emp_map = await _build_emp_map(db, [task])
    return task_to_dict(task, emp_map.get(task.assigned_to), emp_map.get(task.related_employee_id), emp_map.get(task.assigned_by))


@router.put("/{task_id}/unclaim")
async def unclaim_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    """Release a claimed task back to the team pool."""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    if str(task.assigned_to) != str(current_user.id) and not is_hr_or_admin(current_user):
        raise HTTPException(403, "You cannot unclaim this task")

    task.assigned_to = None
    task.status = "pending"
    task.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return task_to_dict(task)


@router.put("/{task_id}")
async def update_task(task_id: uuid.UUID, data: TaskUpdate, db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")

    # Allow if: assigned to me, or my team task, or HR/admin
    user_team = get_user_team(current_user)
    is_my_task = task.assigned_to and str(task.assigned_to) == str(current_user.id)
    is_team_task = user_team and task.notes and f"[team:{user_team}]" in task.notes

    if not is_my_task and not is_team_task and not is_hr_or_admin(current_user):
        raise HTTPException(403, "Access denied")

    for k, v in data.model_dump(exclude_none=True).items():
        setattr(task, k, v)

    if data.status == "completed" and not task.completed_at:
        task.completed_at = datetime.now(timezone.utc)
    elif data.status and data.status != "completed":
        task.completed_at = None

    task.updated_at = datetime.now(timezone.utc)
    await db.flush()

    emp_map = await _build_emp_map(db, [task])
    return task_to_dict(task, emp_map.get(task.assigned_to), emp_map.get(task.related_employee_id), emp_map.get(task.assigned_by))


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: Employee = Depends(get_current_user)):
    if not is_hr_or_admin(current_user):
        raise HTTPException(403, "Insufficient permissions")
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    await db.delete(task)