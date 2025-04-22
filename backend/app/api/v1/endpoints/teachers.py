# app/api/v1/endpoints/teachers.py

import uuid
import logging
from typing import List, Dict, Any, Optional # Added Optional
from fastapi import APIRouter, HTTPException, status, Query, Depends

# Import Pydantic models for Teacher
from ....models.teacher import Teacher, TeacherCreate, TeacherUpdate
# Import CRUD functions for Teacher
from ....db import crud
# Import the authentication dependency
from ....core.security import get_current_user_payload # Adjust path if needed

# Setup logger for this module
logger = logging.getLogger(__name__)

# Create the router instance
router = APIRouter(
    prefix="/teachers",
    tags=["Teachers"]
)

# === Teacher API Endpoints (Updated for Profile) ===

# --- NEW: Endpoint to get the current user's profile ---
@router.get(
    "/me",
    response_model=Teacher,
    status_code=status.HTTP_200_OK,
    summary="Get current user's teacher profile (Protected)",
    description="Retrieves the teacher profile associated with the currently authenticated user.",
    responses={
        404: {"description": "Teacher profile not found for the current user"},
        400: {"description": "Invalid user ID format in token"},
    }
)
async def read_current_user_profile(
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to retrieve the teacher profile for the logged-in user.
    """
    user_kinde_id_str = current_user_payload.get("sub")
    logger.info(f"Attempting to read profile for user ID: {user_kinde_id_str}")

    try:
        # Convert 'sub' claim (string) from token payload to UUID
        user_kinde_id = uuid.UUID(user_kinde_id_str)
    except (ValueError, TypeError):
         logger.error(f"Could not convert requesting user ID '{user_kinde_id_str}' to UUID.")
         raise HTTPException(
             status_code=status.HTTP_400_BAD_REQUEST,
             detail="Invalid user ID format in token."
         )

    # Fetch teacher record using the user's UUID
    # Note: crud.get_teacher_by_id uses user_id which is aliased to _id
    teacher_profile = await crud.get_teacher_by_id(user_id=user_kinde_id)

    if teacher_profile is None:
        logger.warning(f"Teacher profile not found for user ID: {user_kinde_id_str}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher profile not found. Please complete your profile."
        )
    logger.info(f"Successfully retrieved profile for user ID: {user_kinde_id_str}")
    return teacher_profile

# --- (Existing POST / endpoint - No changes needed based on profile update) ---
@router.post(
    "/",
    response_model=Teacher,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new teacher (Protected)",
    description="Creates a new teacher record. Requires authentication."
)
async def create_new_teacher(
    teacher_in: TeacherCreate,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to create teacher: {teacher_in.first_name} {teacher_in.last_name}")
    # TODO: Add authorization check - does this user have permission to create teachers?

    created_teacher = await crud.create_teacher(teacher_in=teacher_in)
    if not created_teacher:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create the teacher record."
        )
    logger.info(f"Teacher '{created_teacher.first_name} {created_teacher.last_name}' created successfully by user {user_kinde_id}.")
    return created_teacher

# --- (Existing GET /{user_id} endpoint - No changes needed based on profile update) ---
@router.get(
    "/{user_id}",
    response_model=Teacher,
    status_code=status.HTTP_200_OK,
    summary="Get a specific teacher by user ID (Protected)",
    description="Retrieves details of a single teacher using their unique user ID. Requires authentication."
)
async def read_teacher(
    user_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    requesting_user_id = current_user_payload.get("sub")
    logger.info(f"User {requesting_user_id} attempting to read teacher ID: {user_id}")
    # TODO: Add authorization check - can user 'requesting_user_id' view profile of 'user_id'?

    teacher = await crud.get_teacher_by_id(user_id=user_id)
    if teacher is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Teacher with user ID {user_id} not found."
        )
    return teacher

# --- (Existing GET / endpoint - No changes needed based on profile update) ---
@router.get(
    "/",
    response_model=List[Teacher],
    status_code=status.HTTP_200_OK,
    summary="Get a list of teachers (Protected)",
    description="Retrieves a list of teachers with optional pagination. Requires authentication."
)
async def read_teachers(
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Max records to return"),
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read list of teachers (skip={skip}, limit={limit}).")
    # TODO: Add authorization check? (e.g., only admins can list all?) Or filter based on user?

    teachers = await crud.get_all_teachers(skip=skip, limit=limit)
    return teachers

# --- UPDATED PUT Endpoint ---
@router.put(
    "/{user_id}",
    response_model=Teacher,
    status_code=status.HTTP_200_OK,
    summary="Update an existing teacher/profile (Protected)", # Updated summary
    description="Updates details of an existing teacher profile. Requires authentication. Users may only update their own profile unless they have admin rights." # Updated description
)
async def update_existing_teacher(
    user_id: uuid.UUID, # The ID of the teacher profile being updated
    teacher_in: TeacherUpdate, # Use the updated TeacherUpdate model
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to update an existing teacher profile.
    """
    requesting_user_id_str = current_user_payload.get("sub")
    logger.info(f"User {requesting_user_id_str} attempting to update teacher profile ID: {user_id}")

    # --- Authorization Check ---
    # Basic check: Allow user to update their own profile.
    # TODO: Enhance this check later to allow admins to update any profile.
    try:
        # Convert 'sub' claim (string) from token payload to UUID for comparison
        requesting_user_uuid = uuid.UUID(requesting_user_id_str)
    except (ValueError, TypeError):
         logger.error(f"Could not convert requesting user ID '{requesting_user_id_str}' to UUID.")
         raise HTTPException(
             status_code=status.HTTP_400_BAD_REQUEST,
             detail="Invalid user ID format in token."
         )

    if user_id != requesting_user_uuid:
         # TODO: Add check for admin role/permission here
         logger.warning(f"User {requesting_user_id_str} attempted to update profile for different user {user_id}.")
         raise HTTPException(
             status_code=status.HTTP_403_FORBIDDEN,
             detail="Not authorized to update this teacher's profile."
         )
    # --- End Authorization Check ---

    # Check if the teacher profile exists before attempting update
    existing_teacher = await crud.get_teacher_by_id(user_id=user_id)
    if not existing_teacher:
         raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Teacher profile with user ID {user_id} not found."
        )

    # Call CRUD function with the TeacherUpdate data
    updated_teacher = await crud.update_teacher(user_id=user_id, teacher_in=teacher_in)

    if updated_teacher is None:
        # This might happen if the update failed in the DB for some reason (e.g., concurrency)
        # It shouldn't be a 404 because we checked existence above.
        logger.error(f"Update failed for teacher ID {user_id} even after existence check.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update teacher profile with ID {user_id}."
        )

    logger.info(f"Teacher profile ID {user_id} updated successfully by user {requesting_user_id_str}.")
    return updated_teacher

# --- (Existing DELETE / endpoint - No changes needed based on profile update) ---
@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a teacher (Protected)",
    description="Deletes a teacher record using their unique user ID. Requires authentication and likely admin privileges."
)
async def delete_existing_teacher(
    user_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    requesting_user_id = current_user_payload.get("sub")
    logger.info(f"User {requesting_user_id} attempting to delete teacher ID: {user_id}")
    # TODO: Implement proper authorization. Deleting users is sensitive.
    logger.warning(f"Performing delete for teacher {user_id} by user {requesting_user_id}. Authorization check needed!")

    deleted_successfully = await crud.delete_teacher(user_id=user_id)
    if not deleted_successfully:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Teacher with user ID {user_id} not found."
        )
    logger.info(f"Teacher ID {user_id} deleted successfully by user {requesting_user_id}.")
    return None