from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.models import User
from app.services.event_service import event_snapshot, get_team_for_user

router = APIRouter()


def make_event(event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    return jsonable_encoder({
        "type": event_type,
        "timestamp": timestamp,
        "server_time": timestamp,
        "payload": payload or {},
    })


class ConnectionManager:
    """In-memory fan-out for the single-instance hackathon deployment."""

    def __init__(self):
        self.active_connections: dict[WebSocket, dict[str, Any]] = {}

    async def connect(self, websocket: WebSocket, identity: dict[str, Any]):
        await websocket.accept()
        self.active_connections[websocket] = identity

    def disconnect(self, websocket: WebSocket):
        self.active_connections.pop(websocket, None)

    async def send_event(self, websocket: WebSocket, event_type: str, payload: dict[str, Any] | None = None):
        await websocket.send_json(make_event(event_type, payload))

    async def broadcast_event(self, event_type: str, payload: dict[str, Any] | None = None):
        message = make_event(event_type, payload)
        dead: list[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.disconnect(connection)

    async def broadcast_json(self, data: dict):
        """Compatibility adapter for existing REST routes while keeping one envelope."""
        event_type = str(data.get("type", "event_updated"))
        payload = {key: value for key, value in data.items() if key != "type"}
        await self.broadcast_event(event_type, payload)


manager = ConnectionManager()


def _authenticate_socket(token: str | None, db: Session) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not token:
        return None, None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email = payload.get("sub")
        session_id = payload.get("session_id")
        user = db.query(User).filter(User.email == email).first()
        if not user or (user.session_id and user.session_id != session_id):
            return None, None
        team = get_team_for_user(db, user) if user.role != "admin" else None
        identity = {
            "user_id": user.id,
            "email": user.email,
            "role": user.role,
            "team_id": team.id if team else None,
        }
        snapshot = event_snapshot(db)
        snapshot["identity"] = {"role": user.role, "team_id": team.id if team else None}
        return identity, snapshot
    except JWTError:
        return None, None


@router.websocket("/ws/auction")
async def websocket_auction(websocket: WebSocket, db: Session = Depends(get_db)):
    identity, snapshot = _authenticate_socket(websocket.query_params.get("token"), db)
    if not identity or not snapshot:
        await websocket.close(code=4401, reason="Valid access token required")
        return

    await manager.connect(websocket, identity)
    await manager.send_event(websocket, "event_snapshot", snapshot)
    try:
        while True:
            # Mutations are deliberately REST-only. Incoming frames are only
            # accepted as keep-alives and never rebroadcast.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
