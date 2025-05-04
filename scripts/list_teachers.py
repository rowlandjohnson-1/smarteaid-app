import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from pprint import pprint
from dotenv import load_dotenv # To load env vars from .env file
import sys
from pydantic import ValidationError # Import ValidationError

# --- START: Improved Path Logic ---
# Get the directory containing the script
script_path = os.path.abspath(__file__)
scripts_dir = os.path.dirname(script_path)
# Assume the project root is one level above the 'scripts' directory
project_root = os.path.dirname(scripts_dir)

# Add the project root to sys.path to allow imports like 'from backend...'
if project_root not in sys.path:
    print(f"Adding project root to sys.path: {project_root}")
    sys.path.insert(0, project_root)
# --- END: Improved Path Logic ---

# --- Database Access ---
# Attempt to import the get_database function if available, otherwise use direct connection
try:
    # Adjust the import path according to your project structure
    from backend.app.db.database import get_database, close_db_connection, connect_to_mongo
    USE_APP_DB_MODULE = True
    print("Using database module from backend.app.db...")
except ImportError:
    USE_APP_DB_MODULE = False
    print("Database module not found, will attempt direct connection using environment variables or hardcoded values.")


# Constants (should match your project)
TEACHER_COLLECTION = "teachers"

# --- WARNING: Hardcoded Credentials --- 
# The following connection string and database name are hardcoded.
# It is strongly recommended to use environment variables (.env file) instead 
# for better security and flexibility.
# --------------------------------------
HARDCODED_MONGODB_URL = "mongodb://cosmos-sdt-uks-aidetector-dev-2sqnu5js6ahlw:BxElpPHLdWJpyC9hdK8Go8q7k2jibQnN4p80SGYO5rlHi6b3Dvvz0dJwtIqMPgNmKmSbgc7gUlojACDbJRZupw==@cosmos-sdt-uks-aidetector-dev-2sqnu5js6ahlw.mongo.cosmos.azure.com:10255/?ssl=true&retrywrites=false&replicaSet=globaldb&maxIdleTimeMS=120000&appName=@cosmos-sdt-uks-aidetector-dev-2sqnu5js6ahlw@"
HARDCODED_DB_NAME = "aidetector_dev"

async def list_all_teachers_direct_connection():
    """Connects directly using HARDCODED values and lists teachers."""
    # Use hardcoded values instead of environment variables
    mongodb_url = HARDCODED_MONGODB_URL
    database_name = HARDCODED_DB_NAME

    client = None
    try:
        print(f"Connecting directly to MongoDB (using hardcoded credentials)...")
        # Increase timeout slightly for script execution if needed
        client = AsyncIOMotorClient(mongodb_url, serverSelectionTimeoutMS=10000) 
        # Verify connection
        await client.admin.command('ping') 
        db = client[database_name]
        print(f"Successfully connected to database: {database_name}")
        
        collection = db[TEACHER_COLLECTION]
        print(f"Fetching teachers from collection: '{TEACHER_COLLECTION}'...")

        teachers = []
        cursor = collection.find({}) # Find all documents
        async for teacher_doc in cursor:
            teachers.append(teacher_doc)
        
        if not teachers:
            print("No teachers found in the collection.")
        else:
            print(f"Found {len(teachers)} teacher(s):")
            print("-" * 30) # Separator
            for teacher in teachers:
                pprint(teacher, sort_dicts=False) # Use pprint for readable output
                print("-" * 30) # Separator

    except Exception as e:
        print(f"An error occurred during direct connection or fetching: {e}")
    finally:
        if client:
            client.close()
            print("Direct MongoDB connection closed.")

async def list_all_teachers_app_module():
    """Uses the application's database module to connect and list teachers."""
    db = None
    try:
        print("Connecting using application's database module...")
        # Ensure connection is established (depends on your connect_to_mongo implementation)
        await connect_to_mongo() 
        db = get_database()
        if db is None:
            raise Exception("Failed to get database instance from module.")
        print(f"Successfully connected to database: {db.name}")

        collection = db[TEACHER_COLLECTION]
        print(f"Fetching teachers from collection: '{TEACHER_COLLECTION}'...")

        teachers = []
        cursor = collection.find({}) # Find all documents
        async for teacher_doc in cursor:
            teachers.append(teacher_doc)
            
        if not teachers:
            print("No teachers found in the collection.")
        else:
            print(f"Found {len(teachers)} teacher(s):")
            print("-" * 30) # Separator
            for teacher in teachers:
                pprint(teacher, sort_dicts=False) # Use pprint for readable output
                print("-" * 30) # Separator
                
    except Exception as e:
        print(f"An error occurred using the app database module: {e}")
    finally:
        # Ensure disconnection is handled (depends on your close_db_connection)
        print("Closing connection via application's database module...")
        await close_db_connection()
        print("App module connection closed.")


async def main():
    # Load environment variables from .env file if it exists
    dotenv_path = os.path.join(project_root, '.env')
    if os.path.exists(dotenv_path):
        print(f"Loading environment variables from: {dotenv_path}")
        load_dotenv(dotenv_path=dotenv_path)
        print("Note: Environment variables loaded, but the direct connection function will use hardcoded values.") 
    else:
        print("Warning: .env file not found in project root. Relying on globally set environment variables (if applicable) or hardcoded values.")

    if USE_APP_DB_MODULE:
        await list_all_teachers_app_module()
    else:
        await list_all_teachers_direct_connection()

if __name__ == "__main__":
    # For Windows compatibility with asyncio + Motor
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main()) 