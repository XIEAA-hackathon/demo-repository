from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Hackathon Auction Platform"
    SECRET_KEY: str = "supersecretkey_please_change_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440 # 24 hours
    
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/hackathon_db"

    class Config:
        env_file = ".env"

settings = Settings()
