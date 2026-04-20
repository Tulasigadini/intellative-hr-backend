from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    # Application Settings
    DEBUG: bool = False
    ENVIRONMENT: str = "production"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Security
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database
    DATABASE_URL: str = Field(..., env="DATABASE_URL")

    # SMTP Settings (Move sensitive data to .env)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = Field(..., env="SMTP_USER")
    SMTP_PASSWORD: str = Field(..., env="SMTP_PASSWORD")
    SMTP_FROM: str = Field(..., env="SMTP_FROM")
    SMTP_FROM_NAME: str = "Intellativ HR"

    # Notification Emails
    HR_NOTIFICATION_EMAIL: str = Field(..., env="HR_NOTIFICATION_EMAIL")
    INSURANCE_TEAM_EMAIL: str = Field(..., env="INSURANCE_TEAM_EMAIL")
    IT_TEAM_EMAIL: str = Field(..., env="IT_TEAM_EMAIL")

    # File Uploads
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_EXTENSIONS: list = ["pdf", "jpg", "jpeg", "png", "doc", "docx"]

    # Company & Frontend
    COMPANY_NAME: str = "Intellativ"
    COMPANY_DOMAIN: str = "intellativ.com"
    FRONTEND_URL: str = Field("http://localhost:3000", env="FRONTEND_URL")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Global settings instance
settings = Settings()
