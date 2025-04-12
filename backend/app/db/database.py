# app/db/database.py
import motor.motor_asyncio
import logging
import urllib.parse
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
            retryWrites=False,  # Required for Cosmos DB
            directConnection=True,  # Try direct connection
            serverSelectionTimeoutMS=30000,  # Increase timeout
            connectTimeoutMS=30000,
            socketTimeoutMS=30000,
            waitQueueTimeoutMS=30000,
            maxPoolSize=10,
            minPoolSize=0
        )
        
        # Get the database
        _db = _client[DB_NAME]
        
        # A simpler check - just try to list collections
        collections = await _db.list_collection_names()
        logger.info(f"Found {len(collections)} collections in database")
        
        logger.info(f"Successfully connected to Cosmos DB database: '{DB_NAME}'")
    except Exception as e:
        logger.error(f"ERROR: Could not connect to MongoDB: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Attempt to log some diagnostic information
        try:
            # Extract host and credentials from connection string for diagnostics
            if MONGODB_URL.startswith('mongodb://'):
                parts = MONGODB_URL.split('@')
                if len(parts) > 1:
                    host_part = parts[1].split('/?')[0]
                    logger.info(f"Attempting to diagnose connection to host: {host_part}")
                    
                    # Test if the host is reachable
                    import socket
                    hostname, port = host_part.split(':')
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5)
                    result = sock.connect_ex((hostname, int(port)))
                    if result == 0:
                        logger.info(f"Port {port} on {hostname} is open")
                    else:
                        logger.error(f"Port {port} on {hostname} is not reachable, error code: {result}