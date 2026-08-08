from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, team, problem_statements, auction, wildcard, websockets
from app.core.database import engine, Base
from app.models import models

# Create database tables automatically if they don't exist
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Hackathon Auction Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, tags=["Authentication"])
app.include_router(team.router, tags=["Team Management"])
app.include_router(problem_statements.router, tags=["Problem Statements"])
app.include_router(auction.router, tags=["Auction"])
app.include_router(wildcard.router, tags=["Wildcard"])
app.include_router(websockets.router, tags=["WebSockets"])

@app.get("/")
def read_root():
    return {"message": "Welcome to Hackathon Auction Platform API"}
