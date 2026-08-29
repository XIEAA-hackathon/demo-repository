from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Hackathon Auction Platform"
    SECRET_KEY: str = "supersecretkey_please_change_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440 # 24 hours
    DEPLOYED_COMMIT: str = "development"
    APP_ENV: str = "development"
    ENABLE_EVENT_RESET: bool = False

    # SQLite is the zero-configuration local default. Production uses a
    # postgresql+psycopg URL supplied through the service environment.
    DATABASE_URL: str = "sqlite:///./casino_hackathon.db"
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

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.strip().lower() in {"production", "prod", "live"}


settings = Settings()
