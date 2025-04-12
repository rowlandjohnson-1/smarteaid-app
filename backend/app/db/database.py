# app/db/database.py
import motor.motor_asyncio
import logging
from pymongo.server_api import ServerApi
from app.core.config import MONGODB_URL, DB_NAME, PROJECT_NAME

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(f"{PROJECT_NAME}.db")

# Global variables to hold the client and database instances
# Note: In more complex scenarios, you might manage this via dependency injection
_client: motor.motor_asyncio.AsyncIOMotorClient = None
_db = None

async def connect_to_mongo():
    """Establishes connection to the MongoDB database."""
    global _client, _db
    logger.info(f"Attempting to connect to MongoDB at {MONGODB_URL}...")
    try:
        # Define the Stable API version to use
        server_api = ServerApi('1')
        # Create the client, specifying the server_api version
        _client = motor.motor_asyncio.AsyncIOMotorClient(
            MONGODB_URL,
            tls=True,
            serverSelectionTimeoutMS=5000,
            appName=PROJECT_NAME,
            server_api=server_api
        )
        # The ismaster command is cheap and does not require auth.
        await _client.admin.command('ismaster')  # Ping the server to verify connection
        _db = _client[DB_NAME]  # Get the specific database instance
        logger.info(f"Successfully connected to MongoDB database: '{DB_NAME}' using Stable API v1")
    except Exception as e:
        logger.error(f"ERROR: Could not connect to MongoDB: {e}")
        _client = None
        _db = None

async def close_mongo_connection():
    """Closes the MongoDB connection."""
    global _client
    if _client:
        logger.info("Closing MongoDB connection...")
        _client.close()
        logger.info("MongoDB connection closed.")

def get_database():
    """
    Returns the database instance. Ensures connection is established.
    NOTE: Relies on connect_to_mongo() being called at app startup.
    """
    if _db is None:
        logger.warning("Warning: Database instance is not initialized!")
        # Depending on design, you might raise an error or attempt connection here.
        # For now, assuming startup handles connection.
    return _db

def get_mongo_client() -> motor.motor_asyncio.AsyncIOMotorClient:
    """
    Returns the MongoDB client instance. Ensures connection is established.
    NOTE: Relies on connect_to_mongo() being called at app startup.
    """
    if _client is None:
        logger.warning("Warning: MongoDB client is not initialized!")
    return _client