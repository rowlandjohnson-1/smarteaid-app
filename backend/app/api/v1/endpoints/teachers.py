# app/api/v1/endpoints/teachers.py

import uuid
import logging
from typing import List, Dict, Any, Optional
# Import Request (kept as per user's file)
from fastapi import APIRouter, HTTPException, status, Query, Depends, Request
# Import Pydantic validation error
from pydantic import ValidationError

# Import Pydantic models for Teacher
from app.models.teacher import Teacher, TeacherCreate, TeacherUpdate
# Import CRUD functions for Teacher
from app.db import crud
# Import the authentication dependency
from app.core.security import get_current_user_payload

# Setup logger for this module
logger = logging.getLogger(__name__)

# Create the router instance
router = APIRouter(
    prefix="/teachers",
    tags=["Teachers"]
)

# === Teacher API Endpoints (Updated Flow) ===

# --- GET /me endpoint (Fetch Only) ---
@router.get(
    "/me",
    response_model=Teacher,
    status_code=status.HTTP_200_OK,
    summary="Get current user's teacher profile (Protected)",
    description=(
        "Retrieves the teacher profile associated with the currently authenticated user, "
        "identified by Kinde ID. Returns 404 if the profile does not exist."
    ),
    responses={
        404: {"description": "Teacher profile not found for the current user"},
        400: {"description": "User identifier missing from token"},
    }
)
async def read_current_user_profile(
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Retrieves the current user's teacher profile. Returns 404 if not found.
    Does NOT create the profile automatically.
    """
    user_kinde_id_str = current_user_payload.get("sub")
    if not user_kinde_id_str:
        logger.error("Kinde 'sub' claim missing from token payload.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User identifier missing from token.")

    logger.info(f"Attempting to retrieve profile for Kinde ID: {user_kinde_id_str}")

    # 1. Try to get the existing teacher profile
    teacher = await crud.get_teacher_by_kinde_id(kinde_id=user_kinde_id_str)

    if teacher:
        logger.info(f"Found existing teacher profile for Kinde ID: {user_kinde_id_str}, Internal ID: {teacher.id}")
        return teacher
    else:
        # 2. Profile not found, return 404
        logger.warning(f"Teacher profile not found for Kinde ID: {user_kinde_id_str}. Returning 404.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher profile not found. Please complete your profile." # Keep message consistent with frontend expectation
        )

# --- GET /teachers/{teacher_kinde_id} endpoint (Admin Only) ---
@router.get(
    "/{teacher_kinde_id_to_fetch}", # Path parameter for the Kinde ID of the teacher to fetch
    response_model=Teacher,
    status_code=status.HTTP_200_OK,
    summary="Get specific teacher profile by Kinde ID (Admin Only)",
    description=(
        "Retrieves the profile of a specific teacher identified by their Kinde ID. "
        "Requires administrator privileges."
    ),
    responses={
        403: {"description": "User does not have admin privileges"},
        404: {"description": "Teacher profile not found for the given Kinde ID"},
    }
)
async def read_teacher_by_id_as_admin(
    teacher_kinde_id_to_fetch: str, # The Kinde ID from the path
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Admin-only endpoint to retrieve a specific teacher's profile by their Kinde ID.
    """
    requesting_user_kinde_id = current_user_payload.get("sub")
    requesting_user_roles = current_user_payload.get("roles", [])

    logger.info(
        f"User {requesting_user_kinde_id} (Roles: {requesting_user_roles}) attempting to fetch profile for Kinde ID: {teacher_kinde_id_to_fetch}"
    )

    # Authorization check: Only allow users with the "admin" role
    if "admin" not in requesting_user_roles:
        logger.warning(
            f"User {requesting_user_kinde_id} (Roles: {requesting_user_roles}) denied access to fetch teacher {teacher_kinde_id_to_fetch} (requires admin role)."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this resource."
        )

    logger.info(f"Admin user {requesting_user_kinde_id} granted access to fetch teacher {teacher_kinde_id_to_fetch}.")

    # Fetch the teacher using the Kinde ID from the path
    teacher = await crud.get_teacher_by_kinde_id(kinde_id=teacher_kinde_id_to_fetch)

    if teacher:
        logger.info(f"Successfully fetched teacher profile for Kinde ID: {teacher_kinde_id_to_fetch}")
        return teacher
    else:
        logger.warning(f"Teacher profile not found for Kinde ID: {teacher_kinde_id_to_fetch} when requested by admin {requesting_user_kinde_id}.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Teacher profile not found for Kinde ID: {teacher_kinde_id_to_fetch}"
        )

# --- PUT /me endpoint (Update or Create - Upsert Logic - CORRECTED for User Version) ---
@router.put(
    "/me",
    response_model=Teacher,
    status_code=status.HTTP_200_OK, # Return 200 for both update and create via PUT
    summary="Update or Create current user's teacher profile (Protected)",
    description=(
        "Updates the teacher profile associated with the currently authenticated user. "
        "If the profile does not exist, it creates a new one using the provided data "
        "and the Kinde ID from the token."
    ),
     responses={
        # 404 is less likely now unless DB fails during check
        404: {"description": "Teacher profile not found (should not happen with create logic unless DB error)"},
        400: {"description": "User identifier missing from token or invalid update data"},
        422: {"description": "Validation Error in request body"},
        500: {"description": "Internal server error during profile creation/update"},
    }
)
async def update_or_create_current_user_profile(
    request: Request, # Keep for potential raw body logging on error (as per user's code)
    teacher_data: TeacherUpdate, # Use TeacherUpdate which allows optional fields
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to update the current user's teacher profile.
    If the profile doesn't exist, it creates it using the provided data.
    """
    user_kinde_id_str = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id_str} attempting to update or create their profile.")
    # Use exclude_unset=True to only log fields explicitly sent by the client
    logger.debug(f"Received profile data (TeacherUpdate model): {teacher_data.model_dump(exclude_unset=True)}")

    if not user_kinde_id_str:
        logger.error("Kinde 'sub' claim missing from token payload during profile update/create.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User identifier missing from token.")

    # 1. Try to find the existing teacher
    existing_teacher = await crud.get_teacher_by_kinde_id(kinde_id=user_kinde_id_str)

    if existing_teacher:
        # --- UPDATE PATH ---
        logger.info(f"Found existing profile for {user_kinde_id_str} (ID: {existing_teacher.id}). Proceeding with update.")
        try:
            # Pass only fields that were actually set in the request to the CRUD function
            # NOTE: Using teacher_data directly as per user's original code.
            # Ensure crud.update_teacher handles TeacherUpdate model correctly,
            # potentially ignoring unset fields internally or using model_dump(exclude_unset=True).
            update_payload_for_log = teacher_data.model_dump(exclude_unset=True)
            if not update_payload_for_log:
                 logger.warning(f"Update request for Kinde ID {user_kinde_id_str} contained no fields to update.")
                 # Return existing teacher data if no changes were sent
                 return existing_teacher

            logger.debug(f"Calling crud.update_teacher for Kinde ID {user_kinde_id_str} with data: {update_payload_for_log}")
            updated_teacher = await crud.update_teacher(kinde_id=user_kinde_id_str, teacher_in=teacher_data)

            if updated_teacher is None:
                 # This might happen if the record disappeared between check and update, or DB error
                 logger.error(f"Update failed unexpectedly for teacher Kinde ID {user_kinde_id_str}. Profile might not exist or DB error occurred.")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher profile not found during update attempt.")

            logger.info(f"Teacher profile for Kinde ID {user_kinde_id_str} updated successfully.")
            return updated_teacher

        except ValidationError as e:
            # This might occur if crud.update_teacher does internal validation that fails
            logger.error(f"Pydantic validation failed during teacher update for Kinde ID {user_kinde_id_str}: {e.errors()}", exc_info=False)
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.errors())
        except Exception as e:
            logger.error(f"CRUD update_teacher failed for Kinde ID {user_kinde_id_str}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update profile due to server error.")

    else:
        # --- CREATE PATH ---
        logger.warning(f"No existing profile found for {user_kinde_id_str}. Proceeding with creation via PUT.")

        # We MUST get email from token for creation.
        email_from_token = current_user_payload.get("email")
        if not email_from_token:
             logger.error(f"Cannot create profile for {user_kinde_id_str}: Email missing from token.")
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email missing from authentication token. Cannot create profile.")

        # Validate that required fields for creation are present in the request body (teacher_data)
        required_fields_for_create = ['first_name', 'last_name', 'school_name', 'role', 'country', 'state_county']
        missing_required = []
        payload_for_create = {} # This will hold data for the TeacherCreate model

        # Populate required fields from teacher_data (TeacherUpdate instance)
        for field in required_fields_for_create:
            # Use getattr to safely access fields from the TeacherUpdate object
            value = getattr(teacher_data, field, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing_required.append(field)
            else:
                payload_for_create[field] = value

        if missing_required:
             logger.error(f"Cannot create profile for {user_kinde_id_str}: Required fields missing from request body: {missing_required}")
             raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Missing required profile fields: {', '.join(missing_required)}")

        # Add email from token
        payload_for_create['email'] = email_from_token

        # *** CORRECTED: Safely add optional fields using getattr ***
        how_did_you_hear_value = getattr(teacher_data, 'how_did_you_hear', None)
        if how_did_you_hear_value: # Add only if value exists and is not empty/None
            payload_for_create['how_did_you_hear'] = how_did_you_hear_value
            logger.debug(f"Adding 'how_did_you_hear': {how_did_you_hear_value}")
        else:
             logger.debug("'how_did_you_hear' not provided or empty.")


        description_value = getattr(teacher_data, 'description', None)
        if description_value: # Add only if value exists and is not empty/None
            payload_for_create['description'] = description_value
            logger.debug(f"Adding 'description': {description_value}")
        else:
            logger.debug("'description' not provided or empty.")

        # is_active defaults to True in TeacherCreate model, so no need to set explicitly unless needed

        logger.debug(f"Constructing TeacherCreate payload: {payload_for_create}")

        # Construct the TeacherCreate object
        try:
            teacher_create_payload = TeacherCreate(**payload_for_create)
        except ValidationError as e:
             logger.error(f"Pydantic validation failed constructing TeacherCreate for Kinde ID {user_kinde_id_str}: {e.errors()}", exc_info=False)
             # Provide more specific error details if possible
             raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid profile data provided for creation: {e.errors()}")

        # Call CRUD create function
        try:
            # Pass kinde_id separately to the CRUD function
            logger.debug(f"Calling crud.create_teacher for Kinde ID {user_kinde_id_str} with payload: {teacher_create_payload.model_dump()}")
            created_teacher = await crud.create_teacher(teacher_in=teacher_create_payload, kinde_id=user_kinde_id_str)

            if created_teacher:
                logger.info(f"Successfully created new teacher profile via PUT for Kinde ID: {user_kinde_id_str}, Internal ID: {created_teacher.id}")
                return created_teacher
            else:
                # This case implies crud.create_teacher returned None without raising an exception, which is unusual.
                logger.error(f"crud.create_teacher returned None unexpectedly during PUT for Kinde ID: {user_kinde_id_str}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create teacher profile due to an unexpected internal error.")
        except Exception as e:
            # Catch potential exceptions from the CRUD operation (e.g., database errors, unique constraints)
            logger.error(f"Exception during teacher creation via PUT for Kinde ID {user_kinde_id_str}: {e}", exc_info=True)
            # Check for specific DB errors if possible, otherwise return generic 500
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while creating the teacher profile.")

# --- PUT /teachers/{teacher_kinde_id_to_update} endpoint (Admin Only) ---
@router.put(
    "/{teacher_kinde_id_to_update}",
    response_model=Teacher,
    status_code=status.HTTP_200_OK,
    summary="Update a specific teacher's profile by Kinde ID (Admin Only)",
    description=(
        "Updates the profile of a specific teacher identified by their Kinde ID. "
        "Requires administrator privileges."
    ),
    responses={
        403: {"description": "User does not have admin privileges"},
        404: {"description": "Teacher profile not found for the given Kinde ID to update"},
        422: {"description": "Validation Error in request body"},
        500: {"description": "Internal server error during profile update"},
    }
)
async def update_teacher_by_id_as_admin(
    teacher_kinde_id_to_update: str, # The Kinde ID from the path of the teacher to update
    teacher_update_data: TeacherUpdate,    # The update data from the request body
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Admin-only endpoint to update a specific teacher's profile by their Kinde ID.
    """
    requesting_user_kinde_id = current_user_payload.get("sub")
    requesting_user_roles = current_user_payload.get("roles", [])

    logger.info(
        f"User {requesting_user_kinde_id} (Roles: {requesting_user_roles}) attempting to update profile for Kinde ID: {teacher_kinde_id_to_update}"
    )
    logger.debug(f"Admin update payload for {teacher_kinde_id_to_update}: {teacher_update_data.model_dump(exclude_unset=True)}")

    # 1. Authorization check: Only allow users with the "admin" role
    if "admin" not in requesting_user_roles:
        logger.warning(
            f"User {requesting_user_kinde_id} (Roles: {requesting_user_roles}) denied attempt to update teacher {teacher_kinde_id_to_update} (requires admin role)."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action."
        )

    logger.info(f"Admin user {requesting_user_kinde_id} granted access to update teacher {teacher_kinde_id_to_update}.")

    # 2. Check if the target teacher profile exists
    # This step is implicitly handled by crud.update_teacher if it returns None for non-existent IDs,
    # but an explicit check can provide a clearer 404 before attempting an update.
    # However, to align with how PUT /me and other updates might work, we can rely on crud.update_teacher
    # to handle the "not found" case if it's designed to do so (e.g., by returning None).
    # For robustness, an explicit check is often better if crud.update_teacher doesn't distinguish between "not found" and "update failed for other reasons".
    # Let's assume crud.update_teacher will be called and its return value checked.

    # 3. Perform the update using the CRUD function
    # Ensure crud.update_teacher can accept a kinde_id to identify the teacher and TeacherUpdate model.
    try:
        updated_teacher = await crud.update_teacher(
            kinde_id=teacher_kinde_id_to_update, 
            teacher_in=teacher_update_data
        )

        if updated_teacher is None:
            # This means the teacher was not found by crud.update_teacher or another issue occurred.
            logger.warning(f"Admin update failed: Teacher profile not found for Kinde ID: {teacher_kinde_id_to_update} (or update returned None).")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Teacher profile with Kinde ID '{teacher_kinde_id_to_update}' not found or update failed."
            )

        logger.info(f"Teacher profile for Kinde ID {teacher_kinde_id_to_update} updated successfully by admin {requesting_user_kinde_id}.")
        return updated_teacher

    except ValidationError as e:
        logger.error(f"Pydantic validation error during admin update for Kinde ID {teacher_kinde_id_to_update}: {e.errors()}", exc_info=False)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.errors())
    except Exception as e:
        logger.error(f"CRUD update_teacher failed for Kinde ID {teacher_kinde_id_to_update} during admin update: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update teacher profile due to a server error.")

# --- POST / Endpoint ---
# (Code remains the same as user provided)
@router.post(
    "/",
    response_model=Teacher,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new teacher profile (Protected)",
    description="Creates a new teacher profile linked to the authenticated user's Kinde ID. Returns 409 if profile already exists. (Consider if PUT /me replaces this for user creation)",
    responses={
        409: {"description": "Teacher profile already exists for this user"},
        422: {"description": "Validation Error"},
        500: {"description": "Internal Server Error"}
    }
)
async def create_new_teacher(
    request: Request, # Keep Request to log raw body
    # teacher_in: TeacherCreate, # Temporarily remove Pydantic validation here
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to create a new teacher profile for the calling user.
    NOTE: PUT /me now handles initial profile creation. This endpoint might
    only be needed for specific scenarios or admin actions.
    """
    raw_body_str = ""
    try:
        raw_body = await request.body()
        raw_body_str = raw_body.decode()
        logger.debug(f"Raw body received for POST /teachers/: {raw_body_str}")
    except Exception as e:
        logger.error(f"Could not read raw request body: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not read request body.")

    # --- Explicit Pydantic Validation with Logging ---
    try:
        # Manually parse the raw body using the TeacherCreate model
        teacher_data = TeacherCreate.model_validate_json(raw_body_str)
        logger.info(f"Manual validation successful. Data: {teacher_data.model_dump()}")
    except ValidationError as e:
        logger.error(f"Pydantic validation failed for POST /teachers/: {e.errors()}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.errors()
        )
    except Exception as e:
        logger.error(f"Error parsing request body for POST /teachers/: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid request body format: {e}")
    # --- End Explicit Validation ---

    user_kinde_id_str = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id_str} attempting to create teacher profile using validated data: {teacher_data.model_dump()}")

    if not user_kinde_id_str:
        logger.error("Kinde 'sub' claim missing from token payload during teacher creation.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User identifier missing from token.")

    # Check if profile already exists for this Kinde ID
    existing_teacher = await crud.get_teacher_by_kinde_id(kinde_id=user_kinde_id_str)
    if existing_teacher:
        logger.warning(f"Attempt to create profile failed: Teacher profile already exists for Kinde ID {user_kinde_id_str}.")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Teacher profile already exists for this user."
        )

    logger.debug(f"Calling crud.create_teacher for Kinde ID {user_kinde_id_str} with validated data: {teacher_data.model_dump()}")
    try:
        # Pass the validated Pydantic object and kinde_id to the CRUD function
        created_teacher = await crud.create_teacher(teacher_in=teacher_data, kinde_id=user_kinde_id_str)
    except Exception as e:
        logger.error(f"CRUD create_teacher failed for Kinde ID {user_kinde_id_str}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create profile due to server error.")

    if not created_teacher:
        logger.error(f"crud.create_teacher returned None unexpectedly for Kinde ID {user_kinde_id_str}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create the teacher record due to an internal error."
        )

    logger.info(f"Teacher profile '{created_teacher.first_name} {created_teacher.last_name}' created successfully for user {user_kinde_id_str}.")
    return created_teacher


# --- GET / Endpoint (List all teachers - likely admin only) ---
@router.get(
    "/",
    response_model=List[Teacher],
    status_code=status.HTTP_200_OK,
    summary="Get a list of teachers (Protected)",
    description="Retrieves a list of teachers with optional pagination. Requires authentication (likely admin)."
)
async def read_teachers(
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Max records to return"),
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    user_kinde_id = current_user_payload.get("sub")
    user_roles = current_user_payload.get("roles", [])

    logger.info(f"User {user_kinde_id} (Roles: {user_roles}) attempting to read list of teachers (skip={skip}, limit={limit}).")

    # Authorization check: Only allow users with the "admin" role
    if "admin" not in user_roles:
        logger.warning(f"User {user_kinde_id} (Roles: {user_roles}) denied access to list all teachers (requires admin role).")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this resource."
        )
    
    logger.info(f"Admin user {user_kinde_id} granted access to list teachers.")
    teachers = await crud.get_all_teachers(skip=skip, limit=limit)
    return teachers


# --- DELETE /me Endpoint (Updated to use Kinde ID) ---
# (Code remains the same as user provided)
@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete current user's teacher profile (Protected)",
    description="Deletes the teacher profile associated with the currently authenticated user.",
     responses={
        404: {"description": "Teacher profile not found for the current user"},
        400: {"description": "User identifier missing from token"},
    }
)
async def delete_current_user_profile(
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to delete the current user's teacher profile.
    Identifies the user via the Kinde ID in the token.
    """
    user_kinde_id_str = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id_str} attempting to delete their own teacher profile.")

    if not user_kinde_id_str:
        logger.error("Kinde 'sub' claim missing from token payload during profile deletion.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User identifier missing from token.")

    # Call CRUD function using Kinde ID to identify the teacher to delete
    # Ensure crud.delete_teacher supports deletion by kinde_id
    deleted_successfully = await crud.delete_teacher(kinde_id=user_kinde_id_str)

    if not deleted_successfully:
        # crud.delete_teacher returning False likely means the record wasn't found
        logger.warning(f"Attempted to delete non-existent teacher profile for Kinde ID: {user_kinde_id_str}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Teacher profile for Kinde ID {user_kinde_id_str} not found."
        )

    logger.info(f"Teacher profile for Kinde ID {user_kinde_id_str} deleted successfully.")
    # Return None for 204 No Content response
    return None

# --- DELETE /teachers/{teacher_kinde_id_to_delete} endpoint (Admin Only) ---
@router.delete(
    "/{teacher_kinde_id_to_delete}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a specific teacher's profile by Kinde ID (Admin Only)",
    description=(
        "Deletes the profile of a specific teacher identified by their Kinde ID. "
        "Requires administrator privileges."
    ),
    responses={
        403: {"description": "User does not have admin privileges"},
        404: {"description": "Teacher profile not found for the given Kinde ID to delete"},
        500: {"description": "Internal server error during profile deletion"},
    }
)
async def delete_teacher_by_id_as_admin(
    teacher_kinde_id_to_delete: str, # The Kinde ID from the path of the teacher to delete
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Admin-only endpoint to delete a specific teacher's profile by their Kinde ID.
    """
    requesting_user_kinde_id = current_user_payload.get("sub")
    requesting_user_roles = current_user_payload.get("roles", [])

    logger.info(
        f"User {requesting_user_kinde_id} (Roles: {requesting_user_roles}) attempting to delete profile for Kinde ID: {teacher_kinde_id_to_delete}"
    )

    # 1. Authorization check: Only allow users with the "admin" role
    if "admin" not in requesting_user_roles:
        logger.warning(
            f"User {requesting_user_kinde_id} (Roles: {requesting_user_roles}) denied attempt to delete teacher {teacher_kinde_id_to_delete} (requires admin role)."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action."
        )

    logger.info(f"Admin user {requesting_user_kinde_id} granted access to delete teacher {teacher_kinde_id_to_delete}.")

    # 2. Perform the delete using the CRUD function
    # Ensure crud.delete_teacher can accept a kinde_id to identify the teacher.
    # It should return True if deletion was successful, False otherwise (e.g., if not found).
    try:
        # First, check if the teacher exists to provide a more specific 404 if needed.
        # (Though crud.delete_teacher might handle this, explicit check is clearer)
        teacher_to_delete = await crud.get_teacher_by_kinde_id(kinde_id=teacher_kinde_id_to_delete)
        if not teacher_to_delete:
            logger.warning(f"Admin delete failed: Teacher profile not found for Kinde ID: {teacher_kinde_id_to_delete}.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Teacher profile with Kinde ID '{teacher_kinde_id_to_delete}' not found."
            )
        
        deleted_successfully = await crud.delete_teacher(kinde_id=teacher_kinde_id_to_delete)

        if not deleted_successfully:
            # This might occur if the record disappeared between check and delete, or another issue.
            logger.error(f"Admin delete operation for Kinde ID {teacher_kinde_id_to_delete} returned False from CRUD, but teacher was found prior.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete teacher profile for Kinde ID '{teacher_kinde_id_to_delete}' due to an unexpected issue after existence check."
            )

        logger.info(f"Teacher profile for Kinde ID {teacher_kinde_id_to_delete} deleted successfully by admin {requesting_user_kinde_id}.")
        # For 204 No Content, FastAPI expects no return body.
        return None # Or return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException: # Re-raise known HTTPExceptions (like the 404 above)
        raise
    except Exception as e:
        logger.error(f"CRUD delete_teacher failed for Kinde ID {teacher_kinde_id_to_delete} during admin delete: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete teacher profile due to a server error.")
