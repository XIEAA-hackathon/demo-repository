from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.models.models import User
from app.services.participant_session import clear_user_session


def provision_lab_admin_account(db: Session) -> User | None:
    """Create or repair the single environment-configured Lab Admin account."""
    email = settings.LAB_ADMIN_EMAIL.strip().lower()
    password = settings.LAB_ADMIN_PASSWORD
    if not email or not password:
        return None

    duplicates = db.query(User).filter(User.role == "lab_admin", func.lower(User.email) != email).all()
    if duplicates:
        raise RuntimeError("Only one Lab Admin account is supported. Remove the duplicate account before startup.")

    user = db.query(User).filter(func.lower(User.email) == email).one_or_none()
    if user is not None and user.role != "lab_admin":
        raise RuntimeError("LAB_ADMIN_EMAIL belongs to a non-Lab-Admin account. Configure a distinct email.")
    if user is None:
        user = User(name=settings.LAB_ADMIN_NAME.strip() or "Lab Admin", email=email, password_hash="", role="lab_admin")
        db.add(user)

    user.name = settings.LAB_ADMIN_NAME.strip() or "Lab Admin"
    user.email = email
    user.role = "lab_admin"
    user.team_id = None
    user.is_system_account = True
    user.account_source = "MANUAL"
    user.credentials_active = True
    if not user.password_hash or not verify_password(password, user.password_hash):
        user.password_hash = get_password_hash(password)
        clear_user_session(user)
    return user
