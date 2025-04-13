# app/db/crud.py
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo import ReturnDocument # Needed for find_one_and_update
import uuid
from typing import List, Optional
from datetime import datetime, timezone # Ensure timezone aware for consistency
import logging

# Import our database access function and Pydantic models
from .database import get_database
from ..models.school import SchoolCreate, SchoolUpdate, School

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO) # Or load config from elsewhere

# Define MongoDB Collection Names
SCHOOL_COLLECTION = "schools"
# Add other collection names here later...

# Helper function to get a specific collection
def _get_collection(collection_name: str) -> Optional[AsyncIOMotorCollection]:
    """Internal helper to get a collection instance."""
    db = get_database()
    if db:
        return db[collection_name]
    logger.error("Database connection is not available.")
    return None

# --- School CRUD Functions ---

async def create_school(school_in: SchoolCreate) -> Optional[School]:
    """
    Creates a new School record in the database.
    (Code as previously provided)
    """
    collection = _get_collection(SCHOOL_COLLECTION)
    if not collection:
        return None

    new_school_id = uuid.uuid4()
    # Use timezone aware datetime
    now = datetime.now(timezone.utc)

    # Use model_dump for Pydantic V2
    school_doc = school_in.model_dump()

    school_doc["_id"] = new_school_id
    school_doc["created_at"] = now
    school_doc["updated_at"] = now

    logger.info(f"Attempting to insert school: {school_doc}")
    try:
        inserted_result = await collection.insert_one(school_doc)
        if inserted_result.acknowledged and inserted_result.inserted_id == new_school_id:
            created_doc = await collection.find_one({"_id": new_school_id})
            if created_doc:
                logger.info(f"Successfully created school with ID: {new_school_id}")
                # Ensure 'id' field (if present in School model) is handled if needed
                # If School model expects 'id' instead of '_id', you might need alias or manual mapping
                return School(**created_doc)
            else:
                logger.error(f"Failed to retrieve school after insertion (ID: {new_school_id})")
                return None
        else:
            logger.error(f"MongoDB insert operation not acknowledged for school ID: {new_school_id}")
            return None
    except Exception as e:
        logger.error(f"Error during school insertion: {e}", exc_info=True)
        return None

# --- Get School by ID ---
async def get_school_by_id(school_id: uuid.UUID) -> Optional[School]:
    """
    Retrieves a single school by its unique ID.

    Args:
        school_id: The UUID of the school to retrieve.

    Returns:
        The School object as a Pydantic model, or None if not found or error.
    """
    collection = _get_collection(SCHOOL_COLLECTION)
    if not collection:
        return None

    logger.info(f"Attempting to retrieve school with ID: {school_id}")
    try:
        school_doc = await collection.find_one({"_id": school_id})
        if school_doc:
            logger.info(f"Successfully retrieved school with ID: {school_id}")
            return School(**school_doc)
        else:
            logger.warning(f"School with ID: {school_id} not found.")
            return None
    except Exception as e:
        logger.error(f"Error retrieving school with ID {school_id}: {e}", exc_info=True)
        return None

# --- Get All Schools (with basic pagination) ---
async def get_all_schools(skip: int = 0, limit: int = 100) -> List[School]:
    """
    Retrieves a list of schools, with optional pagination.

    Args:
        skip: Number of documents to skip (for pagination).
        limit: Maximum number of documents to return.

    Returns:
        A list of School objects as Pydantic models. Empty list if none found or error.
    """
    collection = _get_collection(SCHOOL_COLLECTION)
    schools_list: List[School] = []
    if not collection:
        return schools_list # Return empty list if no DB connection

    logger.info(f"Attempting to retrieve schools with skip={skip}, limit={limit}")
    try:
        # Create an async cursor
        cursor = collection.find({}).skip(skip).limit(limit)
        # Iterate over the cursor asynchronously
        async for school_doc in cursor:
            try:
                schools_list.append(School(**school_doc))
            except Exception as model_err: # Catch potential Pydantic validation errors
                 logger.error(f"Error converting document to School model for ID {school_doc.get('_id', 'N/A')}: {model_err}")
                 # Decide whether to skip this record or stop the process

        logger.info(f"Successfully retrieved {len(schools_list)} schools.")
        return schools_list
    except Exception as e:
        logger.error(f"Error retrieving schools: {e}", exc_info=True)
        return schools_list # Return empty list on error

# --- Update School ---
async def update_school(school_id: uuid.UUID, school_in: SchoolUpdate) -> Optional[School]:
    """
    Updates an existing school record.

    Args:
        school_id: The UUID of the school to update.
        school_in: A Pydantic model containing the fields to update.

    Returns:
        The updated School object as a Pydantic model, or None if not found or error.
    """
    collection = _get_collection(SCHOOL_COLLECTION)
    if not collection:
        return None

    # Convert update model to dict, excluding fields that were not set in the request
    # This prevents accidentally overwriting fields with None if they weren't provided
    update_data = school_in.model_dump(exclude_unset=True)

    # Don't allow updating the ID or created_at timestamp
    update_data.pop("_id", None)
    update_data.pop("id", None) # If you alias _id to id in Pydantic model
    update_data.pop("created_at", None)

    # If there's anything actually to update...
    if not update_data:
         logger.warning(f"Update requested for school {school_id} with no data fields provided.")
         # Optionally retrieve and return the existing document without changes
         return await get_school_by_id(school_id)

    # Always update the 'updated_at' timestamp
    update_data["updated_at"] = datetime.now(timezone.utc)

    logger.info(f"Attempting to update school {school_id} with data: {update_data}")
    try:
        updated_doc = await collection.find_one_and_update(
            {"_id": school_id},
            {"$set": update_data},
            return_document=ReturnDocument.AFTER # Return the document *after* the update
        )

        if updated_doc:
            logger.info(f"Successfully updated school with ID: {school_id}")
            return School(**updated_doc)
        else:
            # This occurs if the document with school_id wasn't found
            logger.warning(f"School with ID: {school_id} not found for update.")
            return None
    except Exception as e:
        logger.error(f"Error updating school with ID {school_id}: {e}", exc_info=True)
        return None

# --- Delete School ---
async def delete_school(school_id: uuid.UUID) -> bool:
    """
    Deletes a school record from the database.

    Args:
        school_id: The UUID of the school to delete.

    Returns:
        True if the school was successfully deleted, False otherwise.
    """
    collection = _get_collection(SCHOOL_COLLECTION)
    if not collection:
        return False

    logger.info(f"Attempting to delete school with ID: {school_id}")
    try:
        delete_result = await collection.delete_one({"_id": school_id})

        if delete_result.deleted_count == 1:
            logger.info(f"Successfully deleted school with ID: {school_id}")
            return True
        else:
            # This occurs if the document with school_id wasn't found
            logger.warning(f"School with ID: {school_id} not found for deletion.")
            return False
    except Exception as e:
        logger.error(f"Error deleting school with ID {school_id}: {e}", exc_info=True)
        return False

# --- Add CRUD functions for Teacher, Student etc. later ---