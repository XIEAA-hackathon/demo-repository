from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Hackathon Auction Platform"
    SECRET_KEY: str = "supersecretkey_please_change_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440 # 24 hours
    DEPLOYED_COMMIT: str = "development"
    APP_ENV: str = "development"
    ENABLE_EVENT_RESET: bool = False

    # SQLite is the zero-configuration local default. The EC2 deployment sets
    # an absolute path on its persistent application volume.
    DATABASE_URL: str = "sqlite:///./casino_hackathon.db"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:5175,http://127.0.0.1:5175"

    # Default admin account created at startup (for admin provisioning)
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = ""
    ADMIN_NAME: str = "Event Admin"
    SYSTEM_ACCOUNT_EMAILS: str = "admin.demo@bidtobuild.example.com,leader@demo.example.com"
    SYSTEM_TEAM_NAMES: str = "Demo Team"

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

    @property
    def system_account_emails(self) -> list[str]:
        return [value.strip().lower() for value in self.SYSTEM_ACCOUNT_EMAILS.split(",") if value.strip()]

    @property
    def system_team_names(self) -> list[str]:
        return [value.strip() for value in self.SYSTEM_TEAM_NAMES.split(",") if value.strip()]

settings = Settings()
