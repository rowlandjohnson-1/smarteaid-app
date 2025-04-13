# app/main.py
from fastapi import FastAPI
from app.core.config import PROJECT_NAME
from app.db.database import connect_to_mongo, close_mongo_connection

# Create FastAPI app instance
app = FastAPI(
    title=PROJECT_NAME,
    version="0.1.0"
    # Add lifespan context manager later for more robust startup/shutdown
)

# --- Event Handlers for DB Connection ---
@app.on_event("startup")
async def startup_db_client():
    """Connect to MongoDB on application startup."""
    await connect_to_mongo()

@app.on_event("shutdown")
async def shutdown_db_client():
    """Disconnect from MongoDB on application shutdown."""
    await close_mongo_connection()

# --- API Endpoints ---
@app.get("/")
async def read_root():
    """Root endpoint welcome message."""
    return {"message": f"Welcome to {PROJECT_NAME}"}

@app.get("/health", status_code=200, tags=["Health Check"])
async def health_check():
    """Simple health check."""
    # Could add DB connection check here later
    return {"status": "OK"}

# API Routers will be included here later