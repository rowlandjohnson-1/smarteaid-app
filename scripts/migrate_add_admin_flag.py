import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv # To load env vars from .env file
import sys

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
    from backend.app.db.database import get_database, close_db_connection, connect_to_mongo
    USE_APP_DB_MODULE = True
    print("Using database module from backend.app.db...")
except ImportError as e:
    USE_APP_DB_MODULE = False
    print(f"Database module import failed ({e}), will attempt direct connection using environment variables or hardcoded values.")

# Constants (should match your project)
TEACHER_COLLECTION = "teachers"

# --- WARNING: Hardcoded Credentials ---
# Using hardcoded values for the direct connection fallback.
# It is strongly recommended to use environment variables (.env file) instead.
# --------------------------------------
HARDCODED_MONGODB_URL = "mongodb://cosmos-sdt-uks-aidetector-dev-2sqnu5js6ahlw:BxElpPHLdWJpyC9hdK8Go8q7k2jibQnN4p80SGYO5rlHi6b3Dvvz0dJwtIqMPgNmKmSbgc7gUlojACDbJRZupw==@cosmos-sdt-uks-aidetector-dev-2sqnu5js6ahlw.mongo.cosmos.azure.com:10255/?ssl=true&retrywrites=false&replicaSet=globaldb&maxIdleTimeMS=120000&appName=@cosmos-sdt-uks-aidetector-dev-2sqnu5js6ahlw@"
HARDCODED_DB_NAME = "aidetector_dev"

async def run_migration_direct_connection():
    """Connects directly using HARDCODED values and runs the migration."""
    mongodb_url = HARDCODED_MONGODB_URL
    database_name = HARDCODED_DB_NAME
    client = None
    update_result = None
    try:
        print(f"Connecting directly to MongoDB (using hardcoded credentials)...")
        client = AsyncIOMotorClient(mongodb_url, serverSelectionTimeoutMS=10000)
        await client.admin.command('ping')
        db = client[database_name]
        print(f"Successfully connected to database: {database_name}")

        collection = db[TEACHER_COLLECTION]
        print(f"Running migration on collection: '{TEACHER_COLLECTION}'...")

        # Filter: Find documents where 'is_administrator' field does not exist
        filter_query = {"is_administrator": {"$exists": False}}

        # Update: Set 'is_administrator' to False
        update_operation = {"$set": {"is_administrator": False}}

        print(f"Updating documents where 'is_administrator' does not exist...")
        update_result = await collection.update_many(filter_query, update_operation)

        print("\n--- Migration Result ---")
        print(f"Documents matched (missing 'is_administrator'): {update_result.matched_count}")
        print(f"Documents modified: {update_result.modified_count}")
        if update_result.acknowledged:
            print("Operation acknowledged by server.")
        else:
            print("Warning: Operation NOT acknowledged by server.")
        print("----------------------")

    except Exception as e:
        print(f"An error occurred during direct connection or migration: {e}")
        if update_result:
             print(f"Partial result before error: Matched={update_result.matched_count}, Modified={update_result.modified_count}")
    finally:
        if client:
            client.close()
            print("Direct MongoDB connection closed.")

async def run_migration_app_module():
    """Uses the application's database module to connect and run migration."""
    db = None
    update_result = None
    try:
        print("Connecting using application's database module...")
        await connect_to_mongo()
        db = get_database()
        if db is None:
            raise Exception("Failed to get database instance from module.")
        print(f"Successfully connected to database: {db.name}")

        collection = db[TEACHER_COLLECTION]
        print(f"Running migration on collection: '{TEACHER_COLLECTION}'...")

        # Filter: Find documents where 'is_administrator' field does not exist
        filter_query = {"is_administrator": {"$exists": False}}

        # Update: Set 'is_administrator' to False
        update_operation = {"$set": {"is_administrator": False}}

        print(f"Updating documents where 'is_administrator' does not exist...")
        update_result = await collection.update_many(filter_query, update_operation)

        print("\n--- Migration Result ---")
        print(f"Documents matched (missing 'is_administrator'): {update_result.matched_count}")
        print(f"Documents modified: {update_result.modified_count}")
        if update_result.acknowledged:
            print("Operation acknowledged by server.")
        else:
            print("Warning: Operation NOT acknowledged by server.")
        print("----------------------")

    except Exception as e:
        print(f"An error occurred using the app database module: {e}")
        if update_result:
             print(f"Partial result before error: Matched={update_result.matched_count}, Modified={update_result.modified_count}")
    finally:
        print("Closing connection via application's database module...")
        await close_db_connection()
        print("App module connection closed.")


async def main():
    dotenv_path = os.path.join(project_root, '.env')
    if os.path.exists(dotenv_path):
        print(f"Loading environment variables from: {dotenv_path}")
        load_dotenv(dotenv_path=dotenv_path)
        print("Note: Environment variables loaded, but direct connection function may use hardcoded values.")
    else:
        print("Warning: .env file not found in project root. Relying on globally set environment variables (if applicable) or hardcoded values.")

    print("\nStarting migration script to add 'is_administrator=False' to teachers missing the field.")

    if USE_APP_DB_MODULE:
        await run_migration_app_module()
    else:
        await run_migration_direct_connection()

    print("\nMigration script finished.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main()) 