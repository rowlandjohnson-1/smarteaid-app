# app/main.py
import logging
import psutil # For system metrics in health check
import time   # For uptime calculation
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
from datetime import datetime, timedelta # For uptime calculation

# Import config and database lifecycle functions
# Adjust path '.' based on where main.py is relative to 'core' and 'db'
from app.core.config import PROJECT_NAME, API_V1_PREFIX, VERSION
from app.db.database import connect_to_mongo, close_mongo_connection, check_database_health

# Import all endpoint routers
# Adjust path '.' based on where main.py is relative to 'api'
# Includes routers for all entities: schools, teachers, class_groups, students, assignments, documents, results
from app.api.v1.endpoints import (
    schools,
    teachers,
    class_groups,
    students,
    assignments,
    documents,  # Includes documents router import
    results,    # Includes results router import
    dashboard   # NEW: Import dashboard router
)

# Setup logging
logger = logging.getLogger(__name__) # Use main module logger or project-specific
# Ensure logging is configured appropriately elsewhere if not using basicConfig
# logging.basicConfig(level=logging.INFO)

# Track application start time for uptime calculation
APP_START_TIME = time.time()

# Define allowed origins
origins = [
    "http://localhost:5173",  # Vite frontend
    "http://localhost:3000",  # Alternative frontend port
    "http://127.0.0.1:5173",  # Alternative localhost
    "http://127.0.0.1:3000",  # Alternative localhost
]

# Create FastAPI app instance with detailed configuration
app = FastAPI(
    title=f"{PROJECT_NAME} - Sentient AI Detector App",
    version=VERSION, # Use version from config
    description="API for detecting AI-generated content in educational settings",
    # Customize API docs/schema URLs
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
    # Using on_event decorators below for DB lifecycle
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Event Handlers for DB Connection ---
@app.on_event("startup")
async def startup_db_client():
    """Connect to MongoDB on application startup."""
    logger.info("Executing startup event: Connecting to database...")
    connected = await connect_to_mongo()
    if not connected:
        logger.critical("FATAL: Database connection failed on startup. Application might not function correctly.")
    else:
        logger.info("Startup event: Database connection successful.")

@app.on_event("shutdown")
async def shutdown_db_client():
    """Disconnect from MongoDB on application shutdown."""
    logger.info("Executing shutdown event: Disconnecting from database...")
    await close_mongo_connection()

# --- API Endpoints ---
@app.get("/", tags=["Root"], include_in_schema=False) # Hide from API docs if desired
async def read_root():
    """Root endpoint welcome message."""
    return {"message": f"Welcome to {PROJECT_NAME}"}

@app.get("/health", status_code=200, tags=["Health Check"])
async def health_check() -> Dict[str, Any]:
    """
    Comprehensive health check endpoint that verifies:
    - Application status and metrics (uptime, memory)
    - Database connectivity and collections
    """
    # Get database health information
    db_health = await check_database_health()

    # Get system metrics using psutil
    process = psutil.Process()
    memory_info = process.memory_info()

    # Calculate uptime
    uptime_seconds = time.time() - APP_START_TIME
    uptime = str(timedelta(seconds=int(uptime_seconds)))

    # Prepare response dictionary
    health_info = {
        "status": "OK", # Start with OK, potentially downgrade based on checks
        "application": {
            "name": PROJECT_NAME,
            "version": VERSION,
            "status": "OK", # Application itself is running if it responds
            "uptime": uptime,
            "memory_usage": {
                "rss_bytes": memory_info.rss,  # Resident Set Size (bytes)
                "vms_bytes": memory_info.vms,  # Virtual Memory Size (bytes)
                "percent": f"{process.memory_percent():.2f}%" # Memory usage percentage
            }
        },
        "database": db_health, # Include detailed DB health dictionary
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z" # Use UTC timestamp
    }

    # Determine overall status based on database health
    if db_health.get("status") == "ERROR":
        health_info["status"] = "ERROR"
    elif db_health.get("status") == "WARNING": # If check_database_health can return WARNING
        health_info["status"] = "WARNING"

    return health_info

# --- Include API Routers ---
# Apply the configured prefix (e.g., /api/v1) to all included routers
app.include_router(schools.router, prefix=API_V1_PREFIX)
app.include_router(teachers.router, prefix=API_V1_PREFIX)
app.include_router(class_groups.router, prefix=API_V1_PREFIX)
app.include_router(students.router, prefix=API_V1_PREFIX)
app.include_router(assignments.router, prefix=API_V1_PREFIX)
app.include_router(documents.router, prefix=API_V1_PREFIX) # Includes documents router
app.include_router(results.router, prefix=API_V1_PREFIX)   # Includes results router
app.include_router(dashboard.router, prefix=API_V1_PREFIX) # NEW: Include dashboard router

# --- TODOs & Future Enhancements ---
# TODO: Add middleware, CORS configuration, and global exception handlers
# from fastapi.middleware.cors import CORSMiddleware
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # SECURITY: Update for production environments!
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

