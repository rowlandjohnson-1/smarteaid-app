# app/db/database.py
import motor.motor_asyncio
import logging
from pymongo.server_api import ServerApi
from app.core.config import MONGODB_URL, DB_NAME, PROJECT_NAME

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(f"{PROJECT_NAME}.db")

# Global variables to hold the client and database instances
_client: motor.motor_asyncio.AsyncIOMotorClient = None
_db = None

async def connect_to_mongo():
    """Establishes connection to the MongoDB database."""
    global _client, _db
    logger.info(f"Attempting to connect to MongoDB at {MONGODB_URL}...")
    try:
        # Cosmos DB specific - don't use Server API for Cosmos DB
        # as it's not fully compatible
        _client = motor.motor_asyncio.AsyncIOMotorClient(
            MONGODB_URL,
            tls=True,
            serverSelectionTimeoutMS=5000,
            appName=PROJECT_NAME,
            # No server_api parameter for Cosmos DB
            # Explicitly set auth source and mechanism for Cosmos DB
            authSource=DB_NAME,
            authMechanism='SCRAM-SHA-256'
        )
        
        # Use a simpler command for Cosmos DB instead of ismaster
        # Just access the database to verify connection
        _db = _client[DB_NAME]
        # Simple command that works with Cosmos DB
        await _db.command("ping")
        
        logger.info(f"Successfully connected to MongoDB/Cosmos DB database: '{DB_NAME}'")
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
    return _db

def get_mongo_client() -> motor.motor_asyncio.AsyncIOMotorClient:
    """
    Returns the MongoDB client instance. Ensures connection is established.
    NOTE: Relies on connect_to_mongo() being called at app startup.
    """
    if _client is None:
        logger.warning("Warning: MongoDB client is not initialized!")
    return _client