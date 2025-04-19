# app/api/v1/endpoints/teachers.py

import uuid
import logging # Import logging
from typing import List, Dict, Any # Add Dict, Any
from fastapi import APIRouter, HTTPException, status, Query, Depends # Add Depends

# Import Pydantic models for Teacher
# Adjust path based on your structure
from ....models.teacher import Teacher, TeacherCreate, TeacherUpdate
# Import CRUD functions for Teacher
from ....db import crud # Assuming crud functions are in app/db/crud.py
# Import the authentication dependency
from ....core.security import get_current_user_payload # Adjust path

# Setup logger for this module
logger = logging.getLogger(__name__)

# Create the router instance
router = APIRouter(
    prefix="/teachers",
    tags=["Teachers"]
)

# === Teacher API Endpoints (Now Protected) ===

@router.post(
    "/",
    response_model=Teacher,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new teacher (Protected)", # Updated summary
    description="Creates a new teacher record. Requires authentication." # Updated description
)
async def create_new_teacher(
    teacher_in: TeacherCreate,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to create a new teacher.
    - **teacher_in**: Teacher data based on the TeacherCreate model.
    """
    user_kinde_id = current_user_payload.get("sub") # Get user ID from token payload
    logger.info(f"User {user_kinde_id} attempting to create teacher: {teacher_in.first_name} {teacher_in.last_name}")
    # TODO: Add authorization check - does this user have permission to create teachers? (e.g., admin role?)

    created_teacher = await crud.create_teacher(teacher_in=teacher_in)
    if not created_teacher:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create the teacher record."
        )
    logger.info(f"Teacher '{created_teacher.first_name} {created_teacher.last_name}' created successfully by user {user_kinde_id}.")
    return created_teacher

@router.get(
    "/{user_id}", # Path parameter is the Kinde user_id which is also the _id for teachers
    response_model=Teacher,
    status_code=status.HTTP_200_OK,
    summary="Get a specific teacher by user ID (Protected)", # Updated summary
    description="Retrieves details of a single teacher using their unique user ID. Requires authentication." # Updated description
)
async def read_teacher(
    user_id: uuid.UUID, # Teacher identified by user_id (UUID)
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to retrieve a specific teacher by their user ID.
    - **user_id**: The UUID of the teacher to retrieve.
    """
    requesting_user_id = current_user_payload.get("sub")
    logger.info(f"User {requesting_user_id} attempting to read teacher ID: {user_id}")
    # TODO: Add authorization check - can user 'requesting_user_id' view profile of 'user_id'?
    # (e.g., are they the same user, or does requester have admin rights?)

    teacher = await crud.get_teacher_by_id(user_id=user_id)
    if teacher is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Teacher with user ID {user_id} not found."
        )
    return teacher

@router.get(
    "/",
    response_model=List[Teacher],
    status_code=status.HTTP_200_OK,
    summary="Get a list of teachers (Protected)", # Updated summary
    description="Retrieves a list of teachers with optional pagination. Requires authentication." # Updated description
)
async def read_teachers(
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Max records to return"),
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to retrieve a list of teachers. Supports pagination.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read list of teachers (skip={skip}, limit={limit}).")
    # TODO: Add authorization check? (e.g., only admins can list all?) Or filter based on user?

    teachers = await crud.get_all_teachers(skip=skip, limit=limit)
    return teachers

@router.put(
    "/{user_id}", # Path parameter is the Kinde user_id which is also the _id for teachers
    response_model=Teacher,
    status_code=status.HTTP_200_OK,
    summary="Update an existing teacher (Protected)", # Updated summary
    description="Updates details of an existing teacher. Requires authentication. Users may only update their own profile unless they have admin rights." # Updated description
)
async def update_existing_teacher(
    user_id: uuid.UUID, # The ID of the teacher profile being updated
    teacher_in: TeacherUpdate,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to update an existing teacher.
    """
    requesting_user_id = current_user_payload.get("sub")
    logger.info(f"User {requesting_user_id} attempting to update teacher ID: {user_id}")

    # --- Authorization Check ---
    # Basic check: Allow user to update their own profile.
    # TODO: Enhance this check later to allow admins to update any profile.
    # This requires checking roles/permissions from the token payload.
    # Example: if user_id != requesting_user_id and "update:any_teacher" not in current_user_payload.get('permissions', []):
    try:
        # Convert 'sub' claim (string) from token payload to UUID for comparison
        requesting_user_uuid = uuid.UUID(requesting_user_id)
    except (ValueError, TypeError):
         logger.error(f"Could not convert requesting user ID '{requesting_user_id}' to UUID.")
         raise HTTPException(
             status_code=status.HTTP_400_BAD_REQUEST,
             detail="Invalid user ID format in token."
         )

    if user_id != requesting_user_uuid:
         raise HTTPException(
             status_code=status.HTTP_403_FORBIDDEN,
             detail="Not authorized to update this teacher's profile."
         )
    # --- End Authorization Check ---

    updated_teacher = await crud.update_teacher(user_id=user_id, teacher_in=teacher_in)
    if updated_teacher is None:
        # This could happen if the user_id doesn't exist (though less likely now with auth check)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Teacher with user ID {user_id} not found or update failed."
        )
    logger.info(f"Teacher ID {user_id} updated successfully by user {requesting_user_id}.")
    return updated_teacher

@router.delete(
    "/{user_id}", # Path parameter is the Kinde user_id which is also the _id for teachers
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a teacher (Protected)", # Updated summary
    description="Deletes a teacher record using their unique user ID. Requires authentication and likely admin privileges." # Updated description
)
async def delete_existing_teacher(
    user_id: uuid.UUID,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to delete a specific teacher by their user ID.
    """
    requesting_user_id = current_user_payload.get("sub")
    logger.info(f"User {requesting_user_id} attempting to delete teacher ID: {user_id}")

    # --- Authorization Check ---
    # TODO: Implement proper authorization. Deleting users (even self) is sensitive.
    # Typically only admins should be allowed. Check for admin role/permission.
    # Example: if "delete:any_teacher" not in current_user_payload.get('permissions', []):
    # raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete teachers.")
    # For now, we allow deletion but log a warning. Consider adding the check above.
    logger.warning(f"Performing delete for teacher {user_id} by user {requesting_user_id}. Authorization check needed!")
    # --- End Authorization Check ---


    deleted_successfully = await crud.delete_teacher(user_id=user_id)
    if not deleted_successfully:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Teacher with user ID {user_id} not found."
        )
    logger.info(f"Teacher ID {user_id} deleted successfully by user {requesting_user_id}.")
    # No content returned on successful delete
    return None

