from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/intellativ_hr"
    # config.py - fix the DATABASE_URL default
    DATABASE_URL: str = "postgresql+asyncpg://intellative_hr_db_user:Vz0ZTIVMO102S5Q2WST0io5kUYjd8Msr@dpg-d7bkvvlm5p6s73evs1a0-a/intellative_hr_db"
    SECRET_KEY: str = "change-this-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "hr@intellativ.com"
    SMTP_FROM_NAME: str = "Intellativ HR"
    HR_NOTIFICATION_EMAIL: str = ""  # HR email to receive notifications
    INSURANCE_TEAM_EMAIL: str = ""   # Insurance team email
    IT_TEAM_EMAIL: str = ""          # IT team email for email setup requests

    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_EXTENSIONS: str = "pdf,jpg,jpeg,png,doc,docx"

    COMPANY_NAME: str = "Intellativ"
    COMPANY_DOMAIN: str = "intellativ.com"
    FRONTEND_URL: str = "http://localhost:3000"

    @property
    def allowed_extensions_list(self) -> List[str]:
        return [ext.strip() for ext in self.ALLOWED_EXTENSIONS.split(",")]

    class Config:
        env_file = ".env"


settings = Settings()
