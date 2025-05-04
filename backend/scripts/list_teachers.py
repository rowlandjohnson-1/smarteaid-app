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
    from backend.app.models.teacher import Teacher # <<< Import the Teacher model
    USE_APP_DB_MODULE = True
    print("Using database module from backend.app.db...")
except ImportError as e:
    USE_APP_DB_MODULE = False
    Teacher = None # Set Teacher to None if import fails
    print(f"Database or Teacher model import failed ({e}), will attempt direct connection using environment variables or hardcoded values.")


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
    if Teacher is None:
        print("Error: Teacher model could not be imported. Cannot validate data.")
        return

    mongodb_url = HARDCODED_MONGODB_URL
    database_name = HARDCODED_DB_NAME

    client = None
    try:
        print(f"Connecting directly to MongoDB (using hardcoded credentials)...")
        client = AsyncIOMotorClient(mongodb_url, serverSelectionTimeoutMS=10000)
        await client.admin.command('ping')
        db = client[database_name]
        print(f"Successfully connected to database: {database_name}")

        collection = db[TEACHER_COLLECTION]
        print(f"Fetching teachers from collection: '{TEACHER_COLLECTION}'...")

        validated_teachers = [] # Store validated dictionaries
        cursor = collection.find({})
        async for teacher_doc in cursor:
            try:
                # --- START: Validate with Pydantic Model ---
                # Map _id to id if necessary before validation
                if '_id' in teacher_doc and 'id' not in teacher_doc:
                     teacher_doc['id'] = str(teacher_doc['_id']) # Kinde ID is already string, but map just in case

                # Map kinde_id to id if kinde_id exists and id doesn't (handle older docs maybe)
                if 'kinde_id' in teacher_doc and 'id' not in teacher_doc:
                    teacher_doc['id'] = teacher_doc['kinde_id']

                # Ensure _id exists before validation if using alias
                # Pydantic v2 should handle alias mapping if 'id' is present
                # but let's keep this for robustness if id is missing but _id isn't
                if 'id' not in teacher_doc and '_id' in teacher_doc:
                     teacher_doc['id'] = str(teacher_doc['_id']) # Treat _id as the primary ID source


                teacher_model = Teacher.model_validate(teacher_doc)
                # Append the model dump (dictionary with defaults)
                validated_teachers.append(teacher_model.model_dump(by_alias=True)) # Use by_alias to show '_id'
                # --- END: Validate with Pydantic Model ---
            except ValidationError as e:
                print(f"\n--- Validation Error for document: ---")
                pprint(teacher_doc)
                print(f"Validation Error: {e}")
                print(f"--- End Validation Error ---")
                # Optionally append the raw doc or skip it
                # validated_teachers.append({"_id": teacher_doc.get('_id'), "error": "Validation Failed", "raw_data": teacher_doc})
            except Exception as e_gen:
                print(f"\n--- General Error processing document: {teacher_doc.get('_id')} ---")
                print(f"Error: {e_gen}")
                print(f"--- End General Error ---")


        if not validated_teachers:
            print("No teachers found or processed in the collection.")
        else:
            print(f"Found and processed {len(validated_teachers)} teacher(s):")
            print("-" * 30)
            for teacher_data in validated_teachers:
                pprint(teacher_data, sort_dicts=False) # Print the validated dictionary
                print("-" * 30)

    except Exception as e:
        print(f"An error occurred during direct connection or fetching: {e}")
    finally:
        if client:
            client.close()
            print("Direct MongoDB connection closed.")

async def list_all_teachers_app_module():
    """Uses the application's database module to connect and list teachers."""
    if Teacher is None:
        print("Error: Teacher model could not be imported. Cannot validate data.")
        return
    db = None
    try:
        print("Connecting using application's database module...")
        await connect_to_mongo()
        db = get_database()
        if db is None:
            raise Exception("Failed to get database instance from module.")
        print(f"Successfully connected to database: {db.name}")

        collection = db[TEACHER_COLLECTION]
        print(f"Fetching teachers from collection: '{TEACHER_COLLECTION}'...")

        validated_teachers = [] # Store validated dictionaries
        cursor = collection.find({})
        async for teacher_doc in cursor:
             try:
                # --- START: Validate with Pydantic Model ---
                 # Map _id to id if necessary before validation
                if '_id' in teacher_doc and 'id' not in teacher_doc:
                     teacher_doc['id'] = str(teacher_doc['_id']) # Kinde ID is already string, but map just in case

                 # Map kinde_id to id if kinde_id exists and id doesn't (handle older docs maybe)
                if 'kinde_id' in teacher_doc and 'id' not in teacher_doc:
                    teacher_doc['id'] = teacher_doc['kinde_id']

                # Ensure _id exists before validation if using alias
                if 'id' not in teacher_doc and '_id' in teacher_doc:
                     teacher_doc['id'] = str(teacher_doc['_id'])


                teacher_model = Teacher.model_validate(teacher_doc)
                # Append the model dump (dictionary with defaults)
                validated_teachers.append(teacher_model.model_dump(by_alias=True)) # Use by_alias to show '_id'
                # --- END: Validate with Pydantic Model ---
             except ValidationError as e:
                print(f"\n--- Validation Error for document: ---")
                pprint(teacher_doc)
                print(f"Validation Error: {e}")
                print(f"--- End Validation Error ---")
             except Exception as e_gen:
                print(f"\n--- General Error processing document: {teacher_doc.get('_id')} ---")
                print(f"Error: {e_gen}")
                print(f"--- End General Error ---")


        if not validated_teachers:
            print("No teachers found or processed in the collection.")
        else:
            print(f"Found and processed {len(validated_teachers)} teacher(s):")
            print("-" * 30)
            for teacher_data in validated_teachers:
                pprint(teacher_data, sort_dicts=False) # Print the validated dictionary
                print("-" * 30)

    except Exception as e:
        print(f"An error occurred using the app database module: {e}")
    finally:
        print("Closing connection via application's database module...")
        await close_db_connection()
        print("App module connection closed.")


async def main():
    dotenv_path = os.path.join(project_root, '.env')
    if os.path.exists(dotenv_path):
        print(f"Loading environment variables from: {dotenv_path}")
        load_dotenv(dotenv_path=dotenv_path)
        print("Note: Environment variables loaded, but the direct connection function may use hardcoded values.")
    else:
        print("Warning: .env file not found in project root. Relying on globally set environment variables (if applicable) or hardcoded values.")

    if USE_APP_DB_MODULE:
        await list_all_teachers_app_module()
    else:
        await list_all_teachers_direct_connection()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
