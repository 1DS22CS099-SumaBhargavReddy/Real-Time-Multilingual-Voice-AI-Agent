import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.database import init_db
from backend.api.routes import router as api_router
from backend.api.websocket import router as ws_router

app = FastAPI(title="2Care Voice AI Agent API", version="1.0.0")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In development, allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup event to initialize sqlite database
@app.on_event("startup")
def startup_event():
    print("[SERVER] Initializing database...")
    init_db()

# Mount routes
app.include_router(api_router, prefix="/api")
app.include_router(ws_router)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "2Care Multilingual Voice AI Agent API",
        "endpoints": {
            "REST": "/api/doctors, /api/appointments, /api/patients/{id}",
            "Websocket": "/ws/voice"
        }
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
