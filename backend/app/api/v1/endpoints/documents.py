# backend/app/api/v1/endpoints/documents.py

import uuid
import logging
import os # Needed for path operations (splitext)
from typing import List, Optional, Dict, Any
from fastapi import (
    APIRouter, HTTPException, status, Query, Depends,
    UploadFile, File, Form
)
# Add PlainTextResponse for the new endpoint's return type
from fastapi.responses import PlainTextResponse, JSONResponse # Added JSONResponse
from datetime import datetime, timezone
import httpx # Import httpx for making external API calls

# Import models
# Adjust path based on your structure if needed
from ....models.document import Document, DocumentCreate, DocumentUpdate
# --- Import ParagraphResult along with others ---
from ....models.result import Result, ResultCreate, ResultUpdate, ParagraphResult
# --- End Import ---
# Ensure FileType is imported along with other enums
from ....models.enums import DocumentStatus, ResultStatus, FileType, BatchPriority, BatchStatus
# Import Batch models
from ....models.batch import Batch, BatchCreate, BatchUpdate, BatchWithDocuments

# Import CRUD functions
from ....db import crud # Assuming crud functions are in app/db/crud.py

# Import Authentication Dependency
from ....core.security import get_current_user_payload # Adjust path

# Import Blob Storage Service (upload is used, assume download exists)
from ....services.blob_storage import upload_file_to_blob, download_blob_as_bytes # Adjusted path, added download assumption

# Import Text Extraction Service
from ....services.text_extraction import extract_text_from_bytes # Adjusted path

# Import external API URL from config (assuming you add it there)
# from ....core.config import ML_API_URL, ML_RECAPTCHA_SECRET # Placeholder - add these to config.py
# --- TEMPORARY: Define URLs directly here until added to config ---
# Use the URL provided by the user
ML_API_URL="https://fa-sdt-uks-aitextdet-prod.azurewebsites.net/api/ai-text-detection?code=PZrMzMk1VBBCyCminwvgUfzv_YGhVU-5E1JIs2if7zqiAzFuMhUC-g%3D%3D"
# ML_RECAPTCHA_SECRET="6LfAEWwqAAAAAKCk5TXLVa7L9tSY-850idoUwOgr" # Store securely if needed - currently unused
# --- END TEMPORARY ---


# Setup logger
logger = logging.getLogger(__name__)

# --- IMPORTANT: Define the router instance ---
router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)
# --- End router definition ---

# === Document API Endpoints (Protected) ===

@router.post(
    "/upload",
    response_model=Document, # Return document metadata on successful upload
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new document for analysis (Protected)",
    description="Uploads a file (PDF, DOCX, TXT, PNG, JPG), stores it in blob storage, "
                "creates a document metadata record, and queues it for analysis. "
                "Requires authentication."
)
async def upload_document(
    # Use Form(...) for fields sent alongside the file
    student_id: uuid.UUID = Form(..., description="Internal ID of the student associated with the document"),
    assignment_id: uuid.UUID = Form(..., description="ID of the assignment associated with the document"),
    # Use File(...) for the file upload itself
    file: UploadFile = File(..., description="The document file to upload (PDF, DOCX, TXT, PNG, JPG)"),
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to upload a document, store it, create metadata,
    and initiate the analysis process.
    """
    user_kinde_id = current_user_payload.get("sub")
    original_filename = file.filename or "unknown_file"
    logger.info(f"User {user_kinde_id} attempting to upload document '{original_filename}' for student {student_id}, assignment {assignment_id}")

    # --- Authorization Check ---
    # TODO: Implement proper authorization. Can this user upload a document for this student/assignment?
    logger.warning(f"Authorization check needed for user {user_kinde_id} uploading for student {student_id} / assignment {assignment_id}")
    # --- End Authorization Check ---

    # --- File Type Validation ---
    content_type = file.content_type
    file_extension = os.path.splitext(original_filename)[1].lower()
    file_type_enum : Optional[FileType] = None
    if file_extension == ".pdf" and content_type == "application/pdf": file_type_enum = FileType.PDF
    elif file_extension == ".docx" and content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document": file_type_enum = FileType.DOCX
    elif file_extension == ".txt" and content_type == "text/plain": file_type_enum = FileType.TXT
    elif file_extension == ".png" and content_type == "image/png": file_type_enum = FileType.PNG
    elif file_extension in [".jpg", ".jpeg"] and content_type == "image/jpeg": file_type_enum = FileType.JPG # Store as JPG
    # Add TEXT as alias for TXT if needed based on your enum
    elif file_extension == ".txt" and file_type_enum is None: file_type_enum = FileType.TEXT

    if file_type_enum is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {original_filename} ({content_type}). Supported types: PDF, DOCX, TXT, PNG, JPG/JPEG."
        )
    # --- End File Type Validation ---

    # 1. Upload file to Blob Storage
    try:
        blob_name = await upload_file_to_blob(upload_file=file)
        if blob_name is None:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,"Failed to upload file to storage.")
    except Exception as e:
        logger.error(f"Error during file upload service call: {e}", exc_info=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,"An error occurred during file upload processing.")

    # 2. Create Document metadata record in DB
    now = datetime.now(timezone.utc)
    document_data = DocumentCreate(
        original_filename=original_filename,
        storage_blob_path=blob_name,
        file_type=file_type_enum,
        upload_timestamp=now,
        student_id=student_id,
        assignment_id=assignment_id,
        status=DocumentStatus.UPLOADED # Correctly uses Enum
    )
    created_document = await crud.create_document(document_in=document_data)
    if not created_document:
        # TODO: Consider deleting the uploaded blob if DB record creation fails
        logger.error(f"Failed to create document metadata record in DB for blob {blob_name}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,"Failed to save document metadata after upload.")

    # 3. Create initial Result record
    result_data = ResultCreate(
        score=None, status=ResultStatus.PENDING, result_timestamp=now, document_id=created_document.id
        # paragraph_results will be None by default from the model
    )
    created_result = await crud.create_result(result_in=result_data)
    if not created_result:
        logger.error(f"Failed to create initial pending result record for document {created_document.id}")
        # Decide if this should cause the whole upload request to fail - maybe not?

    # 4. TODO: Trigger background task for analysis here (using created_document.id)
    # For now, assessment is triggered manually via the /assess endpoint
    logger.info(f"Document {created_document.id} uploaded. Ready for assessment.")

    return created_document


@router.post(
    "/{document_id}/assess",
    response_model=Result, # Return the final Result object
    status_code=status.HTTP_200_OK, # Return 200 OK on successful assessment
    summary="Trigger AI Assessment and get Result (Protected)",
    description="Fetches document text, calls the external ML API for AI detection, "
                "updates the result/document status, and returns the final result. "
                "Requires authentication."
)
async def trigger_assessment(
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to trigger the AI assessment for a document.
    Fetches text, calls external API, updates DB, returns result.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to trigger assessment for document ID: {document_id}")

    # --- Get Document & Authorization Check ---
    document = await crud.get_document_by_id(document_id=document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document with ID {document_id} not found.")

    # TODO: Implement proper authorization check: Can user trigger assessment for this document?
    logger.warning(f"Authorization check needed for user {user_kinde_id} triggering assessment for document {document_id}")

    # Check if assessment can be triggered (e.g., only if UPLOADED or maybe ERROR)
    if document.status not in [DocumentStatus.UPLOADED, DocumentStatus.ERROR]:
        logger.warning(f"Document {document_id} status is '{document.status}'. Assessment cannot be triggered.")
        # Return the existing result instead of erroring if it's already completed/processing
        existing_result = await crud.get_result_by_document_id(document_id=document_id)
        if existing_result:
            # Return 200 OK with the existing result if already completed or processing
            if existing_result.status in [ResultStatus.COMPLETED, ResultStatus.ASSESSING]:
                 logger.info(f"Assessment already completed or in progress for doc {document_id}. Returning existing result.")
                 return existing_result
            else:
                 # If status is PENDING or ERROR, allow re-triggering below
                 pass
        else:
            # This case is odd (doc status implies assessment happened, but no result found)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Assessment cannot be triggered. Document status is {document.status}, but no result found."
            )

    # --- Update Status to PROCESSING ---
    await crud.update_document_status(document_id=document_id, status=DocumentStatus.PROCESSING)
    result = await crud.get_result_by_document_id(document_id=document_id)
    if result:
        # --- Pass dictionary directly to crud.update_result ---
        await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ASSESSING})
    else:
        # Handle case where result record didn't exist (should have been created on upload)
        logger.error(f"Result record missing for document {document_id} during assessment trigger.")
        # Create it now? Or raise error? Let's raise for now.
        await crud.update_document_status(document_id=document_id, status=DocumentStatus.ERROR) # Revert doc status
        raise HTTPException(status_code=500, detail="Internal error: Result record missing.")

    # --- Text Extraction ---
    extracted_text: Optional[str] = None
    try:
        # Convert file_type string back to Enum member if needed
        file_type_enum_member: Optional[FileType] = None
        if isinstance(document.file_type, str):
            for member in FileType:
                if member.value.lower() == document.file_type.lower():
                    file_type_enum_member = member
                    break
        elif isinstance(document.file_type, FileType):
            file_type_enum_member = document.file_type

        if file_type_enum_member is None:
            raise ValueError(f"Could not map file type '{document.file_type}' to enum.")

        # Check if type is supported for text extraction
        if file_type_enum_member not in [FileType.PDF, FileType.DOCX, FileType.TXT, FileType.TEXT]:
             raise ValueError(f"Text extraction not supported for file type: {document.file_type}")

        # Download bytes
        file_bytes = await download_blob_as_bytes(blob_name=document.storage_blob_path)
        if file_bytes is None:
            raise ValueError(f"Failed to download blob '{document.storage_blob_path}'")

        # Extract text
        extracted_text = extract_text_from_bytes(file_bytes=file_bytes, file_type=file_type_enum_member)
        if extracted_text is None:
             # Handle case where extraction returns None for valid but empty/unextractable files
             logger.warning(f"Text extraction returned None for document {document_id}. Treating as empty text.")
             extracted_text = "" # Set to empty string to proceed

        logger.info(f"Successfully extracted text ({len(extracted_text)} chars) for document {document_id}")

    except Exception as e:
        logger.error(f"Failed text extraction stage for document {document_id}: {e}", exc_info=True)
        # Update status to ERROR
        await crud.update_document_status(document_id=document_id, status=DocumentStatus.ERROR)
        # --- Pass dictionary directly to crud.update_result ---
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process document text: {e}")

    # --- Call External ML API ---
    ai_score: Optional[float] = None
    ml_label: Optional[str] = None
    ml_ai_generated: Optional[bool] = None
    ml_human_generated: Optional[bool] = None
    # --- Store the RAW list of paragraph dicts ---
    ml_paragraph_results_raw: Optional[List[Dict[str, Any]]] = None
    # --- END ---

    try:
        ml_payload = {"text": extracted_text if extracted_text else ""}
        headers = {'Content-Type': 'application/json'}

        logger.info(f"Calling ML API for document {document_id} at {ML_API_URL}")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(ML_API_URL, json=ml_payload, headers=headers)
            response.raise_for_status()

            ml_response_data = response.json()
            logger.info(f"ML API response for document {document_id}: {ml_response_data}")

            if isinstance(ml_response_data, dict):
                ml_ai_generated = ml_response_data.get("ai_generated")
                ml_human_generated = ml_response_data.get("human_generated")
                if not isinstance(ml_ai_generated, bool): ml_ai_generated = None
                if not isinstance(ml_human_generated, bool): ml_human_generated = None

                if ("results" in ml_response_data and isinstance(ml_response_data["results"], list)):
                    # --- Store the raw list directly ---
                    ml_paragraph_results_raw = ml_response_data["results"]
                    logger.info(f"Extracted {len(ml_paragraph_results_raw)} raw paragraph results.")
                    # --- END ---

                    if len(ml_paragraph_results_raw) > 0 and isinstance(ml_paragraph_results_raw[0], dict):
                        first_result = ml_paragraph_results_raw[0]
                        ml_label = first_result.get("label")
                        if not isinstance(ml_label, str): ml_label = None

                        score_value = first_result.get("probability")
                        if isinstance(score_value, (int, float)):
                            ai_score = float(score_value)
                            ai_score = max(0.0, min(1.0, ai_score))
                            logger.info(f"Extracted overall AI probability score from first paragraph: {ai_score}")
                        else:
                            logger.warning(f"ML API returned non-numeric probability in first result: {score_value}")
                            ai_score = None
                    else: logger.warning("ML API 'results' list is empty or first item is not a dict.")
                else: logger.warning("ML API response missing 'results' list.")
            else: raise ValueError("ML API response format unexpected (not a dict).")

    # ... (error handling for ML API call remains the same) ...
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error calling ML API for document {document_id}: {e.response.status_code} - {e.response.text}", exc_info=False)
        await crud.update_document_status(document_id=document_id, status=DocumentStatus.ERROR)
        # --- Pass dictionary directly to crud.update_result ---
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error communicating with AI detection service: {e.response.status_code}")
    except ValueError as e:
        logger.error(f"Error processing ML API response for document {document_id}: {e}", exc_info=True)
        await crud.update_document_status(document_id=document_id, status=DocumentStatus.ERROR)
        # --- Pass dictionary directly to crud.update_result ---
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process AI detection result: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during ML API call or processing for document {document_id}: {e}", exc_info=True)
        await crud.update_document_status(document_id=document_id, status=DocumentStatus.ERROR)
        # --- Pass dictionary directly to crud.update_result ---
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get AI detection result: {e}")


    # --- Update DB with Result ---
    final_result: Optional[Result] = None
    try:
        if result:
            # --- MODIFIED: Prepare a simple dictionary for the update ---
            update_payload_dict = {
                "status": ResultStatus.COMPLETED.value, # Store enum value
                "result_timestamp": datetime.now(timezone.utc)
            }
            if ai_score is not None: update_payload_dict["score"] = ai_score
            if ml_label is not None: update_payload_dict["label"] = ml_label
            if ml_ai_generated is not None: update_payload_dict["ai_generated"] = ml_ai_generated
            if ml_human_generated is not None: update_payload_dict["human_generated"] = ml_human_generated
            # Add the raw list of paragraph dicts if available
            if ml_paragraph_results_raw is not None:
                 # Basic check: ensure it's a list of dicts before saving
                 if isinstance(ml_paragraph_results_raw, list) and all(isinstance(item, dict) for item in ml_paragraph_results_raw):
                     update_payload_dict["paragraph_results"] = ml_paragraph_results_raw
                 else:
                     logger.error(f"ml_paragraph_results_raw is not a list of dicts for doc {document_id}. Skipping save.")

            # --- Call CRUD update function with the dictionary ---
            final_result = await crud.update_result(result_id=result.id, update_data=update_payload_dict) # Pass dict

            if final_result:
                await crud.update_document_status(document_id=document_id, status=DocumentStatus.COMPLETED)
                logger.info(f"Assessment completed for document {document_id}. Score: {ai_score}, Label: {ml_label}, Paragraphs: {len(ml_paragraph_results_raw or [])}")
            else:
                 logger.error(f"Failed to update result record {result.id} in database, crud.update_result returned None.")
                 raise ValueError("Failed to update result record in database.")
        else:
             logger.error(f"Result object became None unexpectedly for document {document_id}.")
             raise ValueError("Result record unavailable for update.")

    # ... (error handling for DB update remains the same) ...
    except Exception as e:
        logger.error(f"Failed to update database after successful ML API call for document {document_id}: {e}", exc_info=True)
        await crud.update_document_status(document_id=document_id, status=DocumentStatus.ERROR)
        # --- Pass dictionary directly to crud.update_result ---
        if result: await crud.update_result(result_id=result.id, update_data={"status": ResultStatus.ERROR})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save assessment result.")


    if not final_result:
         logger.error(f"Final result object is None after attempting DB update for doc {document_id}.")
         raise HTTPException(status_code=500, detail="Failed to retrieve final result after update.")

    return final_result # Return the complete, updated Result object


@router.get(
    "/{document_id}",
    response_model=Document,
    status_code=status.HTTP_200_OK,
    summary="Get a specific document's metadata by ID (Protected)",
    description="Retrieves the metadata of a single document using its unique ID. Requires authentication."
)
async def read_document(
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """Protected endpoint to retrieve specific document metadata by its ID."""
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read document ID: {document_id}")
    document = await crud.get_document_by_id(document_id=document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document with ID {document_id} not found.")
    # TODO: Add fine-grained authorization check
    return document

@router.get(
    "/{document_id}/text",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Get extracted plain text content of a document (Protected)",
    description="Downloads the document file from storage, extracts its plain text content "
                "for supported types (PDF, DOCX, TXT), and returns it. Requires authentication.",
    responses={
        200: {"content": {"text/plain": {"schema": {"type": "string"}}}},
        404: {"description": "Document not found"},
        415: {"description": "Text extraction not supported for this file type"},
        500: {"description": "Error downloading file or during text extraction"},
    }
)
async def get_document_text(
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
) -> str:
    """
    Protected endpoint to retrieve the extracted plain text for a specific document.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} requesting extracted text for document ID: {document_id}")

    # 1. Fetch document metadata
    document = await crud.get_document_by_id(document_id=document_id)
    if document is None:
        logger.warning(f"Document {document_id} not found for text extraction request by user {user_kinde_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document with ID {document_id} not found.")

    # 2. TODO: Authorization Check
    logger.warning(f"Authorization check needed for user {user_kinde_id} accessing text of document {document_id}")

    # Convert file_type string (from DB/model) back to Enum member if possible
    file_type_str = document.file_type
    file_type_enum_member: Optional[FileType] = None
    if isinstance(file_type_str, str):
        for member in FileType:
            if member.value.lower() == file_type_str.lower():
                file_type_enum_member = member
                break
    elif isinstance(file_type_str, FileType): # If it somehow already is an Enum
        file_type_enum_member = file_type_str

    # 3. Check if file type is supported for text extraction (using the Enum member)
    if file_type_enum_member not in [FileType.PDF, FileType.DOCX, FileType.TXT, FileType.TEXT]:
        logger.warning(f"Text extraction requested for unsupported file type '{file_type_str}' for document {document_id}")
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Text extraction not supported for file type: {file_type_str}"
        )

    # Ensure we have a valid enum member before proceeding
    if file_type_enum_member is None:
        logger.error(f"Could not map file_type string '{file_type_str}' back to FileType enum for doc {document_id}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error processing file type.")

    # 4. Download file bytes from blob storage
    blob_name = document.storage_blob_path
    file_bytes: Optional[bytes] = None
    try:
        logger.debug(f"Attempting to download blob: {blob_name}")
        file_bytes = await download_blob_as_bytes(blob_name=blob_name)
        if file_bytes is None:
            raise ValueError(f"Blob '{blob_name}' not found or download returned None.")
        logger.debug(f"Successfully downloaded {len(file_bytes)} bytes for blob: {blob_name}")
    except Exception as e:
        logger.error(f"Failed to download blob '{blob_name}' for document {document_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve document content from storage.")

    # 5. Extract text using the helper function
    if file_bytes is None: # Safety check
        logger.error(f"File bytes are None after download for blob {blob_name}, cannot extract text.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error retrieving file content.")

    logger.debug(f"Attempting text extraction for document {document_id} (type: {file_type_str})") # Log string
    extracted_text = extract_text_from_bytes(file_bytes=file_bytes, file_type=file_type_enum_member) # Pass Enum

    # 6. Handle extraction result and return response
    if extracted_text is None:
        logger.error(f"Text extraction function returned None for document {document_id} (type: {file_type_str})")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to extract text content from the document.")
    else:
        logger.info(f"Successfully extracted and returning text for document {document_id} ({len(extracted_text)} chars)")
        # Return empty string if extraction yielded nothing, otherwise the text
        return str(extracted_text) if extracted_text is not None else ""

@router.get(
    "/",
    response_model=List[Document],
    status_code=status.HTTP_200_OK,
    summary="Get a list of documents (Protected)",
    description="Retrieves a list of document metadata records, with optional filtering, sorting, and pagination. Requires authentication."
)
async def read_documents(
    student_id: Optional[uuid.UUID] = Query(None, description="Filter by student UUID"),
    assignment_id: Optional[uuid.UUID] = Query(None, description="Filter by assignment UUID"),
    status: Optional[DocumentStatus] = Query(None, description="Filter by document processing status"),
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records to return"),
    sort_by: Optional[str] = Query(None, description="Field to sort by (e.g., 'upload_timestamp', 'original_filename')"),
    sort_order: int = Query(-1, description="Sort order: 1 for ascending, -1 for descending"),
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """Protected endpoint to retrieve a list of document metadata."""
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read list of documents with filters/sorting.")
    # TODO: Add authorization logic (filter results based on user's access)

    # Validate sort_order if provided explicitly
    if sort_order not in [1, -1]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid sort_order value. Use 1 for ascending or -1 for descending.")

    documents = await crud.get_all_documents(
        student_id=student_id,
        assignment_id=assignment_id,
        status=status,
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order
    )
    return documents

@router.put(
    "/{document_id}/status",
    response_model=Document,
    status_code=status.HTTP_200_OK,
    summary="Update a document's processing status (Protected)",
    description="Updates the processing status of a document. Requires authentication. (Typically for internal use)."
)
async def update_document_processing_status(
    document_id: uuid.UUID,
    status_update: DocumentUpdate, # Expects {'status': DocumentStatus}
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """Protected endpoint to update the status of a document."""
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to update status for document ID: {document_id} to {status_update.status}")
    # TODO: Add authorization check: Who can update status?
    if status_update.status is None: raise HTTPException(status.HTTP_400_BAD_REQUEST, "Status field is required.")
    # Assuming update_document_status expects the Enum member
    updated_document = await crud.update_document_status(document_id=document_id, status=status_update.status)
    if updated_document is None: raise HTTPException(status.HTTP_404_NOT_FOUND, f"Document {document_id} not found.")
    # Log the string value from the input
    logger.info(f"Document {document_id} status updated to {status_update.status.value} by user {user_kinde_id}.")
    return updated_document

@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document record (Protected)",
    description="Deletes a document metadata record. Requires authentication. Does NOT delete the file from Blob Storage."
)
async def delete_document_metadata(
    document_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """Protected endpoint to delete document metadata."""
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to delete document metadata ID: {document_id}")
    # TODO: Add authorization check: Who can delete document metadata?
    # TODO: Consider triggering blob deletion (perhaps via background task)
    deleted = await crud.delete_document(document_id=document_id) # Add hard_delete=True/False if needed
    if not deleted: raise HTTPException(status.HTTP_404_NOT_FOUND, f"Document metadata {document_id} not found.")
    logger.info(f"Document metadata {document_id} deleted by user {user_kinde_id}.")
    return None # Return None for 204 response

@router.post(
    "/batch",
    response_model=BatchWithDocuments,
    status_code=status.HTTP_201_CREATED,
    summary="Upload multiple documents in a batch (Protected)",
    description="Uploads multiple files, creates a batch record, and queues them for processing. Requires authentication."
)
async def upload_batch(
    student_id: uuid.UUID = Form(..., description="Internal ID of the student associated with the documents"),
    assignment_id: uuid.UUID = Form(..., description="ID of the assignment associated with the documents"),
    files: List[UploadFile] = File(..., description="The document files to upload (PDF, DOCX, TXT, PNG, JPG)"),
    priority: BatchPriority = Form(BatchPriority.NORMAL, description="Processing priority for the batch"),
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to upload multiple documents in a batch, store them,
    create metadata, and initiate the analysis process.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to upload batch of {len(files)} documents")

    # Create batch record
    batch_data = BatchCreate(
        user_id=user_kinde_id,
        total_files=len(files),
        status=BatchStatus.UPLOADING,
        priority=priority
    )
    batch = await crud.create_batch(batch_in=batch_data)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create batch record"
        )

    documents = []
    failed_files = []

    # Process each file
    for file in files:
        try:
            original_filename = file.filename or "unknown_file"
            
            # File type validation
            content_type = file.content_type
            file_extension = os.path.splitext(original_filename)[1].lower()
            file_type_enum = None
            
            if file_extension == ".pdf" and content_type == "application/pdf": 
                file_type_enum = FileType.PDF
            elif file_extension == ".docx" and content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document": 
                file_type_enum = FileType.DOCX
            elif file_extension == ".txt" and content_type == "text/plain": 
                file_type_enum = FileType.TXT
            elif file_extension == ".png" and content_type == "image/png": 
                file_type_enum = FileType.PNG
            elif file_extension in [".jpg", ".jpeg"] and content_type == "image/jpeg": 
                file_type_enum = FileType.JPG

            if file_type_enum is None:
                failed_files.append({
                    "filename": original_filename,
                    "error": f"Unsupported file type: {content_type}"
                })
                continue

            # Upload to blob storage
            blob_name = await upload_file_to_blob(upload_file=file)
            if not blob_name:
                failed_files.append({
                    "filename": original_filename,
                    "error": "Failed to upload to storage"
                })
                continue

            # Create document record
            now = datetime.now(timezone.utc)
            # Convert priority enum to integer
            priority_value = 0  # Default
            if priority == BatchPriority.LOW:
                priority_value = 0
            elif priority == BatchPriority.NORMAL:
                priority_value = 1
            elif priority == BatchPriority.HIGH:
                priority_value = 2
            elif priority == BatchPriority.URGENT:
                priority_value = 3

            document_data = DocumentCreate(
                original_filename=original_filename,
                storage_blob_path=blob_name,
                file_type=file_type_enum,
                upload_timestamp=now,
                student_id=student_id,
                assignment_id=assignment_id,
                status=DocumentStatus.UPLOADED,
                batch_id=batch.id,
                queue_position=len(documents) + 1,
                processing_priority=priority_value  # Use the converted integer value
            )
            
            document = await crud.create_document(document_in=document_data)
            if not document:
                failed_files.append({
                    "filename": original_filename,
                    "error": "Failed to create document record"
                })
                continue

            # Create initial result record
            result_data = ResultCreate(
                score=None,
                status=ResultStatus.PENDING,
                result_timestamp=now,
                document_id=document.id
            )
            await crud.create_result(result_in=result_data)
            
            documents.append(document)

        except Exception as e:
            logger.error(f"Error processing file {file.filename}: {str(e)}")
            failed_files.append({
                "filename": file.filename,
                "error": str(e)
            })

    # Update batch status
    batch_update = BatchUpdate(
        completed_files=0,
        failed_files=len(failed_files),
        status=BatchStatus.QUEUED if documents else BatchStatus.ERROR,
        error_message=f"Failed to process {len(failed_files)} files" if failed_files else None
    )
    updated_batch = await crud.update_batch(batch_id=batch.id, batch_in=batch_update)

    if not documents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Failed to process any files in the batch",
                "failed_files": failed_files
            }
        )

    return BatchWithDocuments(
        **updated_batch.dict(),
        document_ids=[doc.id for doc in documents]
    )

@router.get(
    "/batch/{batch_id}",
    response_model=BatchWithDocuments,
    status_code=status.HTTP_200_OK,
    summary="Get batch upload status (Protected)",
    description="Get the status of a batch upload including all documents in the batch. Requires authentication."
)
async def get_batch_status(
    batch_id: uuid.UUID,
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to get the status of a batch upload and its documents.
    """
    user_kinde_id = current_user_payload.get("sub")
    
    # Get batch
    batch = await crud.get_batch_by_id(batch_id=batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch with ID {batch_id} not found"
        )

    # Authorization check
    if batch.user_id != user_kinde_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this batch"
        )

    # Get all documents in batch
    documents = await crud.get_documents_by_batch_id(batch_id=batch_id)
    
    return BatchWithDocuments(
        **batch.dict(),
        document_ids=[doc.id for doc in documents]
    )

