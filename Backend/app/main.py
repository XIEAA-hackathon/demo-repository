from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, team, problem_statements, auction, wildcard, websockets, admin, participant
from app.core.database import initialize_database, SessionLocal
from app.models import models
from app.core.config import settings
from app.core.security import get_password_hash
from app.services.event_service import get_or_create_event_config, get_or_create_game_config

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create database tables automatically if they don't exist
    initialize_database()

    db = SessionLocal()
    try:
        # Seed default admin account from settings
        admin_user = db.query(models.User).filter(models.User.email == settings.ADMIN_EMAIL).first()
        if settings.ADMIN_PASSWORD and not admin_user:
            admin_user = models.User(
                name=settings.ADMIN_NAME,
                email=settings.ADMIN_EMAIL,
                password_hash=get_password_hash(settings.ADMIN_PASSWORD),
                role="admin",
            )
            db.add(admin_user)
            db.commit()

        # Ensure singleton EventConfig + GameConfig rows exist
        get_or_create_event_config(db)
        get_or_create_game_config(db)
    finally:
        db.close()

    yield

app = FastAPI(title="Hackathon Auction Platform API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, tags=["Authentication"])
app.include_router(team.router, tags=["Team Management"])
app.include_router(problem_statements.router, tags=["Problem Statements"])
app.include_router(auction.router, tags=["Auction"])
app.include_router(wildcard.router, tags=["Wildcard"])
app.include_router(participant.router, tags=["Participant"])
app.include_router(admin.router, tags=["Admin"])
app.include_router(websockets.router, tags=["WebSockets"])

@app.get("/")
def read_root():
    return {"message": "Welcome to Hackathon Auction Platform API"}


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}


@app.get("/version", tags=["Health"])
def version_check():
    return {"commit": settings.DEPLOYED_COMMIT}
