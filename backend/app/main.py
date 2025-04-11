 # app/main.py
from fastapi import FastAPI
# We'll import config later if needed here, for now just title
# from app.core.config import PROJECT_NAME 

# Create FastAPI app instance
app = FastAPI(title="SmartEducator AI Detector API", version="0.1.0")

@app.get("/")
async def read_root():
    """Root endpoint welcome message."""
    return {"message": f"Welcome to SmartEducator AI Detector API"}

@app.get("/health", status_code=200, tags=["Health Check"])
async def health_check():
    """Simple health check."""
    return {"status": "OK"}

# API Routers will be included here later
