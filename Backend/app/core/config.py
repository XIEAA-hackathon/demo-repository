from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Hackathon Auction Platform"
    SECRET_KEY: str = "supersecretkey_please_change_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440 # 24 hours
    SESSION_HEARTBEAT_SECONDS: int = 20
    SESSION_STALE_SECONDS: int = 90
    SESSION_TOUCH_INTERVAL_SECONDS: int = 15
    DEPLOYED_COMMIT: str = "development"
    APP_ENV: str = "development"
    ENABLE_EVENT_RESET: bool = False

    # Required in every environment. Credentials belong in the process/service
    # environment and are never committed to source control.
    DATABASE_URL: str
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT_SECONDS: int = 10
    DB_POOL_RECYCLE_SECONDS: int = 1800
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:5175,http://127.0.0.1:5175"

    # Default admin account created at startup (for admin provisioning)
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = ""
    ADMIN_NAME: str = "Event Admin"
    DEMO_ADMIN_EMAIL: str = "admin.demo@bidtobuild.example.com"
    DEMO_ADMIN_PASSWORD: str = "DemoAdmin@123"
    DEMO_LEADER_EMAIL: str = "leader@demo.example.com"
    DEMO_LEADER_PASSWORD: str = "DemoLeader@123"
    DEMO_TEAM_NAME: str = "Demo Team"
    LEADERBOARD_DISPLAY_EMAIL: str = "leaderboard@bidtobuild.example.com"
    LEADERBOARD_DISPLAY_PASSWORD: str = "Leaderboard@123"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_postgresql_driver(cls, value):
        """Route common PostgreSQL URL schemes through the installed psycopg 3 driver."""
        if not isinstance(value, str):
            return value
        database_url = value.strip()
        lowered = database_url.lower()
        if lowered.startswith("postgres://"):
            return "postgresql+psycopg://" + database_url[len("postgres://"):]
        if lowered.startswith("postgresql://"):
            return "postgresql+psycopg://" + database_url[len("postgresql://"):]
        return database_url

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.strip().lower() in {"production", "prod", "live"}


settings = Settings()
