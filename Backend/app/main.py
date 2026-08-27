import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.api import auth, team, problem_statements, auction, wildcard, websockets, admin, participant, rounds, operations, judging, management
from app.core.database import initialize_database, SessionLocal
from app.models import models
from app.core.config import settings
from app.core.security import get_password_hash
from app.services.demo_seed import provision_demo_accounts
from app.services.event_service import get_or_create_event_config, get_or_create_game_config, upgrade_legacy_starting_coins
from app.services.event_service import sync_expired_event_state
from app.services.wildcard_service import reconcile_wildcard_selection
from app.api.websockets import manager

logger = logging.getLogger("uvicorn.error")


def validate_startup_configuration() -> None:
    if not settings.DATABASE_URL.strip():
        raise RuntimeError("DATABASE_URL is required.")
    if settings.is_production:
        if settings.SECRET_KEY == "supersecretkey_please_change_in_production" or len(settings.SECRET_KEY) < 32:
            raise RuntimeError("A unique SECRET_KEY of at least 32 characters is required in production.")
        if settings.ENABLE_EVENT_RESET:
            raise RuntimeError("ENABLE_EVENT_RESET must be false in production.")


async def expiry_worker() -> None:
    while True:
        await asyncio.sleep(1)
        db = SessionLocal()
        try:
            actions = sync_expired_event_state(db)
            wildcard_assignment = reconcile_wildcard_selection(db)
            if wildcard_assignment:
                actions.append("wildcard_selection_timeout")
                await manager.broadcast_event("wildcard_updated", {
                    "action": "selection_timeout",
                    "team_name": wildcard_assignment["team_name"],
                    "problem_id": wildcard_assignment["problem"]["id"],
                })
            if actions:
                await manager.broadcast_event("event_state_changed", {"expiry_actions": actions})
        except Exception:
            db.rollback()
            logger.exception("Timer expiry worker failed; it will retry.")
        finally:
            db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_startup_configuration()
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
                is_system_account=True,
            )
            db.add(admin_user)
        if admin_user:
            admin_user.is_system_account = True
        provision_demo_accounts(db)
        db.commit()

        # Ensure singleton EventConfig + GameConfig rows exist
        get_or_create_event_config(db)
        get_or_create_game_config(db)
        upgraded_teams = upgrade_legacy_starting_coins(db)
        if upgraded_teams:
            logger.info("Upgraded %s legacy team wallets to 5,000 starting coins.", upgraded_teams)
    finally:
        db.close()

    worker = asyncio.create_task(expiry_worker(), name="event-timer-expiry")
    try:
        yield
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker

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
app.include_router(rounds.router, tags=["Round Operations"])
app.include_router(websockets.router, tags=["WebSockets"])
app.include_router(operations.router, tags=["Event Operations"])
app.include_router(judging.router, tags=["Judging and Public Results"])
app.include_router(management.router, tags=["Managed Users"])


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_request: Request, exc: SQLAlchemyError):
    logger.error("Database operation failed: %s", exc.__class__.__name__)
    return JSONResponse(status_code=503, content={"detail": "Event service temporarily unavailable. Please retry."})

@app.get("/")
def read_root():
    return {"message": "Welcome to Hackathon Auction Platform API"}


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}


@app.get("/health/ready", tags=["Health"])
def readiness_check():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "healthy"}
    finally:
        db.close()


@app.get("/version", tags=["Health"])
def version_check():
    return {"commit": settings.DEPLOYED_COMMIT}
