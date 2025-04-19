# app/api/v1/endpoints/students.py

import uuid
import logging # Import logging
from typing import List, Optional, Dict, Any # Add Dict, Any
from fastapi import APIRouter, HTTPException, status, Query, Depends # Add Depends

# Import Pydantic models for Student
# Adjust path based on your structure
from ....models.student import Student, StudentCreate, StudentUpdate
# Import CRUD functions for Student
from ....db import crud # Assuming crud functions are in app/db/crud.py
# Import the authentication dependency
from ....core.security import get_current_user_payload # Adjust path

# Setup logger for this module
logger = logging.getLogger(__name__)

# Create the router instance
router = APIRouter(
    prefix="/students",
    tags=["Students"]
)

# === Student API Endpoints (Now Protected) ===

@router.post(
    "/",
    response_model=Student,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new student (Protected)", # Updated summary
    description="Creates a new student record. Requires authentication. Returns a 409 Conflict error if the optional external_student_id is provided and already exists." # Updated description
)
async def create_new_student(
    student_in: StudentCreate,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to create a new student.
    - **student_in**: Student data based on the StudentCreate model.
    """
    user_kinde_id = current_user_payload.get("sub") # Get user ID from token payload
    logger.info(f"User {user_kinde_id} attempting to create student: {student_in.first_name} {student_in.last_name}")
    # TODO: Add authorization check - does this user (teacher/admin) have permission to add students?
    # (e.g., are they adding to a class/school they manage?)

    created_student = await crud.create_student(student_in=student_in)
    if not created_student:
        # Check if the failure might be due to duplicate external_student_id
        if student_in.external_student_id:
             raise HTTPException(
                 status_code=status.HTTP_409_CONFLICT,
                 detail=f"Student with external_student_id '{student_in.external_student_id}' may already exist."
             )
        else:
            # Otherwise, assume a general server error during creation
             raise HTTPException(
                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail="Could not create the student record due to an internal error."
             )
    logger.info(f"Student '{created_student.first_name} {created_student.last_name}' (Internal ID: {created_student.id}) created successfully by user {user_kinde_id}.")
    return created_student

@router.get(
    "/{student_internal_id}",
    response_model=Student,
    status_code=status.HTTP_200_OK,
    summary="Get a specific student by internal ID (Protected)", # Updated summary
    description="Retrieves the details of a single student using their internal unique ID. Requires authentication." # Updated description
)
async def read_student(
    student_internal_id: uuid.UUID, # Internal ID ('id' aliased to '_id' in model)
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to retrieve a specific student by their internal ID.
    - **student_internal_id**: The internal UUID of the student to retrieve.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read student internal ID: {student_internal_id}")

    student = await crud.get_student_by_id(student_internal_id=student_internal_id)
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with internal ID {student_internal_id} not found."
        )

    # TODO: Add authorization check - Can user 'user_kinde_id' view this student?
    # (e.g., is the student in one of the user's ClassGroups? Is the user a school admin?)

    return student

@router.get(
    "/",
    response_model=List[Student],
    status_code=status.HTTP_200_OK,
    summary="Get a list of students (Protected)", # Updated summary
    description="Retrieves a list of students with optional filtering and pagination. Requires authentication." # Updated description
)
async def read_students(
    external_student_id: Optional[str] = Query(None, description="Filter by external student ID"),
    first_name: Optional[str] = Query(None, description="Filter by first name (case-insensitive)"),
    last_name: Optional[str] = Query(None, description="Filter by last name (case-insensitive)"),
    year_group: Optional[str] = Query(None, description="Filter by year group"),
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Max records to return"),
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to retrieve a list of students. Supports filtering and pagination.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read list of students with filters.")

    # TODO: Add authorization logic. Listing ALL students might require admin rights.
    # Non-admins should likely only see students within their associated ClassGroups or School.
    # This might involve modifying the crud.get_all_students function or adding a new one
    # that accepts a list of permissible student IDs based on the user's context.

    students = await crud.get_all_students(
        external_student_id=external_student_id,
        first_name=first_name,
        last_name=last_name,
        year_group=year_group,
        skip=skip,
        limit=limit
    )
    return students

@router.put(
    "/{student_internal_id}",
    response_model=Student,
    status_code=status.HTTP_200_OK,
    summary="Update an existing student (Protected)", # Updated summary
    description="Updates details of an existing student. Requires authentication. Returns 404 if student not found. Returns 409 if update violates unique external_student_id." # Updated description
)
async def update_existing_student(
    student_internal_id: uuid.UUID,
    student_in: StudentUpdate,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to update an existing student.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to update student internal ID: {student_internal_id}")

    # --- Authorization Check ---
    # TODO: Implement proper authorization. Can this user update this student?
    # (e.g., is the student in one of the user's ClassGroups? Is user an admin?)
    # This likely requires fetching the student or their class memberships first.
    # --- End Authorization Check ---

    # Using the improved logic: check existence first
    existing_student = await crud.get_student_by_id(student_internal_id=student_internal_id)
    if not existing_student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with internal ID {student_internal_id} not found."
        )

    # Try to update
    updated_student = await crud.update_student(student_internal_id=student_internal_id, student_in=student_in)
    if updated_student is None:
        # If update failed after existence check, likely a duplicate external_student_id
        if student_in.external_student_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Update failed. Student with external_student_id '{student_in.external_student_id}' may already exist."
            )
        else:
            # Or some other unexpected DB error during update
             raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not update the student record due to an internal error."
            )
    logger.info(f"Student internal ID {student_internal_id} updated successfully by user {user_kinde_id}.")
    return updated_student

@router.delete(
    "/{student_internal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a student (Protected)", # Updated summary
    description="Deletes a student record using their internal unique ID. Requires authentication." # Updated description
)
async def delete_existing_student(
    student_internal_id: uuid.UUID,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to delete a specific student by their internal ID.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to delete student internal ID: {student_internal_id}")

    # --- Authorization Check ---
    # TODO: Implement proper authorization. Can this user delete this student?
    # (Requires checking user's relationship to student via ClassGroups/School or admin role)
    # --- End Authorization Check ---

    deleted_successfully = await crud.delete_student(student_internal_id=student_internal_id)
    if not deleted_successfully:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with internal ID {student_internal_id} not found."
        )
    logger.info(f"Student internal ID {student_internal_id} deleted successfully by user {user_kinde_id}.")
    # No content returned on successful delete
    return None

