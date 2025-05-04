# app/db/crud.py

# --- Core Imports ---
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from pymongo.collation import Collation, CollationStrength # Add for case-insensitive aggregation if needed
import uuid
from typing import List, Optional, Dict, Any, TypeVar, Type, Tuple
from datetime import datetime, timezone, timedelta, date as date_type # Avoid naming conflict with datetime module
import logging
import re
from contextlib import asynccontextmanager
from functools import wraps
import asyncio
from pydantic import ValidationError
# FIX: Import ResourceNotFoundError from azure.core.exceptions
from azure.core.exceptions import ResourceNotFoundError 
from azure.storage.blob import BlobServiceClient
import os
import calendar

# --- Database Access ---
from .database import get_database

# --- Pydantic Models ---
from app.models.school import SchoolCreate, SchoolUpdate, School
# --- CORRECTED Teacher model imports ---
# Import TeacherCreate as defined in your teacher.py
from app.models.teacher import Teacher, TeacherCreate, TeacherUpdate, TeacherRole
# ------------------------------------
from app.models.class_group import ClassGroup, ClassGroupCreate, ClassGroupUpdate
from app.models.student import Student, StudentCreate, StudentUpdate
from app.models.assignment import Assignment, AssignmentCreate, AssignmentUpdate
from app.models.document import Document, DocumentCreate, DocumentUpdate
from app.models.result import Result, ResultCreate, ResultUpdate, ResultStatus
# --- Import Enums used in Teacher model ---
from app.models.enums import DocumentStatus, ResultStatus, FileType, MarketingSource
from app.models.batch import Batch, BatchCreate, BatchUpdate, BatchWithDocuments

# --- Logging Setup ---
logger = logging.getLogger(__name__)

# --- MongoDB Collection Names ---
SCHOOL_COLLECTION = "schools"
TEACHER_COLLECTION = "teachers"
CLASSGROUP_COLLECTION = "classgroups"
STUDENT_COLLECTION = "students"
ASSIGNMENT_COLLECTION = "assignments"
DOCUMENT_COLLECTION = "documents"
RESULT_COLLECTION = "results"

# --- Transaction and Helper Functions ---
@asynccontextmanager
async def transaction():
    db = get_database()
    if db is None: raise RuntimeError("Database connection not available for transaction (db is None)")
    if not hasattr(db, 'client') or db.client is None:
        logger.warning("Database client not available or does not support sessions. Proceeding without transaction.")
        yield None
        return # Exit context manager
    if hasattr(db.client, 'start_session'):
        session = None # Initialize session to None
        try:
            async with await db.client.start_session() as session:
                async with session.start_transaction():
                    logger.debug("MongoDB transaction started.")
                    try:
                        yield session
                        if session.in_transaction:
                            logger.debug("MongoDB transaction committing.")
                            await session.commit_transaction()
                            logger.debug("MongoDB transaction committed.")
                        else:
                            logger.warning("Session not in transaction at commit point.")
                    except Exception as e:
                        logger.error(f"MongoDB transaction aborted due to error: {e}", exc_info=True)
                        if session and session.in_transaction:
                            await session.abort_transaction()
                            logger.debug("MongoDB transaction explicitly aborted.")
                        raise
        except Exception as outer_e:
            # Catch potential errors starting the session itself
            logger.error(f"Failed to start MongoDB session or transaction: {outer_e}", exc_info=True)
            raise # Re-raise the exception that occurred during session/transaction start

    else:
        logger.warning("Database client does not support sessions/transactions. Proceeding without transaction.")
        yield None


def with_transaction(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Check if a session is already provided (nested transaction)
        session = kwargs.get('session')
        if session is not None:
            # If called within an existing transaction, just execute the function
            logger.debug(f"Function {func.__name__} called within existing session.")
            return await func(*args, **kwargs)
        else:
            # If no session provided, start a new one (or proceed without if not supported)
            try:
                async with transaction() as new_session:
                    # Pass the new session (or None if transactions not supported) to the function
                    kwargs['session'] = new_session
                    logger.debug(f"Function {func.__name__} starting with new/no session.")
                    result = await func(*args, **kwargs)
                    logger.debug(f"Function {func.__name__} completed within new/no session.")
                    return result
            except Exception as e:
                # Log error from transaction context or the function itself
                logger.error(f"Operation failed for function {func.__name__}: {e}", exc_info=True)
                # Decide what to return on failure. None is common.
                return None
    return wrapper

def soft_delete_filter(include_deleted: bool = False) -> Dict[str, Any]:
    if include_deleted: return {}
    # return {"is_deleted": False} # Previous implementation
    # NEW: Filter for documents where is_deleted is NOT True (includes missing or False)
    return {"is_deleted": {"$ne": True}} 

def _get_collection(collection_name: str) -> Optional[AsyncIOMotorCollection]:
    db = get_database()
    if db is not None: return db[collection_name]
    logger.error("Database connection is not available (db object is None). Cannot get collection.")
    return None

# --- School CRUD Functions ---
@with_transaction
async def create_school(school_in: SchoolCreate, session=None) -> Optional[School]:
    collection = _get_collection(SCHOOL_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None
    new_school_id = uuid.uuid4()
    school_doc = school_in.model_dump(); school_doc["_id"] = new_school_id
    school_doc["created_at"] = now; school_doc["updated_at"] = now; school_doc["deleted_at"] = None
    logger.info(f"Inserting school: {school_doc['_id']}")
    try:
        inserted_result = await collection.insert_one(school_doc, session=session)
        if inserted_result.acknowledged: created_doc = await collection.find_one({"_id": new_school_id}, session=session)
        else: logger.error(f"Insert not acknowledged for school ID: {new_school_id}"); return None
        if created_doc: return School(**created_doc) # Assumes schema handles alias
        else: logger.error(f"Failed to retrieve school after insert: {new_school_id}"); return None
    except Exception as e: logger.error(f"Error inserting school: {e}", exc_info=True); return None

async def get_school_by_id(school_id: uuid.UUID, include_deleted: bool = False, session=None) -> Optional[School]:
    collection = _get_collection(SCHOOL_COLLECTION);
    if collection is None: return None
    logger.info(f"Getting school ID: {school_id}")
    query = {"_id": school_id}; query.update(soft_delete_filter(include_deleted))
    try: school_doc = await collection.find_one(query, session=session)
    except Exception as e: logger.error(f"Error getting school: {e}", exc_info=True); return None
    if school_doc: return School(**school_doc) # Assumes schema handles alias
    else: logger.warning(f"School {school_id} not found."); return None

async def get_all_schools(skip: int = 0, limit: int = 100, include_deleted: bool = False, session=None) -> List[School]:
    collection = _get_collection(SCHOOL_COLLECTION); schools_list: List[School] = []
    if collection is None: return schools_list
    query = soft_delete_filter(include_deleted)
    logger.info(f"Getting all schools (deleted={include_deleted}) skip={skip} limit={limit}")
    try:
        cursor = collection.find(query, session=session).skip(skip).limit(limit)
        async for doc in cursor:
            try:
                mapped_data = {**doc}
                if "_id" in mapped_data: mapped_data["id"] = mapped_data.pop("_id")
                else: logger.warning(f"School doc missing '_id': {doc}"); continue
                schools_list.append(School(**mapped_data))
            except Exception as validation_err: logger.error(f"Pydantic validation failed for school doc {doc.get('_id', 'UNKNOWN')}: {validation_err}")
    except Exception as e: logger.error(f"Error getting all schools: {e}", exc_info=True)
    return schools_list

@with_transaction
async def update_school(school_id: uuid.UUID, school_in: SchoolUpdate, session=None) -> Optional[School]:
    collection = _get_collection(SCHOOL_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None
    update_data = school_in.model_dump(exclude_unset=True)
    update_data.pop("_id", None); update_data.pop("id", None); update_data.pop("created_at", None); update_data.pop("deleted_at", None)
    if not update_data: logger.warning(f"No update data for school {school_id}"); return await get_school_by_id(school_id, include_deleted=False, session=session)
    update_data["updated_at"] = now; logger.info(f"Updating school {school_id}")
    query_filter = {"_id": school_id, "deleted_at": None}
    try:
        updated_doc = await collection.find_one_and_update(query_filter, {"$set": update_data}, return_document=ReturnDocument.AFTER, session=session)
        if updated_doc: return School(**updated_doc) # Assumes schema handles alias
        else: logger.warning(f"School {school_id} not found or deleted for update."); return None
    except Exception as e: logger.error(f"Error updating school: {e}", exc_info=True); return None

@with_transaction
async def delete_school(school_id: uuid.UUID, hard_delete: bool = False, session=None) -> bool:
    collection = _get_collection(SCHOOL_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return False
    logger.info(f"{'Hard' if hard_delete else 'Soft'} deleting school {school_id}")
    count = 0
    try:
        if hard_delete: result = await collection.delete_one({"_id": school_id}, session=session); count = result.deleted_count
        else: result = await collection.update_one({"_id": school_id, "deleted_at": None}, {"$set": {"deleted_at": now, "updated_at": now}}, session=session); count = result.modified_count
    except Exception as e: logger.error(f"Error deleting school: {e}", exc_info=True); return False
    if count == 1: logger.info(f"Successfully deleted school {school_id}"); return True
    else: logger.warning(f"School {school_id} not found or already deleted."); return False


# --- Teacher CRUD Functions ---
# @with_transaction # Keep commented out if transactions cause issues
async def create_teacher(
    teacher_in: TeacherCreate, # Use TeacherCreate as defined in teacher.py
    kinde_id: str,             # Pass kinde_id separately
    session=None
) -> Optional[Teacher]:
    """
    Creates a teacher record, linking it to a Kinde ID.
    Uses data from TeacherCreate model (typically called by webhook/backend process).
    """
    # If not using transaction, session will be None here
    if session:
        logger.debug("create_teacher called within an existing session.")
    else:
        logger.warning("create_teacher called WITHOUT an active session (transaction decorator removed/disabled).")

    collection = _get_collection(TEACHER_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None

    # Generate a new internal UUID for the teacher record (_id)
    internal_id = uuid.uuid4()

    # Create the document to insert using data from TeacherCreate
    teacher_doc = teacher_in.model_dump() # Dump all fields from TeacherCreate
    teacher_doc["_id"] = internal_id      # Set internal DB ID
    teacher_doc["kinde_id"] = kinde_id    # Add the Kinde ID

    # Set timestamps and soft delete status
    teacher_doc["created_at"] = now; teacher_doc["updated_at"] = now; teacher_doc["deleted_at"] = None

    # Ensure defaults from TeacherBase are applied if not explicitly in TeacherCreate dump
    # Pydantic v2 model_dump includes defaults by default
    # We might need explicit conversion for enums if use_enum_values=False in model
    if isinstance(teacher_doc.get("role"), TeacherRole):
        teacher_doc["role"] = teacher_doc["role"].value # Store the string value
    if isinstance(teacher_doc.get("how_did_you_hear"), MarketingSource):
        teacher_doc["how_did_you_hear"] = teacher_doc["how_did_you_hear"].value # Store the string value
    if "is_active" not in teacher_doc: # Ensure default is set if not present
        teacher_doc["is_active"] = True

    logger.info(f"Inserting teacher with internal ID: {internal_id}, Kinde ID: {kinde_id}")
    try:
        # Insert the document into the collection (pass session if available)
        inserted_result = await collection.insert_one(teacher_doc, session=session)
    except DuplicateKeyError:
        # This assumes you have a unique index on 'kinde_id'
        logger.warning(f"Teacher record with Kinde ID {kinde_id} already exists.")
        # Fetch and return existing record instead of failing
        return await get_teacher_by_kinde_id(kinde_id=kinde_id, session=session)
    except Exception as e:
        # Handle other potential database errors
        logger.error(f"Error inserting teacher: {e}", exc_info=True); return None

    # Verify insertion and fetch the created document using the internal ID
    if inserted_result.acknowledged:
        # Fetch outside the transaction if session is None, or use session if provided
        created_doc = await collection.find_one({"_id": internal_id}, session=session)
        if created_doc:
            return Teacher(**created_doc) # Pydantic will handle the _id to id mapping
        else:
            logger.error(f"Failed retrieve teacher post-insert: internal ID {internal_id}"); return None
    else:
        logger.error(f"Insert teacher not acknowledged: internal ID {internal_id}"); return None

async def get_teacher_by_id(teacher_id: str, session=None) -> Optional[Teacher]:
    """Get a single teacher by their internal ID (string UUID)."""
    collection = _get_collection(TEACHER_COLLECTION)
    if collection is None: return None
    logger.info(f"Getting teacher by internal ID: {teacher_id}")
    try:
        # Ensure ID is searched as string
        teacher_doc = await collection.find_one({"_id": teacher_id}, session=session)
        if teacher_doc:
            # Convert _id to string BEFORE Pydantic validation if it's a UUID
            if isinstance(teacher_doc.get("_id"), uuid.UUID):
                teacher_doc["_id"] = str(teacher_doc["_id"])
            return Teacher(**teacher_doc)
        return None
    except Exception as e:
        logger.error(f"Error getting teacher by ID: {e}", exc_info=True)
        return None

async def get_teacher_by_kinde_id(kinde_id: str, session=None) -> Optional[Teacher]:
    """Get a single teacher by their Kinde ID."""
    collection = _get_collection(TEACHER_COLLECTION)
    if collection is None: return None
    logger.info(f"Getting teacher by kinde_id: {kinde_id}")
    try:
        teacher_doc = await collection.find_one({"kinde_id": kinde_id}, session=session)
        if teacher_doc:
            # Convert _id to string BEFORE Pydantic validation if it's a UUID
            if isinstance(teacher_doc.get("_id"), uuid.UUID):
                logger.debug(f"Found teacher with UUID _id {teacher_doc['_id']} for Kinde ID {kinde_id}. Converting to string for Pydantic.")
                teacher_doc["_id"] = str(teacher_doc["_id"])
            return Teacher(**teacher_doc)
        return None
    # Keep specific ValidationError catch if desired, but broaden general Exception catch
    except ValidationError as e: # Catch Pydantic validation specifically if needed
        logger.error(f"Pydantic validation error getting teacher by Kinde ID {kinde_id}: {e}", exc_info=False) # exc_info=False for cleaner logs maybe
        return None # Return None on validation failure as before
    except Exception as e:
        # Catch any other potential errors (DB connection, etc.)
        logger.error(f"General error getting teacher by Kinde ID {kinde_id}: {e}", exc_info=True)
        return None

async def get_all_teachers(skip: int = 0, limit: int = 100, include_deleted: bool = False, session=None) -> List[Teacher]:
    collection = _get_collection(TEACHER_COLLECTION); teachers_list: List[Teacher] = []
    if collection is None: return teachers_list
    query = soft_delete_filter(include_deleted)
    logger.info(f"Getting all teachers skip={skip} limit={limit}")
    try:
        # Fetch without session
        cursor = collection.find(query).skip(skip).limit(limit)
        async for doc in cursor:
            try:
                 teachers_list.append(Teacher(**doc))
            except Exception as validation_err:
                logger.error(f"Pydantic validation failed for teacher doc {doc.get('_id', 'UNKNOWN')}: {validation_err}")
    except Exception as e:
        logger.error(f"Error getting all teachers: {e}", exc_info=True)
    return teachers_list

@with_transaction # Keep transaction for update as it modifies existing data
async def update_teacher(kinde_id: str, teacher_in: TeacherUpdate, session=None) -> Optional[Teacher]:
    """Updates a teacher's profile information identified by their Kinde ID."""
    collection = _get_collection(TEACHER_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None

    update_data = teacher_in.model_dump(exclude_unset=True)

    if 'role' in update_data and isinstance(update_data.get('role'), TeacherRole):
        update_data['role'] = update_data['role'].value

    # Remove fields that should not be updated directly
    update_data.pop("_id", None); update_data.pop("id", None)
    update_data.pop("kinde_id", None)
    update_data.pop("created_at", None); update_data.pop("deleted_at", None)
    update_data.pop("how_did_you_hear", None)
    update_data.pop("email", None) # Don't allow email update via profile

    if not update_data:
        logger.warning(f"No valid update data provided for teacher with Kinde ID {kinde_id}")
        # Fetch without session if called outside transaction
        return await get_teacher_by_kinde_id(kinde_id=kinde_id, session=session)

    update_data["updated_at"] = now
    logger.info(f"Updating teacher with Kinde ID {kinde_id} with data: {update_data}")

    query_filter = {"kinde_id": kinde_id, "deleted_at": None}

    try:
        updated_doc = await collection.find_one_and_update(
            query_filter,
            {"$set": update_data},
            return_document=ReturnDocument.AFTER,
            session=session # Pass session for transaction atomicity
        )

        if updated_doc:
            # *** ADD CONVERSION HERE ***
            # Convert _id to string BEFORE Pydantic validation if it's a UUID
            if isinstance(updated_doc.get("_id"), uuid.UUID):
                logger.debug(f"Converting updated_doc _id {updated_doc['_id']} to string for Pydantic.")
                updated_doc["_id"] = str(updated_doc["_id"])
            # *** END CONVERSION ***
            return Teacher(**updated_doc)
        else:
            logger.warning(f"Teacher with Kinde ID {kinde_id} not found or already deleted during update attempt.")
            return None
    except Exception as e:
        logger.error(f"Error during teacher update operation for Kinde ID {kinde_id}: {e}", exc_info=True)
        return None

@with_transaction # Keep transaction for delete
async def delete_teacher(kinde_id: str, hard_delete: bool = False, session=None) -> bool:
    """Deletes a teacher record identified by their Kinde ID."""
    collection = _get_collection(TEACHER_COLLECTION)
    if collection is None: return False
    logger.info(f"{'Hard' if hard_delete else 'Soft'} deleting teacher with Kinde ID {kinde_id}")
    count = 0
    query_filter = {"kinde_id": kinde_id}
    try:
        if hard_delete:
            result = await collection.delete_one(query_filter, session=session);
            count = result.deleted_count
        else:
            now = datetime.now(timezone.utc)
            query_filter_soft = {"kinde_id": kinde_id, "deleted_at": None}
            result = await collection.update_one(
                query_filter_soft,
                {"$set": {"deleted_at": now, "updated_at": now}},
                session=session # Pass session
            );
            count = result.modified_count
    except Exception as e:
        logger.error(f"Error deleting teacher with Kinde ID {kinde_id}: {e}", exc_info=True); return False

    if count == 1:
        logger.info(f"Successfully {'hard' if hard_delete else 'soft'} deleted teacher with Kinde ID {kinde_id}")
        return True
    else:
        logger.warning(f"Teacher with Kinde ID {kinde_id} not found or already deleted."); return False


# --- ClassGroup CRUD Functions ---
# --- REMOVED @with_transaction from create_class_group ---
async def create_class_group(
    class_group_in: ClassGroupCreate,
    teacher_id: uuid.UUID, # ADD teacher_id as an argument
    session=None
) -> Optional[ClassGroup]:
    """Creates a class group record using data and the provided teacher ID."""
    collection = _get_collection(CLASSGROUP_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None
    new_id = uuid.uuid4()
    doc = class_group_in.model_dump();
    doc["_id"] = new_id;
    doc["teacher_id"] = teacher_id # ADD the passed teacher_id to the document
    doc.setdefault("student_ids", [])
    doc["created_at"] = now; doc["updated_at"] = now; doc["deleted_at"] = None
    logger.info(f"Inserting class group: {doc['_id']} for teacher: {teacher_id}")
    try: inserted_result = await collection.insert_one(doc, session=session) # Pass session if provided
    except Exception as e: logger.error(f"Error inserting class group: {e}", exc_info=True); return None
    if inserted_result.acknowledged: created_doc = await collection.find_one({"_id": new_id}, session=session)
    else: logger.error(f"Insert class group not acknowledged: {new_id}"); return None
    if created_doc: return ClassGroup(**created_doc) # Assumes schema handles alias
    else: logger.error(f"Failed retrieve class group post-insert: {new_id}"); return None

async def get_class_group_by_id(class_group_id: uuid.UUID, include_deleted: bool = False, session=None) -> Optional[ClassGroup]:
    collection = _get_collection(CLASSGROUP_COLLECTION);
    if collection is None: return None
    logger.info(f"Getting class group: {class_group_id}")
    query = {"_id": class_group_id}; query.update(soft_delete_filter(include_deleted))
    try: doc = await collection.find_one(query, session=session)
    except Exception as e: logger.error(f"Error getting class group: {e}", exc_info=True); return None
    if doc: return ClassGroup(**doc) # Assumes schema handles alias
    else: logger.warning(f"Class group {class_group_id} not found."); return None

async def get_all_class_groups( teacher_id: Optional[uuid.UUID] = None, school_id: Optional[uuid.UUID] = None, skip: int = 0, limit: int = 100, include_deleted: bool = False, session=None) -> List[ClassGroup]:
    collection = _get_collection(CLASSGROUP_COLLECTION); items_list: List[ClassGroup] = []
    if collection is None: return items_list
    filter_query = soft_delete_filter(include_deleted)
    if teacher_id: filter_query["teacher_id"] = teacher_id # Assuming ClassGroup stores teacher's internal UUID (_id/id)
    # if school_id: filter_query["school_id"] = school_id # Assuming ClassGroup stores school's internal UUID (_id/id)
    logger.info(f"Getting all class groups filter={filter_query} skip={skip} limit={limit}")
    try:
        cursor = collection.find(filter_query, session=session).skip(skip).limit(limit)
        async for doc in cursor:
            try:
                mapped_data = {**doc}
                if "_id" in mapped_data: mapped_data["id"] = mapped_data.pop("_id")
                else: logger.warning(f"ClassGroup doc missing '_id': {doc}"); continue
                items_list.append(ClassGroup(**mapped_data))
            except Exception as validation_err: logger.error(f"Pydantic validation failed for class group doc {doc.get('_id', 'UNKNOWN')}: {validation_err}")
    except Exception as e: logger.error(f"Error getting all class groups: {e}", exc_info=True)
    return items_list

@with_transaction
async def update_class_group(class_group_id: uuid.UUID, class_group_in: ClassGroupUpdate, session=None) -> Optional[ClassGroup]:
    collection = _get_collection(CLASSGROUP_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None
    update_data = class_group_in.model_dump(exclude_unset=True)
    update_data.pop("_id", None); update_data.pop("id", None); # Pop internal 'id' if present
    update_data.pop("created_at", None); update_data.pop("deleted_at", None)
    # Prevent changing teacher/school association via this update if needed
    # update_data.pop("teacher_id", None)
    # update_data.pop("school_id", None)
    if not update_data: logger.warning(f"No update data for class group {class_group_id}"); return await get_class_group_by_id(class_group_id, include_deleted=False, session=session)
    update_data["updated_at"] = now; logger.info(f"Updating class group {class_group_id}")
    query_filter = {"_id": class_group_id, "deleted_at": None} # Query by _id
    try:
        updated_doc = await collection.find_one_and_update( query_filter, {"$set": update_data}, return_document=ReturnDocument.AFTER, session=session)
        if updated_doc: return ClassGroup(**updated_doc) # Assumes schema handles alias
        else: logger.warning(f"Class group {class_group_id} not found or already deleted for update."); return None
    except Exception as e: logger.error(f"Error during class group update operation: {e}", exc_info=True); return None

@with_transaction
async def delete_class_group(class_group_id: uuid.UUID, hard_delete: bool = False, session=None) -> bool:
    collection = _get_collection(CLASSGROUP_COLLECTION)
    if collection is None: return False
    logger.info(f"{'Hard' if hard_delete else 'Soft'} deleting class group {class_group_id}")
    count = 0
    try:
        if hard_delete: result = await collection.delete_one({"_id": class_group_id}, session=session); count = result.deleted_count # Query by _id
        else:
            now = datetime.now(timezone.utc)
            result = await collection.update_one({"_id": class_group_id, "deleted_at": None},{"$set": {"deleted_at": now, "updated_at": now}}, session=session); count = result.modified_count # Query by _id
    except Exception as e: logger.error(f"Error deleting class group: {e}", exc_info=True); return False
    if count == 1: return True
    else: logger.warning(f"Class group {class_group_id} not found or already deleted."); return False

# --- START: NEW CRUD FUNCTIONS for ClassGroup <-> Student Relationship ---
@with_transaction
async def add_student_to_class_group(
    class_group_id: uuid.UUID, student_id: uuid.UUID, session=None
) -> bool:
    """Adds a student ID to the student_ids array of a specific class group.

    Uses $addToSet to prevent duplicates.

    Returns:
        bool: True if the student was added or already existed, False on error or if class not found.
    """
    collection = _get_collection(CLASSGROUP_COLLECTION)
    if collection is None:
        return False
    now = datetime.now(timezone.utc)
    logger.info(f"Attempting to add student {student_id} to class group {class_group_id}")
    query_filter = {"_id": class_group_id, "deleted_at": None}
    update_operation = {
        "$addToSet": {"student_ids": student_id},  # Use $addToSet to avoid duplicates
        "$set": {"updated_at": now},
    }
    try:
        result = await collection.update_one(
            query_filter, update_operation, session=session
        )
        # update_one returns matched_count and modified_count.
        # If matched_count is 1, the class group was found.
        # modified_count will be 1 if added, 0 if student already existed. Both are success cases here.
        if result.matched_count == 1:
            logger.info(
                f"Student {student_id} added to (or already in) class group {class_group_id}. Modified count: {result.modified_count}"
            )
            return True
        else:
            logger.warning(
                f"Class group {class_group_id} not found or already deleted when trying to add student {student_id}."
            )
            return False
    except Exception as e:
        logger.error(
            f"Error adding student {student_id} to class group {class_group_id}: {e}",
            exc_info=True,
        )
        return False


@with_transaction
async def remove_student_from_class_group(
    class_group_id: uuid.UUID, student_id: uuid.UUID, session=None
) -> bool:
    """Removes a student ID from the student_ids array of a specific class group.

    Uses $pull operator.

    Returns:
        bool: True if the student was successfully removed, False otherwise (e.g., class not found, student not in class).
    """
    collection = _get_collection(CLASSGROUP_COLLECTION)
    if collection is None:
        return False
    now = datetime.now(timezone.utc)
    logger.info(f"Attempting to remove student {student_id} from class group {class_group_id}")
    query_filter = {"_id": class_group_id, "deleted_at": None}
    update_operation = {
        "$pull": {"student_ids": student_id},  # Use $pull to remove the specific student ID
        "$set": {"updated_at": now},
    }
    try:
        result = await collection.update_one(
            query_filter, update_operation, session=session
        )
        # We need modified_count to be 1 for a successful removal.
        # If matched_count is 1 but modified_count is 0, the student wasn't in the list.
        if result.modified_count == 1:
            logger.info(
                f"Successfully removed student {student_id} from class group {class_group_id}."
            )
            return True
        elif result.matched_count == 1:
            logger.warning(
                f"Student {student_id} was not found in class group {class_group_id} for removal."
            )
            return False
        else:
            logger.warning(
                f"Class group {class_group_id} not found or already deleted when trying to remove student {student_id}."
            )
            return False
    except Exception as e:
        logger.error(
            f"Error removing student {student_id} from class group {class_group_id}: {e}",
            exc_info=True,
        )
        return False
# --- END: NEW CRUD FUNCTIONS for ClassGroup <-> Student Relationship ---

# --- Student CRUD Functions (Keep existing) ---
@with_transaction
async def create_student(student_in: StudentCreate, teacher_id: str, session=None) -> Optional[Student]:
    """
    Creates a new student record in the database.

    Args:
        student_in: Pydantic model containing student data to create.
        teacher_id: The Kinde ID of the teacher creating the student. # Add teacher_id docstring
        session: Optional Motor session for transaction management.

    Returns:
        The created Student object or None if creation failed.
    """
    collection = _get_collection(STUDENT_COLLECTION)
    now = datetime.now(timezone.utc)
    if collection is None:
        return None

    new_student_id = uuid.uuid4()
    # Dump the Pydantic model, explicitly including 'teacher_id' if it's added to StudentCreate
    # If teacher_id is NOT part of StudentCreate yet, it needs to be added here.
    student_doc = student_in.model_dump(exclude_unset=True) # Using exclude_unset might be safer
    student_doc["_id"] = new_student_id
    student_doc["teacher_id"] = teacher_id # Add teacher_id to the document
    student_doc["created_at"] = now
    student_doc["updated_at"] = now
    student_doc["deleted_at"] = None
    # We might need to explicitly add teacher_id here if it's not in student_in
    # Example: student_doc["teacher_id"] = teacher_id_passed_to_function

    logger.info(f"Attempting to insert student with internal ID: {new_student_id} for teacher: {teacher_id}") # Update log
    try:
        inserted_result = await collection.insert_one(student_doc, session=session)
        if inserted_result.acknowledged:
            created_doc = await collection.find_one({"_id": new_student_id}, session=session)
            if created_doc:
                mapped_data = {**created_doc}
                if "_id" in mapped_data: mapped_data["id"] = mapped_data.pop("_id")
                return Student(**mapped_data)
            else:
                logger.error(f"Failed retrieve student post-insert: {new_student_id}"); return None
        else:
            logger.error(f"Insert student not acknowledged: {new_student_id}"); return None
    except DuplicateKeyError:
        ext_id = student_doc.get('external_student_id')
        logger.warning(f"Duplicate external_student_id: '{ext_id}' on create.")
        return None
    except Exception as e:
        logger.error(f"Error inserting student: {e}", exc_info=True); return None

async def get_student_by_id(
    student_internal_id: uuid.UUID,
    teacher_id: str, # <<< ADDED: Make teacher_id mandatory
    include_deleted: bool = False,
    session=None
) -> Optional[Student]:
    collection = _get_collection(STUDENT_COLLECTION);
    if collection is None: return None
    logger.info(f"Getting student: {student_internal_id} for teacher: {teacher_id}") # Update log
    query = {"_id": student_internal_id, "teacher_id": teacher_id}; # <<< MODIFIED: Add teacher_id check
    query.update(soft_delete_filter(include_deleted)) # Query by _id
    try:
        student_doc = await collection.find_one(query, session=session)
        if student_doc:
            mapped_data = {**student_doc}
            if "_id" in mapped_data: mapped_data["id"] = mapped_data.pop("_id")
            return Student(**mapped_data)
        else:
            logger.warning(f"Student {student_internal_id} not found for teacher {teacher_id}."); return None # Modified log
    except Exception as e:
        logger.error(f"Error getting student: {e}", exc_info=True); return None

async def get_all_students(
    teacher_id: str, # <<< ADDED: Make teacher_id mandatory
    external_student_id: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    year_group: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    include_deleted: bool = False,
    session=None
) -> List[Student]:
    collection = _get_collection(STUDENT_COLLECTION); students_list: List[Student] = []
    if collection is None: return students_list
    filter_query = soft_delete_filter(include_deleted)
    filter_query["teacher_id"] = teacher_id # <<< ADDED: Filter by teacher_id
    if external_student_id is not None: filter_query["external_student_id"] = external_student_id
    if first_name is not None: filter_query["first_name"] = {"$regex": f"^{re.escape(first_name)}$", "$options": "i"}
    if last_name is not None: filter_query["last_name"] = {"$regex": f"^{re.escape(last_name)}$", "$options": "i"}
    if year_group is not None: filter_query["year_group"] = year_group
    logger.info(f"Getting all students filter={filter_query} skip={skip} limit={limit}")
    try:
        cursor = collection.find(filter_query, session=session).skip(skip).limit(limit)
        async for doc in cursor:
            try:
                mapped_data = {**doc}
                if "_id" in mapped_data:
                    mapped_data["id"] = mapped_data.pop("_id") # Rename key
                else:
                    logger.warning(f"Student document missing '_id': {doc}")
                    continue # Skip this document if it has no _id
                student_instance = Student(**mapped_data)
                students_list.append(student_instance)
            except Exception as validation_err:
                doc_id_for_log = doc.get('_id', 'UNKNOWN_ID') # Use original doc for logging ID
                logger.error(f"Pydantic validation failed for student doc {doc_id_for_log}: {validation_err}", exc_info=True) # Add traceback for validation errors
    except Exception as e:
        logger.error(f"Error getting all students during DB query: {e}", exc_info=True)
    return students_list

@with_transaction
async def update_student(student_internal_id: uuid.UUID, student_in: StudentUpdate, session=None) -> Optional[Student]:
    collection = _get_collection(STUDENT_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None
    update_data = student_in.model_dump(exclude_unset=True)
    update_data.pop("_id", None); update_data.pop("id", None); update_data.pop("created_at", None); update_data.pop("deleted_at", None)
    if "external_student_id" in update_data and update_data["external_student_id"] == "": update_data["external_student_id"] = None
    if not update_data: logger.warning(f"No update data provided for student {student_internal_id}"); return await get_student_by_id(student_internal_id, include_deleted=False, session=session)
    update_data["updated_at"] = now; logger.info(f"Updating student {student_internal_id}")
    query_filter = {"_id": student_internal_id, "deleted_at": None} # Query by _id
    try:
        updated_doc = await collection.find_one_and_update( query_filter, {"$set": update_data}, return_document=ReturnDocument.AFTER, session=session)
        if updated_doc:
            mapped_data = {**updated_doc}
            if "_id" in mapped_data: mapped_data["id"] = mapped_data.pop("_id")
            return Student(**mapped_data)
        else:
            logger.warning(f"Student {student_internal_id} not found or already deleted for update."); return None
    except DuplicateKeyError:
        ext_id = update_data.get('external_student_id')
        logger.warning(f"Duplicate external_student_id on update: '{ext_id}' for student {student_internal_id}")
        return None # Or raise a specific exception
    except Exception as e:
        logger.error(f"Error during student update operation for {student_internal_id}: {e}", exc_info=True); return None

@with_transaction
async def delete_student(student_internal_id: uuid.UUID, hard_delete: bool = False, session=None) -> bool:
    collection = _get_collection(STUDENT_COLLECTION)
    if collection is None: return False
    logger.info(f"{'Hard' if hard_delete else 'Soft'} deleting student {student_internal_id}")
    count = 0
    try:
        if hard_delete: result = await collection.delete_one({"_id": student_internal_id}, session=session); count = result.deleted_count # Query by _id
        else:
            now = datetime.now(timezone.utc)
            result = await collection.update_one({"_id": student_internal_id, "deleted_at": None},{"$set": {"deleted_at": now, "updated_at": now}}, session=session); count = result.modified_count # Query by _id
    except Exception as e: logger.error(f"Error deleting student: {e}", exc_info=True); return False
    if count == 1: return True
    else: logger.warning(f"Student {student_internal_id} not found or already deleted."); return False


# --- Assignment CRUD Functions (Keep existing) ---
@with_transaction
async def create_assignment(assignment_in: AssignmentCreate, session=None) -> Optional[Assignment]:
    collection = _get_collection(ASSIGNMENT_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None
    assignment_id = uuid.uuid4()
    assignment_doc = assignment_in.model_dump(); assignment_doc["_id"] = assignment_id
    assignment_doc["created_at"] = now; assignment_doc["updated_at"] = now; assignment_doc["deleted_at"] = None
    logger.info(f"Inserting assignment: {assignment_doc['_id']}")
    try: inserted_result = await collection.insert_one(assignment_doc, session=session)
    except Exception as e: logger.error(f"Error inserting assignment: {e}", exc_info=True); return None
    if inserted_result.acknowledged: created_doc = await collection.find_one({"_id": assignment_id}, session=session)
    else: logger.error(f"Insert assignment not acknowledged: {assignment_id}"); return None
    if created_doc: return Assignment(**created_doc)
    else: logger.error(f"Failed retrieve assignment post-insert: {assignment_id}"); return None

async def get_assignment_by_id(assignment_id: uuid.UUID, include_deleted: bool = False, session=None) -> Optional[Assignment]:
    collection = _get_collection(ASSIGNMENT_COLLECTION);
    if collection is None: return None
    logger.info(f"Getting assignment: {assignment_id}")
    query = {"_id": assignment_id}; query.update(soft_delete_filter(include_deleted))
    try: assignment_doc = await collection.find_one(query, session=session)
    except Exception as e: logger.error(f"Error getting assignment: {e}", exc_info=True); return None
    if assignment_doc: return Assignment(**assignment_doc)
    else: logger.warning(f"Assignment {assignment_id} not found."); return None

async def get_all_assignments( class_group_id: Optional[uuid.UUID] = None, skip: int = 0, limit: int = 100, include_deleted: bool = False, session=None) -> List[Assignment]:
    collection = _get_collection(ASSIGNMENT_COLLECTION); assignments_list: List[Assignment] = []
    if collection is None: return assignments_list
    filter_query = soft_delete_filter(include_deleted)
    if class_group_id: filter_query["class_group_id"] = class_group_id
    logger.info(f"Getting all assignments filter={filter_query} skip={skip} limit={limit}")
    try:
        cursor = collection.find(filter_query, session=session).skip(skip).limit(limit)
        async for doc in cursor:
            try:
                mapped_data = {**doc}
                if "_id" in mapped_data: mapped_data["id"] = mapped_data.pop("_id")
                else: logger.warning(f"Assignment doc missing '_id': {doc}"); continue
                assignments_list.append(Assignment(**mapped_data))
            except Exception as validation_err: logger.error(f"Pydantic validation failed for assignment doc {doc.get('_id', 'UNKNOWN')}: {validation_err}")
    except Exception as e: logger.error(f"Error getting all assignments: {e}", exc_info=True)
    return assignments_list

@with_transaction
async def update_assignment(assignment_id: uuid.UUID, assignment_in: AssignmentUpdate, session=None) -> Optional[Assignment]:
    collection = _get_collection(ASSIGNMENT_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None
    update_data = assignment_in.model_dump(exclude_unset=True)
    update_data.pop("_id", None); update_data.pop("id", None); update_data.pop("created_at", None); update_data.pop("class_group_id", None); update_data.pop("deleted_at", None)
    if not update_data: logger.warning(f"No update data for assignment {assignment_id}"); return await get_assignment_by_id(assignment_id, include_deleted=False, session=session)
    update_data["updated_at"] = now; logger.info(f"Updating assignment {assignment_id}")
    query_filter = {"_id": assignment_id, "deleted_at": None}
    try:
        updated_doc = await collection.find_one_and_update( query_filter, {"$set": update_data}, return_document=ReturnDocument.AFTER, session=session)
        if updated_doc: return Assignment(**updated_doc)
        else: logger.warning(f"Assignment {assignment_id} not found or already deleted for update."); return None
    except Exception as e: logger.error(f"Error during assignment update operation: {e}", exc_info=True); return None

@with_transaction
async def delete_assignment(assignment_id: uuid.UUID, hard_delete: bool = False, session=None) -> bool:
    collection = _get_collection(ASSIGNMENT_COLLECTION)
    if collection is None: return False
    logger.info(f"{'Hard' if hard_delete else 'Soft'} deleting assignment {assignment_id}")
    count = 0
    try:
        if hard_delete: result = await collection.delete_one({"_id": assignment_id}, session=session); count = result.deleted_count
        else:
            now = datetime.now(timezone.utc)
            result = await collection.update_one({"_id": assignment_id, "deleted_at": None},{"$set": {"deleted_at": now, "updated_at": now}}, session=session); count = result.modified_count
    except Exception as e: logger.error(f"Error deleting assignment: {e}", exc_info=True); return False
    if count == 1: return True
    else: logger.warning(f"Assignment {assignment_id} not found or already deleted."); return False


# --- Document CRUD Functions (Keep existing) ---
# @with_transaction # Keep transaction commented out if needed for collection creation
async def create_document(document_in: DocumentCreate, session=None) -> Optional[Document]:
    collection = _get_collection(DOCUMENT_COLLECTION)
    if collection is None: return None
    document_id = uuid.uuid4()
    now = datetime.now(timezone.utc); doc_dict = document_in.model_dump()
    if isinstance(doc_dict.get("status"), DocumentStatus): doc_dict["status"] = doc_dict["status"].value
    if isinstance(doc_dict.get("file_type"), FileType): doc_dict["file_type"] = doc_dict["file_type"].value
    doc = doc_dict
    # Explicitly add teacher_id from the input model
    if hasattr(document_in, 'teacher_id') and document_in.teacher_id:
        doc["teacher_id"] = document_in.teacher_id
    doc["_id"] = document_id; doc["created_at"] = now; doc["updated_at"] = now; doc["deleted_at"] = None
    logger.info(f"Inserting document metadata: {doc['_id']}")
    try:
        inserted_result = await collection.insert_one(doc, session=session)
        if inserted_result.acknowledged: created_doc = await collection.find_one({"_id": document_id}, session=session)
        else: logger.error(f"Insert document not acknowledged: {document_id}"); return None
        if created_doc: return Document(**created_doc) # Assumes schema handles alias
        else: logger.error(f"Failed retrieve document post-insert: {document_id}"); return None
    except Exception as e: logger.error(f"Error during document insertion: {e}", exc_info=True); return None

async def get_document_by_id(
    document_id: uuid.UUID,
    teacher_id: str, # <<< ADDED: Make teacher_id mandatory
    include_deleted: bool = False,
    session=None
) -> Optional[Document]:
    collection = _get_collection(DOCUMENT_COLLECTION)
    if collection is None: return None
    logger.info(f"Getting document: {document_id} for teacher: {teacher_id}") # Update log
    query = {"_id": document_id, "teacher_id": teacher_id}; # <<< MODIFIED: Add teacher_id to query
    query.update(soft_delete_filter(include_deleted)) # Query by _id
    try: doc = await collection.find_one(query, session=session)
    except Exception as e: logger.error(f"Error getting document: {e}", exc_info=True); return None
    if doc: return Document(**doc) # Assumes schema handles alias
    else: logger.warning(f"Document {document_id} not found."); return None

async def get_all_documents(
    teacher_id: str, # <<< ADDED: Make teacher_id mandatory
    student_id: Optional[uuid.UUID] = None,
    assignment_id: Optional[uuid.UUID] = None,
    status: Optional[DocumentStatus] = None,
    skip: int = 0,
    limit: int = 100,
    include_deleted: bool = False,
    sort_by: Optional[str] = None, # NEW: Field to sort by (e.g., "upload_timestamp")
    sort_order: int = -1,        # NEW: 1 for asc, -1 for desc (default desc)
    session=None
) -> List[Document]:
    collection = _get_collection(DOCUMENT_COLLECTION)
    documents_list: List[Document] = []
    if collection is None: return documents_list

    filter_query = soft_delete_filter(include_deleted)
    filter_query["teacher_id"] = teacher_id # <<< ADDED: Filter by teacher_id
    if student_id: filter_query["student_id"] = student_id
    if assignment_id: filter_query["assignment_id"] = assignment_id
    if status: filter_query["status"] = status.value # Filter DB by enum value

    logger.info(f"Getting all documents filter={filter_query} sort_by={sort_by} sort_order={sort_order} skip={skip} limit={limit}")

    try:
        cursor = collection.find(filter_query, session=session)

        # --- NEW: Apply Sorting ---
        if sort_by:
            # Map 'id' to '_id' for sorting if necessary
            db_sort_field = "_id" if sort_by == "id" else sort_by
            sort_criteria = [(db_sort_field, sort_order)]
            logger.debug(f"Applying sort criteria: {sort_criteria}")
            cursor = cursor.sort(sort_criteria)
        # --- END NEW Sorting ---

        cursor = cursor.skip(skip).limit(limit) # Apply skip/limit after sorting

        async for doc in cursor:
            try:
                mapped_data = {**doc}
                if "_id" in mapped_data: mapped_data["id"] = mapped_data.pop("_id")
                else: logger.warning(f"Document doc missing '_id': {doc}"); continue
                documents_list.append(Document(**mapped_data))
            except Exception as validation_err: logger.error(f"Pydantic validation failed for document doc {doc.get('_id', 'UNKNOWN')}: {validation_err}")
    except Exception as e: logger.error(f"Error getting all documents: {e}", exc_info=True)
    return documents_list

@with_transaction
async def update_document_status(
    document_id: uuid.UUID,
    status: DocumentStatus,
    character_count: Optional[int] = None, # New optional parameter
    word_count: Optional[int] = None,      # New optional parameter
    session=None
) -> Optional[Document]:
    collection = _get_collection(DOCUMENT_COLLECTION)
    if collection is None: return None
    now = datetime.now(timezone.utc)
    # <<< START EDIT: Build update_data dictionary >>>
    update_data = {
        "status": status.value, # Store enum value
        "updated_at": now
    }
    if character_count is not None:
        update_data["character_count"] = character_count
        logger.info(f"Including character_count={character_count} in update for document {document_id}")
    if word_count is not None:
        update_data["word_count"] = word_count
        logger.info(f"Including word_count={word_count} in update for document {document_id}")
    # <<< END EDIT >>>

    logger.info(f"Updating document {document_id} status to {status.value} and counts if provided.") # Updated log
    query_filter = {"_id": document_id, "deleted_at": None} # Query by _id

    # <<< START EDIT: Add logging before DB call >>>
    logger.debug(f"Attempting find_one_and_update for doc {document_id} with $set payload: {update_data}")
    # <<< END EDIT >>>

    try:
        # <<< START EDIT: Use update_data dictionary in $set >>> # This comment is from previous edits
        updated_doc = await collection.find_one_and_update(
            query_filter,
            {"$set": update_data}, # Use the built dictionary
            return_document=ReturnDocument.AFTER,
            session=session
        )
        # <<< END EDIT >>>
        if updated_doc: return Document(**updated_doc) # Assumes schema handles alias
        else: logger.warning(f"Document {document_id} not found or already deleted for status/count update."); return None
    except Exception as e: logger.error(f"Error updating document status/counts for ID {document_id}: {e}", exc_info=True); return None

@with_transaction
async def delete_document(document_id: uuid.UUID, teacher_id: str, session=None) -> bool: # ADDED teacher_id
    """
    Performs deletion of a document and its associated data (blob, result).
    Checks ownership using teacher_id before proceeding.
    Performs a SOFT delete on the document record itself.

    Args:
        document_id: UUID of the document to delete.
        teacher_id: Kinde ID of the user attempting deletion (for authorization).
        session: Optional database session for transactions (REMOVED - no longer used here).

    Returns:
        True if deletion (including soft delete of document) was successful, False otherwise.
    """
    collection = _get_collection(DOCUMENT_COLLECTION)
    if collection is None:
        return False
    now = datetime.now(timezone.utc)

    # Fetch document first to check ownership and get blob path, even if soft-deleted
    document = await get_document_by_id(
        document_id=document_id,
        teacher_id=teacher_id,
        include_deleted=True, # Fetch even if already soft-deleted
        session=None # REMOVED session
    )
    if not document:
        logger.warning(f"Document {document_id} not found or not owned by teacher {teacher_id} during delete attempt.")
        return False # Not found or not authorized

    # If already soft-deleted, log and return True (idempotency)
    if document.is_deleted: # CHANGED check from deleted_at to is_deleted
        logger.info(f"Document {document_id} is already soft-deleted (is_deleted=True). Delete operation considered successful.") # Updated log
        return True

    blob_path_to_delete = document.storage_blob_path
    result_to_delete = await get_result_by_document_id(
        document_id=document_id,
        include_deleted=True, # Also fetch associated result even if soft-deleted
        session=None # REMOVED session
    )

    logger.info(f"Attempting delete for document {document_id} owned by {teacher_id}. Blob: {blob_path_to_delete}. Result ID: {getattr(result_to_delete, 'id', 'None')}.")

    # --- REMOVED internal try...except block --- 

    # --- Delete Blob (Propagate errors) ---
    if blob_path_to_delete:
        blob_deleted = await delete_blob(blob_path_to_delete)
        if not blob_deleted:
            logger.error(f"delete_blob failed for {blob_path_to_delete}. This might indicate an issue but delete process continues.")
            # Allow continuing, but log clearly
        else:
            logger.info(f"Successfully deleted blob {blob_path_to_delete} for document {document_id}.")
    else:
        logger.warning(f"No storage_blob_path found for document {document_id}. Skipping blob deletion.")

    # --- Delete Result (Propagate errors) ---
    if result_to_delete:
        result_deleted = await delete_result(result_id=result_to_delete.id, session=None)
        if not result_deleted:
            logger.error(f"delete_result failed for {result_to_delete.id}. This might indicate an issue but delete process continues.")
            # Allow continuing, but log clearly
        else:
            logger.info(f"Successfully deleted result {result_to_delete.id} for document {document_id}.")

    # --- Soft Delete Document (Propagate errors) ---
    result = await collection.update_one(
        # OLD Filter: {"_id": document_id, "is_deleted": False},
        # NEW Filter: Match if is_deleted is not True (handles False, null, missing)
        {"_id": document_id, "is_deleted": {"$ne": True}}, 
        {"$set": {"is_deleted": True, "updated_at": now}},
        session=None
    )
    count = result.modified_count

    if count == 1:
        logger.info(f"Successfully soft-deleted document {document_id} (set is_deleted=True)")
        delete_success = True
    else: # count == 0
        logger.warning(
            f"Document {document_id} soft-delete update modified 0 records. "
            f"Assuming already deleted or gone (idempotent success)."
        )
        delete_success = True # Treat as success for idempotency

    # Log final intended return value (still useful)
    logger.critical(f"!!! FINAL INTENDED RETURN VALUE for delete_document({document_id}): {delete_success} (Type: {type(delete_success)}) ")
    return delete_success # Let any exceptions from await calls above propagate

# --- Optional: Add logging to get_result_by_document_id ---
async def get_result_by_document_id(document_id: uuid.UUID, include_deleted: bool = False, session=None) -> Optional[Result]:
    collection = _get_collection(RESULT_COLLECTION)
    if collection is None: return None
    logger.info(f"Getting result for document: {document_id}")
    query = {"document_id": document_id}; query.update(soft_delete_filter(include_deleted))
    try:
        doc = await collection.find_one(query, session=session)
        if doc:
            logger.debug(f"Raw data fetched from DB for doc {document_id}: {doc}") # Log raw data
            try:
                # --- Use model_validate ---
                validated_result = Result.model_validate(doc)
                # --- End change ---
                logger.debug(f"Validated Result object for doc {document_id} has paragraph_results: {'Yes' if validated_result.paragraph_results else 'No'}")
                return validated_result
            except Exception as pydantic_err:
                 logger.error(f"Pydantic validation failed for result fetched for doc {document_id}: {pydantic_err}", exc_info=True)
                 return None # Failed validation
        else:
            logger.info(f"Result for document {document_id} not found.");
            return None
    except Exception as e:
        logger.error(f"Error getting result by doc id {document_id}: {e}", exc_info=True);
        return None
# --- End optional logging ---

# <<< START NEW FUNCTION: create_result >>>
# @with_transaction # Decide if transactions are needed for single insert
async def create_result(result_in: ResultCreate, session=None) -> Optional[Result]:
    """
    Creates a new result record in the database, typically with a PENDING status.

    Args:
        result_in: Pydantic model containing result data to create.
        session: Optional Motor session for transaction management.

    Returns:
        The created Result object or None if creation failed.
    """
    collection = _get_collection(RESULT_COLLECTION)
    if collection is None:
        logger.error("Failed to get results collection for create_result")
        return None

    now = datetime.now(timezone.utc)
    new_result_id = uuid.uuid4()

    # Prepare the document dictionary from the input model
    result_doc = result_in.model_dump(exclude_unset=True) # Start with provided data

    # Set mandatory fields
    result_doc["_id"] = new_result_id
    result_doc["created_at"] = now
    result_doc["updated_at"] = now
    result_doc["deleted_at"] = None # Ensure soft delete field is initialized

    # Set default status if not provided in result_in (should usually be PENDING)
    if "status" not in result_doc:
        result_doc["status"] = ResultStatus.PENDING.value
    elif isinstance(result_doc["status"], ResultStatus): # Convert Enum to value if passed
        result_doc["status"] = result_doc["status"].value

    # Ensure other fields expected by Result model have defaults if not in ResultCreate
    # (e.g., score, label, ai_generated, human_generated, paragraph_results might be None initially)
    result_doc.setdefault("score", None)
    result_doc.setdefault("label", None)
    result_doc.setdefault("ai_generated", None)
    result_doc.setdefault("human_generated", None)
    result_doc.setdefault("paragraph_results", None)


    logger.info(f"Attempting to insert result with internal ID: {new_result_id} for document: {result_doc.get('document_id')}")

    try:
        inserted_result = await collection.insert_one(result_doc, session=session)
        if inserted_result.acknowledged:
            # Fetch the newly created document to return the full Result model
            created_doc = await collection.find_one({"_id": new_result_id}, session=session)
            if created_doc:
                return Result(**created_doc) # Validate and return the full model
            else:
                logger.error(f"Failed to retrieve result post-insert: {new_result_id}")
                return None
        else:
            logger.error(f"Insert result not acknowledged: {new_result_id}")
            return None
    except Exception as e:
        logger.error(f"Error inserting result for document {result_doc.get('document_id')}: {e}", exc_info=True)
        return None
# <<< END NEW FUNCTION: create_result >>>

@with_transaction
async def update_result(
    result_id: uuid.UUID,
    update_data: Dict[str, Any], # Pass update data as a dictionary
    session=None
) -> Optional[Result]:
    """
    Updates an existing result record by its ID.

    Args:
        result_id: The UUID of the result to update.
        update_data: A dictionary containing the fields to update.
        session: Optional MongoDB session for transactions.

    Returns:
        The updated Result object, or None if not found or on error.
    """
    collection = _get_collection(RESULT_COLLECTION)
    now = datetime.now(timezone.utc)
    if collection is None:
        logger.error("Result collection not found during update.")
        return None

    # Ensure _id is not in update data and add updated_at timestamp
    update_data.pop("_id", None)
    update_data.pop("id", None)
    update_data.pop("created_at", None) # Don't allow updating creation time
    update_data.pop("document_id", None) # Don't allow changing the linked document
    update_data.pop("teacher_id", None) # Don't allow changing the teacher ID here

    # Convert enums to their values if necessary (e.g., ResultStatus)
    if "status" in update_data and isinstance(update_data["status"], ResultStatus):
        update_data["status"] = update_data["status"].value

    if not update_data:
        logger.warning(f"No valid update data provided for result {result_id}. Fetching current.")
        # If no fields left to update, maybe just return the current object
        return await get_result_by_id(result_id=result_id, session=session) # Assuming get_result_by_id exists

    update_data["updated_at"] = now

    logger.info(f"Attempting to update result {result_id} with data: {update_data}")

    # Find and update the non-deleted result
    query_filter = {"_id": result_id, "is_deleted": {"$ne": True}}
    update_operation = {"$set": update_data}

    try:
        updated_doc = await collection.find_one_and_update(
            query_filter,
            update_operation,
            return_document=ReturnDocument.AFTER,
            session=session
        )

        if updated_doc:
            logger.info(f"Successfully updated result {result_id}")
            # Validate and return the updated result
            try:
                return Result(**updated_doc)
            except ValidationError as e:
                logger.error(f"Validation error for updated result {result_id}: {e}", exc_info=True)
                return None # Or raise an internal error
        else:
            logger.warning(f"Result {result_id} not found or already deleted, cannot update.")
            return None
    except Exception as e:
        logger.error(f"Error updating result {result_id}: {e}", exc_info=True)
        return None

async def get_dashboard_stats(current_user_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate dashboard statistics for the given teacher based on Kinde payload.
    Finds the internal teacher ID first.
    """
    teacher_kinde_id = current_user_payload.get("sub")
    if not teacher_kinde_id:
        logger.warning("get_dashboard_stats called without teacher Kinde ID (sub) in payload.")
        return {'totalDocs': 0, 'avgScore': None, 'flaggedRecent': 0, 'pending': 0}

    # +++ ADDED Logging +++
    logger.info(f"Calculating dashboard stats for teacher kinde_id: {teacher_kinde_id}")
    # --- END Logging ---

    try:
        # 1. Find the internal teacher ObjectId using the Kinde ID
        teacher = await get_teacher_by_kinde_id(teacher_kinde_id)
        if not teacher:
             # +++ ADDED Logging +++
            logger.warning(f"No teacher found in DB for kinde_id: {teacher_kinde_id}")
             # --- END Logging ---
            return {'totalDocs': 0, 'avgScore': None, 'flaggedRecent': 0, 'pending': 0}

        teacher_internal_id = teacher.id # This is the internal UUID
        # +++ ADDED Logging +++
        logger.debug(f"Found internal teacher id: {teacher_internal_id} for kinde_id: {teacher_kinde_id}")
        # --- END Logging ---

        # 2. Get Collections
        docs_collection = _get_collection(DOCUMENT_COLLECTION)
        results_collection = _get_collection(RESULT_COLLECTION)
        # FIX: Explicitly check against None
        if docs_collection is None or results_collection is None:
            logger.error("Could not get documents or results collection for dashboard stats.")
            return {'totalDocs': 0, 'avgScore': None, 'flaggedRecent': 0, 'pending': 0}

        # 3. Perform Aggregations (using the internal teacher_internal_id)
        # Total Documents
        total_docs = await docs_collection.count_documents({"teacher_id": teacher_kinde_id})
        logger.debug(f"[Stats] Total docs query found: {total_docs}")

        # Average Score (from Results where status is COMPLETED)
        # Note: We use teacher_kinde_id here as it's on the result record directly
        avg_score_pipeline = [
            {"$match": {"teacher_id": teacher_kinde_id, "status": ResultStatus.COMPLETED.value, "score": {"$ne": None}}},
            {"$group": {"_id": None, "avgScore": {"$avg": "$score"}}}
        ]
        avg_score_result = await results_collection.aggregate(avg_score_pipeline).to_list(length=1)
        avg_score = avg_score_result[0]['avgScore'] if avg_score_result else None
        logger.debug(f"[Stats] Avg score query result: {avg_score}")

        # Flagged Recently (Documents with score >= 0.8 in last 7 days)
        # Requires joining Documents and Results or querying Results directly
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        flagged_recent_pipeline = [
            {"$match": {
                "teacher_id": teacher_kinde_id,
                "status": ResultStatus.COMPLETED.value,
                "score": {"$gte": 0.8},
                "updated_at": {"$gte": seven_days_ago}
            }},
            {"$count": "count"}
        ]
        flagged_recent_result = await results_collection.aggregate(flagged_recent_pipeline).to_list(length=1)
        flagged_recent = flagged_recent_result[0]['count'] if flagged_recent_result else 0
        logger.debug(f"[Stats] Flagged recent query result: {flagged_recent}")

        # Pending/Processing Documents (based on Document status)
        pending_statuses = [DocumentStatus.QUEUED.value, DocumentStatus.PROCESSING.value]
        pending = await docs_collection.count_documents({"teacher_id": teacher_kinde_id, "status": {"$in": pending_statuses}})
        logger.debug(f"[Stats] Pending query result: {pending}")

        # 4. Assemble Results
        stats = {
            'totalDocs': total_docs,
            'avgScore': avg_score,
            'flaggedRecent': flagged_recent,
            'pending': pending
        }
        # +++ ADDED Logging +++
        logger.info(f"Dashboard stats calculated for teacher {teacher_kinde_id}: {stats}")
        # --- END Logging ---
        return stats

    except Exception as e:
        logger.error(f"Error calculating dashboard stats for teacher {teacher_kinde_id}: {str(e)}", exc_info=True)
        # Return default/empty stats on error to prevent frontend crash
        return {'totalDocs': 0, 'avgScore': None, 'flaggedRecent': 0, 'pending': 0}

async def get_score_distribution(current_user_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate the distribution of document scores for the given teacher based on Kinde payload.
    Finds the internal teacher ID first.
    """
    teacher_kinde_id = current_user_payload.get("sub")
    if not teacher_kinde_id:
        logger.warning("get_score_distribution called without teacher Kinde ID (sub) in payload.")
        return {"distribution": []}

    # +++ ADDED Logging +++
    logger.info(f"Calculating score distribution for teacher kinde_id: {teacher_kinde_id}")
    # --- END Logging ---

    try:
        # 1. Find the internal teacher ObjectId using the Kinde ID (Optional - could query results directly)
        # teacher = await get_teacher_by_kinde_id(teacher_kinde_id)
        # if not teacher:
        #     logger.warning(f"No teacher found in DB for kinde_id: {teacher_kinde_id} for score distribution")
        #     return {"distribution": []}
        # teacher_internal_id = teacher.id
        # logger.debug(f"Found internal teacher id: {teacher_internal_id} for score distribution calculation")

        # 2. Get Results Collection
        results_collection = _get_collection(RESULT_COLLECTION)
        # FIX: Explicitly check against None
        if results_collection is None:
            logger.error("Could not get results collection for score distribution.")
            return {"distribution": []}

        # 3. Define Score Ranges and Aggregation Pipeline
        # Use teacher_kinde_id as it exists on the result document
        pipeline = [
            {
                "$match": {
                    "teacher_id": teacher_kinde_id,
                    "status": ResultStatus.COMPLETED.value,
                    "score": {"$ne": None} # Exclude documents without a score
                }
            },
            # --- START REPLACEMENT: Use $facet instead of $bucket ---
            {
                "$facet": {
                    "0-20": [
                        { "$match": { "score": { "$gte": 0, "$lte": 0.2 } } },
                        { "$count": "count" }
                    ],
                    "21-40": [
                        { "$match": { "score": { "$gt": 0.2, "$lte": 0.4 } } },
                        { "$count": "count" }
                    ],
                    "41-60": [
                        { "$match": { "score": { "$gt": 0.4, "$lte": 0.6 } } },
                        { "$count": "count" }
                    ],
                    "61-80": [
                        { "$match": { "score": { "$gt": 0.6, "$lte": 0.8 } } },
                        { "$count": "count" }
                    ],
                    "81-100": [
                        { "$match": { "score": { "$gt": 0.8, "$lte": 1.0 } } }, # Adjusted range slightly for edge cases
                        { "$count": "count" }
                    ]
                }
            },
            # Reshape the $facet output to the desired format [{range: "...", count: ...}]
            {
                "$project": {
                    "distribution": [
                        { "range": "0-20", "count": { "$ifNull": [ { "$arrayElemAt": ["$0-20.count", 0] }, 0 ] } },
                        { "range": "21-40", "count": { "$ifNull": [ { "$arrayElemAt": ["$21-40.count", 0] }, 0 ] } },
                        { "range": "41-60", "count": { "$ifNull": [ { "$arrayElemAt": ["$41-60.count", 0] }, 0 ] } },
                        { "range": "61-80", "count": { "$ifNull": [ { "$arrayElemAt": ["$61-80.count", 0] }, 0 ] } },
                        { "range": "81-100", "count": { "$ifNull": [ { "$arrayElemAt": ["$81-100.count", 0] }, 0 ] } }
                    ]
                }
            },
            # Extract the distribution array from the single document result
            {
                "$unwind": "$distribution"
            },
            {
                "$replaceRoot": { "newRoot": "$distribution" }
            }
            # --- END REPLACEMENT ---
        ]

        # +++ ADDED Logging +++
        logger.debug(f"Score distribution pipeline for {teacher_kinde_id}: {pipeline}")
        # --- END Logging ---

        aggregation_result = await results_collection.aggregate(pipeline).to_list(None)

        # +++ ADDED Logging +++
        logger.debug(f"Raw aggregation result for score distribution: {aggregation_result}")
        # --- END Logging ---

        # 4. Format results, ensuring all ranges are present
        # The new pipeline directly outputs the desired format, so mapping is simplified
        # If the aggregation returns nothing (e.g., no results found), aggregation_result will be empty
        final_distribution = aggregation_result if aggregation_result else [
            {"range": "0-20", "count": 0},
            {"range": "21-40", "count": 0},
            {"range": "41-60", "count": 0},
            {"range": "61-80", "count": 0},
            {"range": "81-100", "count": 0}
        ]

        # +++ ADDED Logging +++
        logger.info(f"Final score distribution for teacher {teacher_kinde_id}: {final_distribution}")
        # --- END Logging ---

        return {"distribution": final_distribution}

    except Exception as e:
        logger.error(f"Error calculating score distribution for teacher {teacher_kinde_id}: {str(e)}", exc_info=True)
        return {"distribution": []} # Return empty on error


async def get_recent_documents(teacher_id: str, limit: int = 4) -> List[Document]:
    """
    Get the most recent documents for a teacher using their Kinde ID.
    Args:
        teacher_id: The teacher's Kinde ID string.
        limit: Maximum number of documents to return.
    Returns:
        List of Document objects.
    """
    # +++ ADDED Logging +++
    logger.info(f"Fetching recent documents for teacher_id: {teacher_id}, limit: {limit}")
    # --- END Logging ---
    try:
        docs_collection = _get_collection(DOCUMENT_COLLECTION)
        # FIX: Explicitly check against None
        if docs_collection is None:
            logger.error("Could not get documents collection for recent documents.")
            return []

        # Use the teacher_id (Kinde ID string) directly for filtering
        # Ensure the index exists in Cosmos DB: { "teacher_id": 1, "upload_timestamp": -1 }
        cursor = docs_collection.find(
            {
                "teacher_id": teacher_id
            }
        ).sort([("upload_timestamp", -1)]).limit(limit)

        docs = await cursor.to_list(length=limit)

        # +++ ADDED Logging +++
        logger.debug(f"Found {len(docs)} raw documents for teacher {teacher_id}.")
        # Example log of one document ID if found
        if docs:
            logger.debug(f"First raw doc example: {docs[0]}")
        # --- END Logging ---

        # Convert to Pydantic models
        # Need to handle potential missing 'ai_score' which might be in the Results collection
        # This currently only returns Document base fields. We might need results.
        # TODO: Enhance this to fetch associated result/score if needed by frontend.
        # For now, return Document model instances.
        documents_list = []
        for doc in docs:
            try:
                # Map Pydantic field names (like id) from DB field names (_id)
                doc['id'] = doc.pop('_id', None)
                documents_list.append(Document(**doc))
            except ValidationError as ve:
                logger.warning(f"Validation error converting document {doc.get('id', 'N/A')} to model: {ve}")
            except Exception as model_ex:
                 logger.error(f"Error converting document {doc.get('id', 'N/A')} to model: {model_ex}")

        # +++ ADDED Logging +++
        logger.info(f"Returning {len(documents_list)} Document objects for teacher {teacher_id}.")
        # --- END Logging ---
        return documents_list

    except Exception as e:
        logger.error(f"Error fetching recent documents for teacher {teacher_id}: {str(e)}", exc_info=True)
        return []

# --- Bulk Operations (Keep existing) ---
@with_transaction
async def bulk_create_schools(schools_in: List[SchoolCreate], session=None) -> List[School]:
    collection = _get_collection(SCHOOL_COLLECTION)
    if collection is None: return []
    now = datetime.now(timezone.utc); school_docs = []; created_schools = []; inserted_ids = []
    for school_in in schools_in:
        school_id = uuid.uuid4(); school_doc = school_in.model_dump()
        school_doc["_id"] = school_id; school_doc["created_at"] = now; school_doc["updated_at"] = now; school_doc["deleted_at"] = None
        school_docs.append(school_doc)
    try:
        result = await collection.insert_many(school_docs, session=session)
        if result.acknowledged:
            inserted_ids = result.inserted_ids
            if inserted_ids:
                cursor = collection.find({"_id": {"$in": inserted_ids}}, session=session)
                async for doc in cursor: created_schools.append(School(**doc)) # Assumes schema handles alias
            logger.info(f"Successfully created {len(created_schools)} schools"); return created_schools
        else: logger.error("Bulk school creation insert_many not acknowledged."); return []
    except Exception as e: logger.error(f"Error during bulk school creation: {e}", exc_info=True); return []

@with_transaction
async def bulk_update_schools(updates: List[Dict[str, Any]], session=None) -> List[School]:
    collection = _get_collection(SCHOOL_COLLECTION)
    if collection is None: return []
    now = datetime.now(timezone.utc); updated_schools = []
    try:
        for update_item in updates:
            school_id = update_item.get("id"); update_model_data = update_item.get("data")
            if not isinstance(school_id, uuid.UUID) or not isinstance(update_model_data, dict):
                logger.warning(f"Skipping invalid item in bulk update: id={school_id}, data_type={type(update_model_data)}")
                continue
            try: update_model = SchoolUpdate.model_validate(update_model_data)
            except Exception as validation_err: logger.warning(f"Skipping item due to validation error for school {school_id}: {validation_err}"); continue

            update_doc = update_model.model_dump(exclude_unset=True)
            update_doc.pop("_id", None); update_doc.pop("id", None); update_doc.pop("created_at", None); update_doc.pop("deleted_at", None)
            if not update_doc: continue
            update_doc["updated_at"] = now
            result = await collection.find_one_and_update(
                {"_id": school_id, "deleted_at": None}, {"$set": update_doc}, # Query by _id
                return_document=ReturnDocument.AFTER, session=session )
            if result: updated_schools.append(School(**result)) # Assumes schema handles alias
            else: logger.warning(f"School {school_id} not found/deleted during bulk update.")
        logger.info(f"Successfully updated {len(updated_schools)} schools"); return updated_schools
    except Exception as e: logger.error(f"Error during bulk school update: {e}", exc_info=True); return []

@with_transaction
async def bulk_delete_schools(school_ids: List[uuid.UUID], hard_delete: bool = False, session=None) -> int:
    collection = _get_collection(SCHOOL_COLLECTION)
    if collection is None or not school_ids: return 0
    deleted_count = 0
    try:
        if hard_delete: result = await collection.delete_many( {"_id": {"$in": school_ids}}, session=session); deleted_count = result.deleted_count # Query by _id
        else: result = await collection.update_many({"_id": {"$in": school_ids}, "deleted_at": None},{"$set": {"deleted_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}},session=session); deleted_count = result.modified_count # Query by _id
        logger.info(f"Successfully {'hard' if hard_delete else 'soft'} deleted {deleted_count} schools"); return deleted_count
    except Exception as e: logger.error(f"Error during bulk school deletion: {e}", exc_info=True); return 0

# --- Advanced Filtering Support (Keep existing) ---
class FilterOperator:
    EQUALS = "$eq"; NOT_EQUALS = "$ne"; GREATER_THAN = "$gt"; LESS_THAN = "$lt"
    GREATER_THAN_EQUALS = "$gte"; LESS_THAN_EQUALS = "$lte"; IN = "$in"; NOT_IN = "$nin"
    EXISTS = "$exists"; REGEX = "$regex"; TEXT = "$text"
def build_filter_query(filters: Dict[str, Any], include_deleted: bool = False) -> Dict[str, Any]:
    query = {}
    for field, value in filters.items():
        if isinstance(value, dict):
            op_filter = {}; mongo_op = None
            for op, op_value in value.items():
                mongo_op = op if op.startswith("$") else getattr(FilterOperator, op.upper(), None)
                if mongo_op: op_filter[mongo_op] = op_value
                else: logger.warning(f"Unknown filter operator '{op}' for field '{field}'. Skipping.")
            if op_filter: query[field] = op_filter
        else: query[field] = value
    query.update(soft_delete_filter(include_deleted))
    return query

# --- Relationship Validation (Keep existing) ---
async def validate_school_teacher_relationship( school_id: uuid.UUID, teacher_id: uuid.UUID, session=None) -> bool:
    teacher = await get_teacher_by_kinde_id(kinde_id=str(teacher_id), include_deleted=False, session=session) # Assuming teacher_id is Kinde ID string
    # Adjust based on how teacher ID is stored/passed
    return teacher is not None and teacher.school_id == school_id # Ensure teacher is not None

async def validate_class_group_relationships( class_group_id: uuid.UUID, teacher_id: uuid.UUID, school_id: uuid.UUID, session=None) -> bool:
    class_group = await get_class_group_by_id(class_group_id, include_deleted=False, session=session)
    if class_group is None: return False
    # Assuming teacher_id passed is the internal UUID (_id) stored in ClassGroup
    # If teacher_id passed is Kinde ID, fetch teacher by Kinde ID first
    # teacher = await get_teacher_by_kinde_id(kinde_id=str(teacher_id), session=session)
    # if teacher is None: return False
    # if not await validate_school_teacher_relationship(school_id, teacher.id, session=session): return False # Validate using internal teacher ID
    # For now, assume teacher_id is the internal UUID
    if not await validate_school_teacher_relationship(school_id, teacher_id, session=session): return False
    return (class_group.teacher_id == teacher_id and class_group.school_id == school_id)

async def validate_student_class_group_relationship( student_id: uuid.UUID, class_group_id: uuid.UUID, session=None) -> bool:
    class_group = await get_class_group_by_id(class_group_id, include_deleted=False, session=session)
    # Ensure class_group.student_ids exists and is a list before checking 'in'
    return class_group is not None and isinstance(class_group.student_ids, list) and student_id in class_group.student_ids

# --- Enhanced Query Functions (Keep existing) ---
async def get_schools_with_filters(
    filters: Dict[str, Any], include_deleted: bool = False, skip: int = 0,
    limit: int = 100, sort_by: Optional[str] = None, sort_order: int = 1, session=None
) -> List[School]:
    collection = _get_collection(SCHOOL_COLLECTION)
    if collection is None: return []
    query = build_filter_query(filters, include_deleted)
    sort_field = "_id" if sort_by == "id" else sort_by
    sort_criteria = [(sort_field, sort_order)] if sort_field else None; schools = []
    try:
        cursor = collection.find(query, session=session)
        if sort_criteria: cursor = cursor.sort(sort_criteria)
        cursor = cursor.skip(skip).limit(limit)
        async for doc in cursor:
            try:
                mapped_data = {**doc}
                if "_id" in mapped_data: mapped_data["id"] = mapped_data.pop("_id")
                schools.append(School(**mapped_data))
            except Exception as validation_err: logger.error(f"Pydantic validation failed for school doc {doc.get('_id', 'UNKNOWN')}: {validation_err}")
        logger.info(f"Retrieved {len(schools)} schools with filters")
        return schools
    except Exception as e: logger.error(f"Error retrieving schools with filters: {e}", exc_info=True); return []

async def get_teachers_by_school(
    school_id: uuid.UUID, include_deleted: bool = False, skip: int = 0,
    limit: int = 100, session=None
) -> List[Teacher]:
    collection = _get_collection(TEACHER_COLLECTION)
    if collection is None: return []
    query = {"school_id": school_id}; query.update(soft_delete_filter(include_deleted))
    teachers = []
    try:
        cursor = collection.find(query, session=session).skip(skip).limit(limit)
        async for doc in cursor:
            try:
                mapped_data = {**doc}
                if "_id" in mapped_data: mapped_data["id"] = mapped_data.pop("_id")
                teachers.append(Teacher(**mapped_data))
            except Exception as validation_err: logger.error(f"Pydantic validation failed for teacher doc {doc.get('_id', 'UNKNOWN')}: {validation_err}")
        logger.info(f"Retrieved {len(teachers)} teachers for school {school_id}")
        return teachers
    except Exception as e: logger.error(f"Error retrieving teachers by school: {e}", exc_info=True); return []

# --- Final Placeholder ---
# (All core entities now have basic CRUD with consistent pattern, applied explicit _id->id mapping for list returns)

# === Batch Operations ===

async def create_batch(*, batch_in: BatchCreate) -> Optional[Batch]:
    """Create a new batch record."""
    collection = _get_collection("batches")
    if collection is None:
        logger.error("Failed to get batches collection")
        return None

    try:
        batch_dict = batch_in.dict()
        batch_dict["_id"] = uuid.uuid4()  # Generate new UUID for the batch
        batch_dict["created_at"] = datetime.now(timezone.utc)
        batch_dict["updated_at"] = batch_dict["created_at"]
        
        result = await collection.insert_one(batch_dict)
        if result.inserted_id:
            return await get_batch_by_id(batch_id=batch_dict["_id"])
        return None
    except Exception as e:
        logger.error(f"Error creating batch: {e}")
        return None

async def get_batch_by_id(*, batch_id: uuid.UUID) -> Optional[Batch]:
    """Get a batch by its ID."""
    collection = _get_collection("batches")
    if collection is None:
        logger.error("Failed to get batches collection")
        return None

    try:
        batch_dict = await collection.find_one({"_id": batch_id})
        if batch_dict:
            return Batch(**batch_dict)
        return None
    except Exception as e:
        logger.error(f"Error getting batch {batch_id}: {e}")
        return None

async def update_batch(*, batch_id: uuid.UUID, batch_in: BatchUpdate) -> Optional[Batch]:
    """Update a batch record."""
    collection = _get_collection("batches")
    if collection is None:
        logger.error("Failed to get batches collection")
        return None

    try:
        update_data = batch_in.dict(exclude_unset=True)
        if not update_data:
            return await get_batch_by_id(batch_id=batch_id)
        
        update_data["updated_at"] = datetime.now(timezone.utc)
        
        result = await collection.update_one(
            {"_id": batch_id},
            {"$set": update_data}
        )
        
        if result.modified_count:
            return await get_batch_by_id(batch_id=batch_id)
        return None
    except Exception as e:
        logger.error(f"Error updating batch {batch_id}: {e}")
        return None

async def get_documents_by_batch_id(*, batch_id: uuid.UUID) -> List[Document]:
    """Get all documents in a batch."""
    collection = _get_collection(DOCUMENT_COLLECTION)
    if collection is None:
        logger.error("Failed to get documents collection")
        return []

    try:
        cursor = collection.find({"batch_id": batch_id})
        documents = []
        async for doc in cursor:
            documents.append(Document(**doc))
        return documents
    except Exception as e:
        logger.error(f"Error getting documents for batch {batch_id}: {e}")
        return []

async def get_batch_status_summary(*, batch_id: uuid.UUID) -> dict:
    """Get a summary of document statuses in a batch."""
    collection = _get_collection(DOCUMENT_COLLECTION)
    if collection is None:
        logger.error("Failed to get documents collection")
        return {}

    try:
        pipeline = [
            {"$match": {"batch_id": batch_id}},
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        cursor = collection.aggregate(pipeline)
        status_counts = {}
        async for result in cursor:
            status_counts[result["_id"]] = result["count"]
        
        return status_counts
    except Exception as e:
        logger.error(f"Error getting status summary for batch {batch_id}: {e}")
        return {}

async def delete_batch(*, batch_id: uuid.UUID) -> bool:
    """Delete a batch and optionally its documents (metadata only)."""
    batch_collection = _get_collection("batches")
    doc_collection = _get_collection(DOCUMENT_COLLECTION)
    if batch_collection is None or doc_collection is None:
        logger.error("Failed to get required collections")
        return False

    try:
        # Delete the batch record
        result = await batch_collection.delete_one({"_id": batch_id})
        if result.deleted_count:
            # Update documents to remove batch_id reference
            await doc_collection.update_many(
                {"batch_id": batch_id},
                {"$unset": {"batch_id": "", "queue_position": ""}}
            )
            return True
        return False
    except Exception as e:
        logger.error(f"Error deleting batch {batch_id}: {e}")
        return False

async def delete_result(result_id: uuid.UUID, session=None) -> bool:
    """
    Delete a result from the database.
    
    Args:
        result_id: UUID of the result to delete
        session: Optional database session
        
    Returns:
        bool: True if result was deleted, False otherwise
    """
    try:
        collection = _get_collection(RESULT_COLLECTION) # FIX: Use _get_collection and correct constant
        if collection is None: return False # Add check
        result = await collection.delete_one({"_id": result_id})
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"Error deleting result {result_id}: {e}")
        return False

async def delete_blob(blob_path: str) -> bool:
    """
    Delete a blob from storage.
    
    Args:
        blob_path: Path of the blob to delete
        
    Returns:
        bool: True if blob was deleted, False otherwise
    """
    try:
        # FIX: Check environment variables first
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        container_name = os.getenv("AZURE_STORAGE_CONTAINER_NAME")

        if not connection_string or not container_name:
            logger.error("Azure Storage connection string or container name not configured.")
            return False

        # Get blob service client
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        
        # Get blob name from path (assuming path might be just the name or full URL)
        # This logic might need adjustment depending on how storage_blob_path is stored
        if '/' in blob_path:
            blob_name = blob_path.split("/")[-1]
        else:
            blob_name = blob_path # Assume it's just the name
        
        # Get blob client and delete
        blob_client = blob_service_client.get_blob_client(
            container=container_name,
            blob=blob_name
        )
        # FIX: Check if blob exists before deleting to avoid errors on retries/cleanup
        if await blob_client.exists():
            await blob_client.delete_blob()
            logger.info(f"Successfully deleted blob {container_name}/{blob_name}")
        else:
            logger.warning(f"Blob {container_name}/{blob_name} not found, skipping deletion.")
        return True
    except ResourceNotFoundError:
        logger.warning(f"Blob {container_name}/{blob_name} not found during deletion attempt.")
        return True # Treat as success if blob is already gone
    except Exception as e:
        logger.error(f"Error deleting blob {blob_path}: {e}", exc_info=True) # Log traceback
        return False

# <<< START EDIT: Add new analytics CRUD function >>>
async def get_usage_stats_for_period(
    teacher_id: str,
    period: str, # 'daily', 'weekly', 'monthly'
    target_date: date_type # Use the aliased date type
) -> Optional[Dict[str, Any]]: # Matches UsageStatsResponse structure
    """
    Aggregates document usage stats (count, characters, words) for a specific teacher
    over a given period (daily, weekly, monthly) based on a target date.

    Args:
        teacher_id: The Kinde ID of the teacher.
        period: The time period ('daily', 'weekly', 'monthly').
        target_date: The date defining the period.

    Returns:
        A dictionary containing the aggregated stats and period info, or None on error.
    """
    collection = _get_collection(DOCUMENT_COLLECTION)
    if collection is None:
        logger.error(f"Failed to get document collection for usage stats (teacher: {teacher_id})")
        return None

    logger.info(f"Calculating usage stats for teacher {teacher_id}, period={period}, target_date={target_date}")

    # --- Calculate Date Range in UTC --- START ---
    start_datetime_utc: Optional[datetime] = None
    end_datetime_utc: Optional[datetime] = None
    start_date_local: Optional[date_type] = None # For response
    end_date_local: Optional[date_type] = None   # For response

    try:
        # Combine target_date with min/max time and make timezone-aware (UTC)
        min_time = datetime.min.time()
        max_time_plus_one = (datetime.combine(target_date, min_time) + timedelta(days=1)).time()

        if period == 'daily':
            start_date_local = target_date
            end_date_local = target_date
            start_datetime_utc = datetime.combine(target_date, min_time, tzinfo=timezone.utc)
            # End date is the beginning of the *next* day, exclusive
            end_datetime_utc = datetime.combine(target_date + timedelta(days=1), min_time, tzinfo=timezone.utc)

        elif period == 'weekly':
            # Monday is 0, Sunday is 6. Calculate start of week (Monday).
            start_of_week = target_date - timedelta(days=target_date.weekday())
            end_of_week = start_of_week + timedelta(days=6)
            start_date_local = start_of_week
            end_date_local = end_of_week
            start_datetime_utc = datetime.combine(start_of_week, min_time, tzinfo=timezone.utc)
            # End date is the beginning of the day *after* the week ends, exclusive
            end_datetime_utc = datetime.combine(end_of_week + timedelta(days=1), min_time, tzinfo=timezone.utc)

        elif period == 'monthly':
            # Get the first and last day of the month
            first_day_of_month = target_date.replace(day=1)
            last_day_of_month = target_date.replace(day=calendar.monthrange(target_date.year, target_date.month)[1])
            start_date_local = first_day_of_month
            end_date_local = last_day_of_month
            start_datetime_utc = datetime.combine(first_day_of_month, min_time, tzinfo=timezone.utc)
            # End date is the beginning of the day *after* the month ends, exclusive
            end_datetime_utc = datetime.combine(last_day_of_month + timedelta(days=1), min_time, tzinfo=timezone.utc)
        else:
            raise ValueError(f"Invalid period specified: {period}")

        logger.debug(f"Calculated UTC range for {teacher_id}, {period}: {start_datetime_utc} to {end_datetime_utc}")

    except Exception as date_err:
        logger.error(f"Error calculating date range for usage stats: {date_err}", exc_info=True)
        return None # Or raise a specific error
    # --- Calculate Date Range in UTC --- END ---

    # --- Aggregation Pipeline --- START ---
    pipeline = [
        {
            '$match': {
                'teacher_id': teacher_id, # Crucial RBAC filter
                'upload_timestamp': {
                    '$gte': start_datetime_utc, # Greater than or equal to start
                    '$lt': end_datetime_utc    # Less than end (exclusive)
                }
            }
        },
        {
            '$group': {
                '_id': None, # Group all matched documents together
                'document_count': {'$sum': 1},
                # Sum counts, treating null/missing as 0
                'total_characters': {'$sum': {'$ifNull': ['$character_count', 0]}},
                'total_words': {'$sum': {'$ifNull': ['$word_count', 0]}}
            }
        }
    ]
    # --- Aggregation Pipeline --- END ---

    try:
        aggregation_result = await collection.aggregate(pipeline).to_list(length=1)
        logger.debug(f"Usage stats aggregation result for {teacher_id}, {period}: {aggregation_result}")

        # --- Process Results --- START ---
        if aggregation_result:
            stats = aggregation_result[0]
            result_payload = {
                "period": period,
                "target_date": target_date,
                "start_date": start_date_local,
                "end_date": end_date_local,
                "document_count": stats.get('document_count', 0),
                "total_characters": stats.get('total_characters', 0),
                "total_words": stats.get('total_words', 0),
                "teacher_id": teacher_id
            }
        else:
            # No documents found in the period for this teacher
            logger.info(f"No documents found for usage stats (teacher: {teacher_id}, period: {period}, target: {target_date})")
            result_payload = {
                "period": period,
                "target_date": target_date,
                "start_date": start_date_local,
                "end_date": end_date_local,
                "document_count": 0,
                "total_characters": 0,
                "total_words": 0,
                "teacher_id": teacher_id
            }
        # --- Process Results --- END ---

        logger.info(f"Successfully retrieved usage stats for {teacher_id}, period={period}: {result_payload}")
        return result_payload

    except Exception as e:
        logger.error(f"Error during usage stats aggregation for teacher {teacher_id}: {e}", exc_info=True)
        return None # Indicate failure
# <<< END EDIT: Add new analytics CRUD function >>> 