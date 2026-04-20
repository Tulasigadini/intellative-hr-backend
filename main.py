from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from app.db.database import create_tables
from app.api.routes.auth import router as auth_router
from app.api.routes.departments import dept_router, role_router
from app.api.routes.employees import router as emp_router
from app.api.routes.iam import router as iam_router
from app.api.routes.onboarding import router as onboarding_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.bank_details import router as bank_router
from app.api.routes.resume_parse import router as resume_router
from app.api.routes.password_reset import router as pwd_reset_router
from app.api.routes.password_reset import tasks_router as profile_task_router
from app.api.routes.salary_details import router as salary_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    yield


app = FastAPI(
    title="Intellativ HR & IAM API",
    version="1.0.0",
    description="HR Onboarding & Identity Access Management System",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(dept_router, prefix="/api/v1")
app.include_router(role_router, prefix="/api/v1")
app.include_router(emp_router, prefix="/api/v1")
app.include_router(iam_router, prefix="/api/v1")
app.include_router(onboarding_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(bank_router, prefix="/api/v1")
app.include_router(resume_router, prefix="/api/v1")
app.include_router(pwd_reset_router, prefix="/api/v1")
app.include_router(profile_task_router, prefix="/api/v1")
app.include_router(salary_router, prefix="/api/v1")

if os.path.exists(settings.UPLOAD_DIR):
    app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


@app.get("/")
async def root():
    return {"status": "Intellativ HR API running", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}