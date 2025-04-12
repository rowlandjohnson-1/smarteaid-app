# app/db/database.py
import motor.motor_asyncio
import logging
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
        # For Azure Cosmos DB with MongoDB API
        _client = motor.motor_asyncio.AsyncIOMotorClient(
            MONGODB_URL,
            tls=True,
            retryWrites=False,  # Still required for Cosmos DB
            serverSelectionTimeoutMS=10000,
            maxPoolSize=10
        )
        
        # Get the database
        _db = _client[DB_NAME]
        
        # Try to list collections to verify connection
        collections = await _db.list_collection_names()
        logger.info(f"Found {len(collections)} collections in database")
        
        logger.info(f"Successfully connected to Cosmos DB database: '{DB_NAME}'")
        return True
    except Exception as e:
        logger.error(f"ERROR: Could not connect to MongoDB: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        _client = None
        _db = None
        return False

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