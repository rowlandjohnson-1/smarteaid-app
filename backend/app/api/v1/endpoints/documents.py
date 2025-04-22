# app/api/v1/endpoints/documents.py

import uuid
import logging
import os # Needed for path operations (splitext)
from typing import List, Optional, Dict, Any
from fastapi import (
    APIRouter, HTTPException, status, Query, Depends,
    UploadFile, File, Form
)
# Add PlainTextResponse for the new endpoint's return type
from fastapi.responses import PlainTextResponse
from datetime import datetime, timezone

# Import models
# Adjust path based on your structure if needed
from ....models.document import Document, DocumentCreate, DocumentUpdate
from ....models.result import ResultCreate, ResultUpdate
# Ensure FileType is imported along with other enums
from ....models.enums import DocumentStatus, ResultStatus, FileType

# Import CRUD functions
from ....db import crud # Assuming crud functions are in app/db/crud.py

# Import Authentication Dependency
from ....core.security import get_current_user_payload # Adjust path

# Import Blob Storage Service (upload is used, assume download exists)
from ....services.blob_storage import upload_file_to_blob, download_blob_as_bytes # Adjusted path, added download assumption

# Import Text Extraction Service
from ....services.text_extraction import extract_text_from_bytes # Adjusted path

# Setup logger
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)

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
    # ... (upload_document function code remains the same) ...
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
    )
    created_result = await crud.create_result(result_in=result_data)
    if not created_result:
         logger.error(f"Failed to create initial pending result record for document {created_document.id}")
         # Decide if this should cause the whole upload request to fail - maybe not?

    # 4. TODO: Trigger background task for analysis here (using created_document.id)
    logger.info(f"Document {created_document.id} uploaded. Background analysis task should be triggered.")

    return created_document


@router.post(
    "/{document_id}/assess",
    # ... (trigger_assessment function code remains the same) ...
    status_code=status.HTTP_202_ACCEPTED, # 202 Accepted indicates processing started
    summary="Trigger AI Assessment (Simulated - Protected)",
    description="Updates the document and result status to indicate analysis has started. "
                "Does NOT actually call the ML API in this version. Requires authentication."
)
async def trigger_assessment(
    document_id: uuid.UUID,
    # === Add Authentication Dependency ===
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """
    Protected endpoint to simulate triggering the AI assessment for a document.
    Updates status fields in the database.
    """
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to trigger assessment for document ID: {document_id}")

    # --- Authorization Check ---
    document = await crud.get_document_by_id(document_id=document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Document with ID {document_id} not found.")
    # TODO: Implement proper authorization check: Can user trigger assessment for this document?
    logger.warning(f"Authorization check needed for user {user_kinde_id} triggering assessment for document {document_id}")
    # --- End Authorization Check ---

    # Check against the Enum member directly
    if document.status not in [DocumentStatus.UPLOADED, DocumentStatus.ERROR]:
         # Log the string value if needed
         logger.warning(f"Document {document_id} status is '{document.status}'. Cannot re-trigger assessment.")
         return {"message": f"Assessment already initiated or completed for document {document_id}."}

    # 1. Update Document status to QUEUED
    updated_doc = await crud.update_document_status(document_id=document_id, status=DocumentStatus.QUEUED)
    if not updated_doc:
        logger.error(f"Failed to update document {document_id} status to QUEUED.")
        raise HTTPException(status_code=500, detail="Failed to update document status.")

    # 2. Update associated Result status to ASSESSING
    result = await crud.get_result_by_document_id(document_id=document_id)
    if result:
        result_update_data = ResultUpdate(status=ResultStatus.ASSESSING)
        updated_result = await crud.update_result(result_id=result.id, result_in=result_update_data)
        if not updated_result:
             logger.error(f"Failed to update result status to ASSESSING for document {document_id}, result {result.id}")
    else:
         logger.error(f"No result record found for document {document_id} when triggering assessment.")
         # Optionally create one here if it should always exist

    logger.info(f"Simulated assessment triggered for document {document_id}. Status -> QUEUED.")
    return {"message": "Assessment process initiated."}


@router.get(
    "/{document_id}",
    # ... (read_document function code remains the same) ...
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Document with ID {document_id} not found.")
    # TODO: Add fine-grained authorization check
    return document

# --- MODIFIED ENDPOINT FOR TEXT EXTRACTION ---
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

    # --- MODIFICATION START ---
    # Convert file_type string (from DB/model) back to Enum member if possible,
    # needed for the check below and for passing to extract_text_from_bytes
    file_type_str = document.file_type # Assuming document.file_type holds the string like "pdf"
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
         # Log the string value for clarity
         logger.warning(f"Text extraction requested for unsupported file type '{file_type_str}' for document {document_id}")
         raise HTTPException(
             status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
             detail=f"Text extraction not supported for file type: {file_type_str}"
         )

    # Ensure we have a valid enum member before proceeding
    if file_type_enum_member is None:
        logger.error(f"Could not map file_type string '{file_type_str}' back to FileType enum for doc {document_id}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error processing file type.")
    # --- MODIFICATION END ---


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

    # --- MODIFIED: Pass the Enum member to the extraction function ---
    logger.debug(f"Attempting text extraction for document {document_id} (type: {file_type_str})") # Log string
    extracted_text = extract_text_from_bytes(file_bytes=file_bytes, file_type=file_type_enum_member) # Pass Enum
    # --- END MODIFICATION ---

    # 6. Handle extraction result and return response
    if extracted_text is None:
        # --- MODIFIED: Log the string file type ---
        logger.error(f"Text extraction function returned None for document {document_id} (type: {file_type_str})")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to extract text content from the document.")
    else:
        logger.info(f"Successfully extracted and returning text for document {document_id} ({len(extracted_text)} chars)")
        return str(extracted_text) if extracted_text is not None else ""

# --- END MODIFIED TEXT ENDPOINT ---


@router.get(
    "/",
    # ... (read_documents function code remains the same - already fixed) ...
    response_model=List[Document],
    status_code=status.HTTP_200_OK,
    summary="Get a list of documents (Protected)",
    description="Retrieves a list of document metadata records, with optional filtering and pagination. Requires authentication."
)
async def read_documents(
    student_id: Optional[uuid.UUID] = Query(None, description="Filter by student UUID"),
    assignment_id: Optional[uuid.UUID] = Query(None, description="Filter by assignment UUID"),
    status: Optional[DocumentStatus] = Query(None, description="Filter by document processing status"),
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    current_user_payload: Dict[str, Any] = Depends(get_current_user_payload)
):
    """Protected endpoint to retrieve a list of document metadata."""
    user_kinde_id = current_user_payload.get("sub")
    logger.info(f"User {user_kinde_id} attempting to read list of documents with filters.")
    # TODO: Add authorization logic (filter results based on user's access)
    # ----- CORRECTED CALL: Removed db=None -----
    documents = await crud.get_all_documents(
        student_id=student_id, assignment_id=assignment_id, status=status, skip=skip, limit=limit
    )
    # -----------------------------------------
    # NOTE: Ensure get_all_documents internally handles Pydantic validation correctly
    # if it returns raw DB data that needs conversion/validation.
    return documents

@router.put(
    "/{document_id}/status",
    # ... (update_document_processing_status function code remains the same) ...
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
    # ... (delete_document_metadata function code remains the same) ...
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