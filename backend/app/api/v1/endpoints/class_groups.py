# app/api/v1/endpoints/class_groups.py

import uuid
import logging # Import logging
from typing import List, Optional, Dict, Any # Add Dict, Any
from fastapi import APIRouter, HTTPException, status, Query, Depends # Add Depends

# Import Pydantic models for ClassGroup
# Adjust path based on your structure
from ....models.class_group import ClassGroup, ClassGroupCreate, ClassGroupUpdate
# Import CRUD functions for ClassGroup
from ....db import crud # Assuming crud functions are in app/db/crud.py
# Import the authentication dependency
from ....core.security import get_current_user_payload # Adjust path

# Setup logger for this module
logger = logging.getLogger(__name__)

# Create the router instance
router = APIRouter(
    prefix="/classgroups", # URL prefix uses 'classgroups'
    tags=["Class Groups"] # Tag for OpenAPI docs
)

# === Helper for Authorization Check ===
# (Could be moved to security module or a dedicated authz module later)
def _check_user_is_teacher_of_group(
    class_group: ClassGroup,
    user_payload: Dict[str, Any],
    action: str = "access"
):
    """Checks if the authenticated user is the teacher assigned to the class group."""
    user_kinde_id_str = user_payload.get("sub")
    try:
        # Convert 'sub' claim (string) from token payload to UUID for comparison
        user_kinde_id = uuid.UUID(user_kinde_id_str)
        if class_group.teacher_id != user_kinde_id:
            logger.warning(f"User {user_kinde_id_str} attempted to {action} ClassGroup {class_group.id} owned by {class_group.teacher_id}.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, # 403 Forbidden
                detail=f"Not authorized to {action} this class group."
            )
    except (ValueError, TypeError):
         # Handle cases where 'sub' claim is not a valid UUID string
         logger.error(f"Could not convert requesting user ID '{user_kinde_id_str}' to UUID for authorization check.")
         raise HTTPException(
             status_code=status.HTTP_400_BAD_REQUEST,
             detail="Invalid user ID format in token."
         )

# === ClassGroup API Endpoints (Now Protected) ===

@router.post(
    "/",
    response_model=ClassGroup,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new class group (Protected)", # Updated summary
    description="Creates a new class group record. Requires authentication. User must be the teacher assigned." # Updated description
)
async def create_new_class_group(
    class_group_in: ClassGroupCreate,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to create a new class group.
    Ensures the creator is the assigned teacher.
    - **class_group_in**: Class group data (ClassGroupCreate model).
    """
    user_kinde_id_str = current_user_payload.get("sub") # Get user ID string from token
    logger.info(f"User {user_kinde_id_str} attempting to create class group: {class_group_in.class_name}")

    # --- Authorization Check ---
    # Ensure the user creating the group is the one assigned as the teacher_id in the input
    try:
        user_kinde_id = uuid.UUID(user_kinde_id_str) # Convert to UUID
        if class_group_in.teacher_id != user_kinde_id:
             logger.warning(f"User {user_kinde_id_str} attempted to create ClassGroup assigned to different teacher {class_group_in.teacher_id}.")
             raise HTTPException(
                 status_code=status.HTTP_403_FORBIDDEN, # 403 Forbidden
                 detail="Cannot create a class group assigned to another teacher."
             )
    except (ValueError, TypeError):
         # Handle cases where 'sub' claim is not a valid UUID string
         logger.error(f"Could not convert requesting user ID '{user_kinde_id_str}' to UUID for authorization check.")
         raise HTTPException(
             status_code=status.HTTP_400_BAD_REQUEST,
             detail="Invalid user ID format in token."
         )
    # TODO: Add further checks? Does the specified school_id exist? Is the user associated with that school?
    # --- End Authorization Check ---

    created_cg = await crud.create_class_group(class_group_in=class_group_in)
    if not created_cg:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create the class group record."
        )
    logger.info(f"ClassGroup '{created_cg.class_name}' (ID: {created_cg.id}) created successfully by user {user_kinde_id_str}.")
    return created_cg

@router.get(
    "/{class_group_id}",
    response_model=ClassGroup,
    status_code=status.HTTP_200_OK,
    summary="Get a specific class group by ID (Protected)", # Updated summary
    description="Retrieves details of a single class group. Requires authentication." # Updated description
)
async def read_class_group(
    class_group_id: uuid.UUID,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to retrieve a specific class group by its ID.
    - **class_group_id**: The UUID of the class group to retrieve.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read class group ID: {class_group_id}")

    class_group = await crud.get_class_group_by_id(class_group_id=class_group_id)
    if class_group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Class group with ID {class_group_id} not found."
        )

    # TODO: Add fine-grained authorization check:
    # Can this user view this specific class group?
    # (e.g., are they the teacher_id, or an admin of the school_id?)
    # For now, any authenticated user can read any group they know the ID of.

    return class_group

@router.get(
    "/",
    response_model=List[ClassGroup],
    status_code=status.HTTP_200_OK,
    summary="Get a list of class groups (Protected)", # Updated summary
    description="Retrieves a list of class groups, with optional filtering by teacher/school and pagination. Requires authentication." # Updated description
)
async def read_class_groups(
    teacher_id: Optional[uuid.UUID] = Query(None, description="Filter by teacher UUID"),
    school_id: Optional[uuid.UUID] = Query(None, description="Filter by school UUID"),
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Max records to return"),
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to retrieve a list of class groups. Supports filtering and pagination.
    - **teacher_id**: Optional teacher UUID filter.
    - **school_id**: Optional school UUID filter.
    - **skip**: Number of records to skip.
    - **limit**: Maximum number of records per page.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read list of class groups with filters: teacher={teacher_id}, school={school_id}")

    # TODO: Add authorization logic. E.g.:
    # - If user is not admin, maybe force filter by their own teacher_id?
    # - If school_id is provided, check if user belongs to that school?
    # For now, allows any authenticated user to use filters as provided.

    class_groups = await crud.get_all_class_groups(
        teacher_id=teacher_id,
        school_id=school_id,
        skip=skip,
        limit=limit
    )
    return class_groups

@router.put(
    "/{class_group_id}",
    response_model=ClassGroup,
    status_code=status.HTTP_200_OK,
    summary="Update an existing class group (Protected)", # Updated summary
    description="Updates details (name, due date, student list) of an existing class group. Requires authentication. Only the assigned teacher can update." # Updated description
)
async def update_existing_class_group(
    class_group_id: uuid.UUID,
    class_group_in: ClassGroupUpdate,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to update an existing class group.
    Ensures the updater is the assigned teacher.
    - **class_group_id**: The UUID of the class group to update.
    - **class_group_in**: The class group data fields to update (ClassGroupUpdate model).
    """
    user_kinde_id_str = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id_str} attempting to update class group ID: {class_group_id}")

    # --- Authorization Check ---
    # Get the existing group first to check ownership
    existing_class_group = await crud.get_class_group_by_id(class_group_id=class_group_id)
    if existing_class_group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Class group with ID {class_group_id} not found."
        )
    # Check if the current user is the teacher for this group using the helper
    _check_user_is_teacher_of_group(existing_class_group, current_user_payload, action="update")
    # TODO: Allow admins to update? Check roles/permissions here.
    # --- End Authorization Check ---

    updated_cg = await crud.update_class_group(class_group_id=class_group_id, class_group_in=class_group_in)
    # CRUD function returns None if not found, but we already checked existence.
    # If it returns None now, it implies an unexpected DB error during update.
    if updated_cg is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update class group with ID {class_group_id}."
        )
    logger.info(f"ClassGroup ID {class_group_id} updated successfully by user {user_kinde_id_str}.")
    return updated_cg

@router.delete(
    "/{class_group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a class group (Protected)", # Updated summary
    description="Deletes a class group record. Requires authentication. Only the assigned teacher can delete." # Updated description
)
async def delete_existing_class_group(
    class_group_id: uuid.UUID,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to delete a specific class group by its ID.
    Ensures the deleter is the assigned teacher.
    - **class_group_id**: The UUID of the class group to delete.
    """
    user_kinde_id_str = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id_str} attempting to delete class group ID: {class_group_id}")

    # --- Authorization Check ---
    # Get the existing group first to check ownership
    existing_class_group = await crud.get_class_group_by_id(class_group_id=class_group_id)
    if existing_class_group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Class group with ID {class_group_id} not found."
        )
    # Check if the current user is the teacher for this group using the helper
    _check_user_is_teacher_of_group(existing_class_group, current_user_payload, action="delete")
    # TODO: Allow admins to delete? Check roles/permissions here.
    # --- End Authorization Check ---

    deleted_successfully = await crud.delete_class_group(class_group_id=class_group_id)
    if not deleted_successfully:
        # Should not happen if existence check passed, implies other error during delete
         raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete class group with ID {class_group_id}."
        )
    logger.info(f"ClassGroup ID {class_group_id} deleted successfully by user {user_kinde_id_str}.")
    # No content returned on successful delete
    return None

