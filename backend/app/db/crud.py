# app/db/crud.py

# --- Core Imports ---
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from pymongo.collation import Collation, CollationStrength # Add for case-insensitive aggregation if needed
import uuid
from typing import List, Optional, Dict, Any, TypeVar, Type, Tuple
from datetime import datetime, timezone, timedelta
import logging
import re
from contextlib import asynccontextmanager
from functools import wraps
import asyncio

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
    return {"deleted_at": None}

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

async def get_teacher_by_kinde_id(kinde_id: str, include_deleted: bool = False, session=None) -> Optional[Teacher]:
    """Retrieves a teacher profile using their Kinde ID."""
    collection = _get_collection(TEACHER_COLLECTION);
    if collection is None: return None
    logger.info(f"Getting teacher by kinde_id: {kinde_id}")
    query = {"kinde_id": kinde_id}; query.update(soft_delete_filter(include_deleted))
    try:
        teacher_doc = await collection.find_one(query, session=session)
        if teacher_doc:
            return Teacher(**teacher_doc)
        else:
            logger.warning(f"Teacher with Kinde ID {kinde_id} not found."); return None
    except Exception as e:
        logger.error(f"Error getting teacher by Kinde ID: {e}", exc_info=True); return None

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
        return await get_teacher_by_kinde_id(kinde_id=kinde_id, include_deleted=False, session=session)

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
async def create_student(student_in: StudentCreate, session=None) -> Optional[Student]:
    collection = _get_collection(STUDENT_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None
    internal_id = uuid.uuid4()
    student_doc = student_in.model_dump()
    student_doc["_id"] = internal_id # Use _id for DB
    student_doc["created_at"] = now
    student_doc["updated_at"] = now
    student_doc["deleted_at"] = None
    if student_doc.get("external_student_id") == "": student_doc["external_student_id"] = None
    logger.info(f"Inserting student: {student_doc['_id']}")
    try:
        inserted_result = await collection.insert_one(student_doc, session=session)
        if inserted_result.acknowledged:
            created_doc = await collection.find_one({"_id": internal_id}, session=session)
            if created_doc:
                mapped_data = {**created_doc}
                if "_id" in mapped_data: mapped_data["id"] = mapped_data.pop("_id")
                return Student(**mapped_data)
            else:
                logger.error(f"Failed retrieve student post-insert: {internal_id}"); return None
        else:
            logger.error(f"Insert student not acknowledged: {internal_id}"); return None
    except DuplicateKeyError:
        ext_id = student_doc.get('external_student_id')
        logger.warning(f"Duplicate external_student_id: '{ext_id}' on create.")
        return None
    except Exception as e:
        logger.error(f"Error inserting student: {e}", exc_info=True); return None

async def get_student_by_id(student_internal_id: uuid.UUID, include_deleted: bool = False, session=None) -> Optional[Student]:
    collection = _get_collection(STUDENT_COLLECTION);
    if collection is None: return None
    logger.info(f"Getting student: {student_internal_id}")
    query = {"_id": student_internal_id}; query.update(soft_delete_filter(include_deleted)) # Query by _id
    try:
        student_doc = await collection.find_one(query, session=session)
        if student_doc:
            mapped_data = {**student_doc}
            if "_id" in mapped_data: mapped_data["id"] = mapped_data.pop("_id")
            return Student(**mapped_data)
        else:
            logger.warning(f"Student {student_internal_id} not found."); return None
    except Exception as e:
        logger.error(f"Error getting student: {e}", exc_info=True); return None

async def get_all_students( external_student_id: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None, year_group: Optional[str] = None, skip: int = 0, limit: int = 100, include_deleted: bool = False, session=None) -> List[Student]:
    collection = _get_collection(STUDENT_COLLECTION); students_list: List[Student] = []
    if collection is None: return students_list
    filter_query = soft_delete_filter(include_deleted)
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
    doc = doc_dict; doc["_id"] = document_id; doc["created_at"] = now; doc["updated_at"] = now; doc["deleted_at"] = None
    logger.info(f"Inserting document metadata: {doc['_id']}")
    try:
        inserted_result = await collection.insert_one(doc, session=session)
        if inserted_result.acknowledged: created_doc = await collection.find_one({"_id": document_id}, session=session)
        else: logger.error(f"Insert document not acknowledged: {document_id}"); return None
        if created_doc: return Document(**created_doc) # Assumes schema handles alias
        else: logger.error(f"Failed retrieve document post-insert: {document_id}"); return None
    except Exception as e: logger.error(f"Error during document insertion: {e}", exc_info=True); return None

async def get_document_by_id(document_id: uuid.UUID, include_deleted: bool = False, session=None) -> Optional[Document]:
    collection = _get_collection(DOCUMENT_COLLECTION)
    if collection is None: return None
    logger.info(f"Getting document: {document_id}")
    query = {"_id": document_id}; query.update(soft_delete_filter(include_deleted)) # Query by _id
    try: doc = await collection.find_one(query, session=session)
    except Exception as e: logger.error(f"Error getting document: {e}", exc_info=True); return None
    if doc: return Document(**doc) # Assumes schema handles alias
    else: logger.warning(f"Document {document_id} not found."); return None

async def get_all_documents(
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
async def update_document_status(document_id: uuid.UUID, status: DocumentStatus, session=None) -> Optional[Document]:
    collection = _get_collection(DOCUMENT_COLLECTION)
    if collection is None: return None
    now = datetime.now(timezone.utc)
    update_data = {"status": status.value, "updated_at": now} # Store enum value
    logger.info(f"Updating document {document_id} status to {status.value}")
    query_filter = {"_id": document_id, "deleted_at": None} # Query by _id
    try:
        updated_doc = await collection.find_one_and_update(query_filter, {"$set": update_data}, return_document=ReturnDocument.AFTER, session=session)
        if updated_doc: return Document(**updated_doc) # Assumes schema handles alias
        else: logger.warning(f"Document {document_id} not found or already deleted for status update."); return None
    except Exception as e: logger.error(f"Error updating document status for ID {document_id}: {e}", exc_info=True); return None

@with_transaction
async def delete_document(document_id: uuid.UUID, hard_delete: bool = False, session=None) -> bool:
    collection = _get_collection(DOCUMENT_COLLECTION)
    if collection is None: return False
    logger.info(f"{'Hard' if hard_delete else 'Soft'} deleting document metadata {document_id}")
    count = 0
    try:
        if hard_delete: result = await collection.delete_one({"_id": document_id}, session=session); count = result.deleted_count # Query by _id
        else:
            now = datetime.now(timezone.utc)
            result = await collection.update_one({"_id": document_id, "deleted_at": None},{"$set": {"deleted_at": now, "updated_at": now}}, session=session); count = result.modified_count # Query by _id
    except Exception as e: logger.error(f"Error deleting document metadata: {e}", exc_info=True); return False
    if count == 1: return True
    else: logger.warning(f"Document metadata {document_id} not found or already deleted."); return False

# --- Result CRUD Functions (Keep existing) ---
# @with_transaction # Keep transaction commented out if needed
async def create_result(result_in: ResultCreate, session=None) -> Optional[Result]:
    collection = _get_collection(RESULT_COLLECTION)
    if collection is None: return None
    result_id = uuid.uuid4()
    now = datetime.now(timezone.utc); result_dict = result_in.model_dump()
    if isinstance(result_dict.get("status"), ResultStatus): result_dict["status"] = result_dict["status"].value
    result_doc = result_dict; result_doc["_id"] = result_id; result_doc["created_at"] = now; result_doc["updated_at"] = now; result_doc["deleted_at"] = None
    logger.info(f"Inserting result for document: {result_doc['document_id']}")
    try:
        inserted_result = await collection.insert_one(result_doc, session=session)
        if inserted_result.acknowledged: created_doc = await collection.find_one({"_id": result_id}, session=session)
        else: logger.error(f"Insert result not acknowledged: {result_id}"); return None
        if created_doc: return Result(**created_doc) # Assumes schema handles alias
        else: logger.error(f"Failed retrieve result post-insert: {result_id}"); return None
    except Exception as e: logger.error(f"Error during result insertion: {e}", exc_info=True); return None

async def get_result_by_id(result_id: uuid.UUID, include_deleted: bool = False, session=None) -> Optional[Result]:
    collection = _get_collection(RESULT_COLLECTION)
    if collection is None: return None
    logger.info(f"Getting result: {result_id}")
    query = {"_id": result_id}; query.update(soft_delete_filter(include_deleted)) # Query by _id
    try: doc = await collection.find_one(query, session=session)
    except Exception as e: logger.error(f"Error getting result: {e}", exc_info=True); return None
    if doc: return Result(**doc) # Assumes schema handles alias
    else: logger.warning(f"Result {result_id} not found."); return None

@with_transaction
async def update_result(result_id: uuid.UUID, update_data: Dict[str, Any], session=None) -> Optional[Result]:
    """
    Updates an existing Result record in the database using a raw dictionary.

    Assumes 'paragraph_results' in update_data is already a list of dicts.
    Includes enhanced logging.
    """
    collection = _get_collection(RESULT_COLLECTION)
    if collection is None:
        logger.error("Failed to get results collection for update.")
        return None

    now = datetime.now(timezone.utc)

    # Log the raw data received by the function
    logger.debug(f"crud.update_result received update_data for {result_id}: {update_data}")

    # Prepare the dictionary for the $set operation
    set_payload = {}

    # Copy allowed fields from input update_data to set_payload
    allowed_fields = ["score", "status", "label", "ai_generated", "human_generated", "paragraph_results", "result_timestamp"]
    for field in allowed_fields:
        if field in update_data and update_data[field] is not None:
             # Special handling for status enum
             if field == "status" and isinstance(update_data[field], ResultStatus):
                 set_payload[field] = update_data[field].value # Store the enum value string
             # --- FIX: Check for datetime for result_timestamp ---
             elif field == "result_timestamp" and isinstance(update_data[field], datetime):
                 set_payload[field] = update_data[field] # Store datetime object
             # --- END FIX ---
             else:
                 set_payload[field] = update_data[field]

    # Ensure 'paragraph_results' is a list of dicts if present
    if "paragraph_results" in set_payload:
        if not isinstance(set_payload["paragraph_results"], list) or \
           not all(isinstance(item, dict) for item in set_payload["paragraph_results"]):
            logger.warning(f"Invalid format for 'paragraph_results' in update data for {result_id}. Removing field.")
            set_payload.pop("paragraph_results", None)
        else:
             logger.info(f"Preparing to save {len(set_payload['paragraph_results'])} paragraph results for {result_id}.")

    # Check if there's anything left to update
    if not set_payload:
        logger.warning(f"No valid fields to update for result {result_id}")
        # Return the existing document if no changes were made
        return await get_result_by_id(result_id, include_deleted=False, session=session)

    # Always set updated_at
    set_payload["updated_at"] = now
    # result_timestamp should be included in the incoming update_data if needed

    logger.info(f"Updating result {result_id} with fields: {list(set_payload.keys())}")
    # Log the exact payload for the $set operation
    logger.debug(f"Payload for $set operation for result {result_id}: {set_payload}") # Check this log carefully

    query_filter = {"_id": result_id, "deleted_at": None} # Query by internal _id

    try:
        # Perform the database update
        updated_doc = await collection.find_one_and_update(
            query_filter,
            {"$set": set_payload}, # Use the prepared set_payload dictionary
            return_document=ReturnDocument.AFTER, # Return the document *after* the update
            session=session # Pass the session for transaction atomicity
        )

        # Process the result of the update
        if updated_doc:
            logger.info(f"Successfully updated result {result_id} in DB.")
            logger.debug(f"Raw document returned from find_one_and_update for result {result_id}: {updated_doc}")
            try:
                # --- Use model_validate for potentially better error info ---
                validated_result = Result.model_validate(updated_doc)
                # --- End change ---
                logger.debug(f"Validated Result object for {result_id} has paragraph_results: {'Yes' if validated_result.paragraph_results else 'No'}")
                return validated_result
            except Exception as pydantic_err:
                logger.error(f"Pydantic validation failed for updated result {result_id} from DB: {pydantic_err}", exc_info=True)
                return None # Failed validation
        else:
            logger.warning(f"Result {result_id} not found or already deleted during update attempt.")
            return None
    except Exception as e:
        logger.error(f"Error updating result with ID {result_id}: {e}", exc_info=True)
        return None

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

# --- NEW Dashboard CRUD Functions ---

async def get_dashboard_stats(
    # Add parameters if stats need filtering, e.g., teacher_id, school_id
    session=None
) -> Dict[str, Any]:
    """Calculates various statistics for the dashboard."""
    doc_collection = _get_collection(DOCUMENT_COLLECTION)
    result_collection = _get_collection(RESULT_COLLECTION)
    stats = {
        "totalAssessed": 0,
        "avgScore": None,
        "flaggedRecent": 0,
        "pending": 0
    }
    if doc_collection is None or result_collection is None:
        logger.error("Cannot get dashboard stats: Collection(s) not available.")
        return stats # Return default empty stats

    logger.info("Calculating dashboard stats...")
    try:
        # 1. Total Assessed (Count completed documents/results)
        total_assessed_filter = {
            "status": ResultStatus.COMPLETED.value,
            "deleted_at": None
        }
        stats["totalAssessed"] = await result_collection.count_documents(total_assessed_filter, session=session)

        # 2. Average Score (Aggregation on completed results)
        avg_score_pipeline = [
            {
                "$match": {
                    "status": ResultStatus.COMPLETED.value,
                    "score": {"$ne": None},
                    "deleted_at": None
                }
            },
            {"$group": {"_id": None, "averageScore": {"$avg": "$score"}}}
        ]
        avg_cursor = result_collection.aggregate(avg_score_pipeline, session=session)
        avg_result = await avg_cursor.to_list(length=1)
        if avg_result and "averageScore" in avg_result[0]:
            stats["avgScore"] = avg_result[0]["averageScore"]

        # 3. Flagged Recently (Count results flagged as AI in last 7 days)
        time_threshold = datetime.now(timezone.utc) - timedelta(days=7)
        flagged_filter = {
            "ai_generated": True,
            "result_timestamp": {"$gte": time_threshold},
            "deleted_at": None
        }
        stats["flaggedRecent"] = await result_collection.count_documents(flagged_filter, session=session)

        # 4. Pending/Processing (Count documents in relevant states)
        pending_filter = {
            "status": {"$in": [DocumentStatus.PROCESSING.value, DocumentStatus.QUEUED.value]},
            "deleted_at": None
        }
        stats["pending"] = await doc_collection.count_documents(pending_filter, session=session)

        logger.info(f"Dashboard stats calculated: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Error calculating dashboard stats: {e}", exc_info=True)
        return stats # Return default/partially calculated stats on error


async def get_score_distribution(
    # Add parameters if distribution needs filtering, e.g., teacher_id, date range
    session=None
) -> Dict[str, Any]:
    """
    Calculate the distribution of AI scores across predefined ranges.
    Returns a dictionary containing the distribution and total count.
    """
    collection = _get_collection(RESULT_COLLECTION)  # Changed to RESULT_COLLECTION
    if collection is None:
        logger.error("Failed to get results collection for score distribution")
        return {"distribution": [], "total_documents": 0}

    try:
        # Define the aggregation pipeline
        pipeline = [
            # First match only completed results with scores
            {
                "$match": {
                    "status": ResultStatus.COMPLETED.value,
                    "score": {"$exists": True, "$ne": None},
                    "deleted_at": None
                }
            },
            
            # Add normalized score field
            {
                "$addFields": {
                    "normalized_score": {
                        "$cond": {
                            "if": {"$lt": ["$score", 1]},
                            "then": {"$multiply": ["$score", 100]},
                            "else": "$score"
                        }
                    }
                }
            },
            
            # Add score range field using the normalized score
            {
                "$addFields": {
                    "score_range": {
                        "$switch": {
                            "branches": [
                                {
                                    "case": {
                                        "$and": [
                                            {"$gte": ["$normalized_score", 0]},
                                            {"$lte": ["$normalized_score", 20]}
                                        ]
                                    },
                                    "then": "0-20"
                                },
                                {
                                    "case": {
                                        "$and": [
                                            {"$gte": ["$normalized_score", 21]},
                                            {"$lte": ["$normalized_score", 40]}
                                        ]
                                    },
                                    "then": "21-40"
                                },
                                {
                                    "case": {
                                        "$and": [
                                            {"$gte": ["$normalized_score", 41]},
                                            {"$lte": ["$normalized_score", 60]}
                                        ]
                                    },
                                    "then": "41-60"
                                },
                                {
                                    "case": {
                                        "$and": [
                                            {"$gte": ["$normalized_score", 61]},
                                            {"$lte": ["$normalized_score", 80]}
                                        ]
                                    },
                                    "then": "61-80"
                                },
                                {
                                    "case": {
                                        "$and": [
                                            {"$gte": ["$normalized_score", 81]},
                                            {"$lte": ["$normalized_score", 100]}
                                        ]
                                    },
                                    "then": "81-100"
                                }
                            ],
                            "default": "0-20"
                        }
                    }
                }
            },
            
            # Group by score range and count documents
            {
                "$group": {
                    "_id": "$score_range",
                    "count": {"$sum": 1}
                }
            },
            
            # Project to match expected format
            {
                "$project": {
                    "_id": 0,
                    "range": "$_id",
                    "count": 1
                }
            },
            
            # Sort by range
            {
                "$sort": {
                    "range": 1
                }
            }
        ]

        # Execute the pipeline
        results = []
        async for doc in collection.aggregate(pipeline, session=session):
            results.append(doc)

        # Ensure all ranges are present with at least 0 count
        ranges = ["0-20", "21-40", "41-60", "61-80", "81-100"]
        distribution = {item["range"]: item["count"] for item in results}
        final_distribution = [{"range": r, "count": distribution.get(r, 0)} for r in ranges]

        # Calculate total documents
        total_documents = sum(item["count"] for item in final_distribution)

        return {
            "distribution": final_distribution,
            "total_documents": total_documents
        }

    except Exception as e:
        logger.error(f"Error calculating score distribution: {e}", exc_info=True)
        return {"distribution": [], "total_documents": 0}

# --- END NEW Dashboard CRUD Functions ---

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
 