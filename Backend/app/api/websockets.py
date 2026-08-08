from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Dict

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)
            
    async def broadcast_json(self, data: dict):
        for connection in self.active_connections:
            await connection.send_json(data)

manager = ConnectionManager()

@router.websocket("/ws/auction")
async def websocket_auction(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Client might send their bids through WS, but typically they will use REST API 
            # and the server will broadcast updates over WS.
            data = await websocket.receive_text()
            # Echo for now, or handle specific commands if needed
            # await manager.broadcast(f"Update: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        
# For broadcasting updates from REST routes, you can import `manager` in your `auction.py` 
# and call `await manager.broadcast_json(...)` whenever a bid is placed or round starts/ends.
