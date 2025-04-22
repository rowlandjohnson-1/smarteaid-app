# app/db/crud.py

# --- Core Imports ---
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
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
from ..models.school import SchoolCreate, SchoolUpdate, School
# --- Use the updated Teacher models ---
from ..models.teacher import Teacher, TeacherCreate, TeacherUpdate
# ------------------------------------
from ..models.class_group import ClassGroup, ClassGroupCreate, ClassGroupUpdate
from ..models.student import Student, StudentCreate, StudentUpdate
from ..models.assignment import Assignment, AssignmentCreate, AssignmentUpdate
from ..models.document import Document, DocumentCreate, DocumentUpdate
from ..models.result import Result, ResultCreate, ResultUpdate
# --- Import Enums used in Teacher model ---
from ..models.enums import DocumentStatus, ResultStatus, FileType, TeacherRole, MarketingSource
# ----------------------------------------

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

# --- Transaction and Helper Functions (Assume these exist as before) ---
@asynccontextmanager
async def transaction():
    db = get_database()
    if db is None: raise RuntimeError("Database connection not available for transaction (db is None)")
    if not db.client: raise RuntimeError("Database client not available for session")
    if hasattr(db.client, 'start_session'):
        async with await db.client.start_session() as session:
            async with session.start_transaction():
                logger.debug("MongoDB transaction started.")
                try:
                    yield session
                    logger.debug("MongoDB transaction committing.")
                except Exception as e:
                    logger.error(f"MongoDB transaction aborted due to error: {e}", exc_info=True)
                    await session.abort_transaction()
                    logger.debug("MongoDB transaction explicitly aborted.")
                    raise
    else:
        logger.warning("Database client does not support sessions/transactions. Proceeding without transaction.")
        yield None

def with_transaction(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        session = kwargs.get('session')
        if session is not None:
            return await func(*args, **kwargs)
        else:
            try:
                async with transaction() as new_session:
                    kwargs['session'] = new_session
                    return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Transaction failed or not supported for function {func.__name__}: {e}")
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

# --- School CRUD Functions (Assume these exist as before) ---
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
@with_transaction
async def create_teacher(teacher_in: TeacherCreate, kinde_id: str, session=None) -> Optional[Teacher]:
    """Creates a teacher record, linking it to a Kinde ID."""
    collection = _get_collection(TEACHER_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None

    # Assuming the primary key (_id) for Teacher should be the Kinde user ID ('sub')
    try:
        user_id = uuid.UUID(kinde_id) # Use Kinde ID as the primary UUID key
    except (ValueError, TypeError):
        logger.error(f"Invalid Kinde ID format '{kinde_id}' provided for new teacher.")
        return None # Or raise a specific error

    teacher_doc = teacher_in.model_dump();
    teacher_doc["_id"] = user_id # Use Kinde UUID as the primary key _id
    teacher_doc["user_id"] = user_id # Also store it in user_id field if model expects it
    teacher_doc["kinde_id"] = kinde_id # Store the original string Kinde ID if needed

    teacher_doc["created_at"] = now; teacher_doc["updated_at"] = now; teacher_doc["deleted_at"] = None
    logger.info(f"Inserting teacher with ID (from Kinde sub): {teacher_doc['_id']}")
    try:
        inserted_result = await collection.insert_one(teacher_doc, session=session)
    except DuplicateKeyError:
        logger.warning(f"Teacher record with ID {user_id} already exists.")
        # Optionally fetch and return existing record or handle as error
        return await get_teacher_by_id(user_id=user_id, session=session)
    except Exception as e:
        logger.error(f"Error inserting teacher: {e}", exc_info=True); return None

    if inserted_result.acknowledged:
        created_doc = await collection.find_one({"_id": user_id}, session=session)
        if created_doc:
            # Map _id back to user_id for Pydantic model
            mapped_data = {**created_doc}
            if "_id" in mapped_data: mapped_data["user_id"] = mapped_data.pop("_id")
            return Teacher(**mapped_data)
        else:
            logger.error(f"Failed retrieve teacher post-insert: {user_id}"); return None
    else:
        logger.error(f"Insert teacher not acknowledged: {user_id}"); return None


async def get_teacher_by_id(user_id: uuid.UUID, include_deleted: bool = False, session=None) -> Optional[Teacher]:
    collection = _get_collection(TEACHER_COLLECTION);
    if collection is None: return None
    # Use _id for query as that's the DB primary key
    logger.info(f"Getting teacher by user_id: {user_id}")
    query = {"_id": user_id}; query.update(soft_delete_filter(include_deleted))
    try:
        teacher_doc = await collection.find_one(query, session=session)
        if teacher_doc:
             # Map _id back to user_id for Pydantic model
            mapped_data = {**teacher_doc}
            if "_id" in mapped_data: mapped_data["user_id"] = mapped_data.pop("_id")
            return Teacher(**mapped_data) # Assumes schema handles alias correctly now
        else:
            logger.warning(f"Teacher {user_id} not found."); return None
    except Exception as e:
        logger.error(f"Error getting teacher: {e}", exc_info=True); return None

async def get_all_teachers(skip: int = 0, limit: int = 100, include_deleted: bool = False, session=None) -> List[Teacher]:
    collection = _get_collection(TEACHER_COLLECTION); teachers_list: List[Teacher] = []
    if collection is None: return teachers_list
    query = soft_delete_filter(include_deleted)
    logger.info(f"Getting all teachers skip={skip} limit={limit}")
    try:
        cursor = collection.find(query, session=session).skip(skip).limit(limit)
        async for doc in cursor:
             try:
                 mapped_data = {**doc}
                 # --- Ensure _id is mapped to user_id for the Teacher model ---
                 if "_id" in mapped_data:
                     mapped_data["user_id"] = mapped_data.pop("_id") # Map _id to user_id
                 else:
                     logger.warning(f"Teacher doc missing '_id': {doc}"); continue
                 # -------------------------------------------------------------
                 teachers_list.append(Teacher(**mapped_data))
             except Exception as validation_err:
                 logger.error(f"Pydantic validation failed for teacher doc {doc.get('_id', 'UNKNOWN')}: {validation_err}")
    except Exception as e:
        logger.error(f"Error getting all teachers: {e}", exc_info=True)
    return teachers_list

# --- UPDATED update_teacher Function ---
@with_transaction
async def update_teacher(user_id: uuid.UUID, teacher_in: TeacherUpdate, session=None) -> Optional[Teacher]:
    collection = _get_collection(TEACHER_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None

    # Get update data, excluding fields not set in the input model
    # Use model_dump for Pydantic V2
    update_data = teacher_in.model_dump(exclude_unset=True)

    # Convert enums to their values if necessary for DB storage
    # (Depends on if your DB driver handles enums directly or needs values)
    if 'role' in update_data and isinstance(update_data['role'], TeacherRole):
        update_data['role'] = update_data['role'].value

    # Remove fields that should not be updated directly or are handled by DB/logic
    update_data.pop("_id", None) # Cannot update primary key
    update_data.pop("id", None) # Cannot update alias if present
    update_data.pop("user_id", None) # Should not update user_id link
    update_data.pop("kinde_id", None) # Should not update kinde_id link
    update_data.pop("created_at", None) # Should not update creation time
    update_data.pop("deleted_at", None) # Soft delete handled separately
    # Remove how_did_you_hear if it's not in TeacherUpdate
    update_data.pop("how_did_you_hear", None)


    # Check if there's anything left to update
    if not update_data:
        logger.warning(f"No update data provided for teacher {user_id}")
        # Return the current teacher data if no changes were requested
        return await get_teacher_by_id(user_id, include_deleted=False, session=session)

    # Add the update timestamp
    update_data["updated_at"] = now
    logger.info(f"Updating teacher {user_id} with data: {update_data}")

    # Define the filter to find the correct teacher document (_id is the primary key)
    query_filter = {"_id": user_id, "deleted_at": None} # Ensure we don't update soft-deleted records

    try:
        # Perform the update and return the updated document
        updated_doc = await collection.find_one_and_update(
            query_filter,
            {"$set": update_data},
            return_document=ReturnDocument.AFTER, # Return the document *after* the update
            session=session
        )

        if updated_doc:
            # Map _id back to user_id before returning Pydantic model
            mapped_data = {**updated_doc}
            if "_id" in mapped_data:
                mapped_data["user_id"] = mapped_data.pop("_id")
            return Teacher(**mapped_data) # Validate and return
        else:
            logger.warning(f"Teacher {user_id} not found or already deleted during update attempt.")
            return None
    except Exception as e:
        logger.error(f"Error during teacher update operation for {user_id}: {e}", exc_info=True)
        return None
# --- END UPDATED update_teacher Function ---

@with_transaction
async def delete_teacher(user_id: uuid.UUID, hard_delete: bool = False, session=None) -> bool:
    collection = _get_collection(TEACHER_COLLECTION)
    if collection is None: return False
    logger.info(f"{'Hard' if hard_delete else 'Soft'} deleting teacher {user_id}")
    count = 0
    try:
        if hard_delete: result = await collection.delete_one({"_id": user_id}, session=session); count = result.deleted_count # Query by _id
        else:
            now = datetime.now(timezone.utc)
            result = await collection.update_one({"_id": user_id, "deleted_at": None},{"$set": {"deleted_at": now, "updated_at": now}}, session=session); count = result.modified_count # Query by _id
    except Exception as e: logger.error(f"Error deleting teacher: {e}", exc_info=True); return False
    if count == 1: return True
    else: logger.warning(f"Teacher {user_id} not found or already deleted."); return False


# --- ClassGroup CRUD Functions (Assume these exist as before) ---
@with_transaction
async def create_class_group(class_group_in: ClassGroupCreate, session=None) -> Optional[ClassGroup]:
    collection = _get_collection(CLASSGROUP_COLLECTION); now = datetime.now(timezone.utc)
    if collection is None: return None
    new_id = uuid.uuid4()
    doc = class_group_in.model_dump(); doc["_id"] = new_id; doc.setdefault("student_ids", [])
    doc["created_at"] = now; doc["updated_at"] = now; doc["deleted_at"] = None
    logger.info(f"Inserting class group: {doc['_id']}")
    try: inserted_result = await collection.insert_one(doc, session=session)
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
    if teacher_id: filter_query["teacher_id"] = teacher_id
    if school_id: filter_query["school_id"] = school_id
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


# --- Student CRUD Functions (Assume these exist as before) ---
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
                mapped_data = {**doc} # Create a mutable copy
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


# --- Assignment CRUD Functions (Assume these exist as before) ---
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


# --- Document CRUD Functions (Assume these exist as before) ---
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

async def get_all_documents( student_id: Optional[uuid.UUID] = None, assignment_id: Optional[uuid.UUID] = None, status: Optional[DocumentStatus] = None, skip: int = 0, limit: int = 100, include_deleted: bool = False, session=None) -> List[Document]:
    collection = _get_collection(DOCUMENT_COLLECTION); documents_list: List[Document] = []
    if collection is None: return documents_list
    filter_query = soft_delete_filter(include_deleted)
    if student_id: filter_query["student_id"] = student_id
    if assignment_id: filter_query["assignment_id"] = assignment_id
    if status: filter_query["status"] = status.value # Filter DB by enum value
    logger.info(f"Getting all documents filter={filter_query} skip={skip} limit={limit}")
    try:
        cursor = collection.find(filter_query, session=session).skip(skip).limit(limit)
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

# --- Result CRUD Functions (Assume these exist as before) ---
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

async def get_result_by_document_id(document_id: uuid.UUID, include_deleted: bool = False, session=None) -> Optional[Result]:
    collection = _get_collection(RESULT_COLLECTION)
    if collection is None: return None
    logger.info(f"Getting result for document: {document_id}")
    query = {"document_id": document_id}; query.update(soft_delete_filter(include_deleted))
    try: doc = await collection.find_one(query, session=session)
    except Exception as e: logger.error(f"Error getting result by doc id: {e}", exc_info=True); return None
    if doc: return Result(**doc) # Assumes schema handles alias
    else: logger.info(f"Result for document {document_id} not found."); return None

@with_transaction
async def update_result(result_id: uuid.UUID, result_in: ResultUpdate, session=None) -> Optional[Result]:
    collection = _get_collection(RESULT_COLLECTION)
    if collection is None: return None
    now = datetime.now(timezone.utc)
    update_data = result_in.model_dump(exclude_unset=True)
    if "status" in update_data and isinstance(update_data["status"], ResultStatus): update_data["status"] = update_data["status"].value
    update_data.pop("_id", None); update_data.pop("id", None); update_data.pop("created_at", None); update_data.pop("document_id", None); update_data.pop("deleted_at", None)
    if not update_data: logger.warning(f"No update data for result {result_id}"); return await get_result_by_id(result_id, include_deleted=False, session=session)
    update_data["updated_at"] = now; logger.info(f"Updating result {result_id}")
    query_filter = {"_id": result_id, "deleted_at": None} # Query by _id
    try:
        updated_doc = await collection.find_one_and_update(query_filter, {"$set": update_data}, return_document=ReturnDocument.AFTER, session=session)
        if updated_doc: return Result(**updated_doc) # Assumes schema handles alias
        else: logger.warning(f"Result {result_id} not found or already deleted for update."); return None
    except Exception as e: logger.error(f"Error updating result with ID {result_id}: {e}", exc_info=True); return None

@with_transaction
async def delete_result(result_id: uuid.UUID, hard_delete: bool = False, session=None) -> bool:
    collection = _get_collection(RESULT_COLLECTION)
    if collection is None: return False
    logger.info(f"{'Hard' if hard_delete else 'Soft'} deleting result {result_id}")
    count = 0
    try:
        if hard_delete: result = await collection.delete_one({"_id": result_id}, session=session); count = result.deleted_count # Query by _id
        else:
            now = datetime.now(timezone.utc)
            result = await collection.update_one({"_id": result_id, "deleted_at": None},{"$set": {"deleted_at": now, "updated_at": now}}, session=session); count = result.modified_count # Query by _id
    except Exception as e: logger.error(f"Error deleting result: {e}", exc_info=True); return False
    if count == 1: return True
    else: logger.warning(f"Result {result_id} not found or already deleted."); return False

# --- Bulk Operations (Assume these exist as before) ---
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

# --- Advanced Filtering Support (Assume these exist as before) ---
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

# --- Relationship Validation (Assume these exist as before) ---
async def validate_school_teacher_relationship( school_id: uuid.UUID, teacher_id: uuid.UUID, session=None) -> bool:
    teacher = await get_teacher_by_id(teacher_id, include_deleted=False, session=session)
    return teacher is not None and teacher.school_id == school_id # Ensure teacher is not None

async def validate_class_group_relationships( class_group_id: uuid.UUID, teacher_id: uuid.UUID, school_id: uuid.UUID, session=None) -> bool:
    class_group = await get_class_group_by_id(class_group_id, include_deleted=False, session=session)
    if class_group is None: return False
    if not await validate_school_teacher_relationship(school_id, teacher_id, session=session): return False
    return (class_group.teacher_id == teacher_id and class_group.school_id == school_id)

async def validate_student_class_group_relationship( student_id: uuid.UUID, class_group_id: uuid.UUID, session=None) -> bool:
    class_group = await get_class_group_by_id(class_group_id, include_deleted=False, session=session)
    # Ensure class_group.student_ids exists and is a list before checking 'in'
    return class_group is not None and isinstance(class_group.student_ids, list) and student_id in class_group.student_ids

# --- Enhanced Query Functions (Assume these exist as before) ---
async def get_schools_with_filters(
    filters: Dict[str, Any], include_deleted: bool = False, skip: int = 0,
    limit: int = 100, sort_by: Optional[str] = None, sort_order: int = 1, session=None
) -> List[School]:
    collection = _get_collection(SCHOOL_COLLECTION)
    if collection is None: return []
    query = build_filter_query(filters, include_deleted)
    # Use _id for sorting if 'id' is passed, assuming alias handling in schema output
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
