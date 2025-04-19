# app/services/blob_storage.py

import logging
import uuid
import os
from typing import Optional

# --- Azure SDK Imports ---
# Use the async client for FastAPI compatibility
from azure.storage.blob.aio import BlobServiceClient, ContainerClient, BlobClient
from azure.core.exceptions import AzureError
from azure.storage.blob import ContentSettings # To set content type

# --- FastAPI Imports (for type hinting) ---
from fastapi import UploadFile

# --- Config Imports ---
# Adjust path based on your structure
from ..core.config import AZURE_BLOB_CONNECTION_STRING, AZURE_BLOB_CONTAINER_NAME

# --- Logging Setup ---
logger = logging.getLogger(__name__)
# Ensure logging is configured elsewhere (e.g., main.py or logging config)
# logging.basicConfig(level=logging.INFO) # Avoid basicConfig here

# --- Blob Service Client (Cached) ---
# We can create the client once and reuse it, as it handles pooling.
# Using a simple global variable for simplicity here.
_blob_service_client: Optional[BlobServiceClient] = None

def get_blob_service_client() -> Optional[BlobServiceClient]:
    """Gets or creates the async BlobServiceClient instance."""
    global _blob_service_client
    if _blob_service_client is None:
        if not AZURE_BLOB_CONNECTION_STRING:
            logger.error("Azure Blob Storage connection string is not configured.")
            return None
        try:
            # Create client from connection string
            _blob_service_client = BlobServiceClient.from_connection_string(
                conn_str=AZURE_BLOB_CONNECTION_STRING
            )
            logger.info("BlobServiceClient initialized.")
        except ValueError as e:
            logger.error(f"Invalid Blob Storage connection string format: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize BlobServiceClient: {e}", exc_info=True)
            return None
    return _blob_service_client

# --- File Upload Function ---

async def upload_file_to_blob(
    upload_file: UploadFile, # Use FastAPI's UploadFile type
    # Optionally pass content_type if not reliably inferred from filename
    # content_type: Optional[str] = None
) -> Optional[str]:
    """
    Uploads a file to Azure Blob Storage in the configured container.

    Args:
        upload_file: The UploadFile object received from the FastAPI request.
                     Contains filename, content_type, and file stream.

    Returns:
        The unique name of the blob created in the container if successful,
        otherwise None.
    """
    service_client = get_blob_service_client()
    if not service_client or not AZURE_BLOB_CONTAINER_NAME:
        logger.error("Blob storage service client or container name not available.")
        return None

    # Extract original filename and determine extension
    original_filename = upload_file.filename or "unknown_file"
    _, file_extension = os.path.splitext(original_filename)

    # Generate a unique blob name to prevent overwrites and collisions
    blob_name = f"{uuid.uuid4()}{file_extension}"
    content_type = upload_file.content_type # Get content type from UploadFile

    logger.info(f"Attempting to upload '{original_filename}' as blob '{blob_name}' to container '{AZURE_BLOB_CONTAINER_NAME}'...")

    try:
        # Get a client for the specific container
        container_client: ContainerClient = service_client.get_container_client(AZURE_BLOB_CONTAINER_NAME)

        # Get a client for the specific blob (file) to be uploaded
        blob_client: BlobClient = container_client.get_blob_client(blob_name)

        # Get the file stream from the UploadFile object
        file_stream = upload_file.file

        # Upload the stream directly
        # Set content type for proper handling by browsers/clients later
        content_settings = ContentSettings(content_type=content_type) if content_type else None

        await blob_client.upload_blob(
            data=file_stream,
            overwrite=True, # Safe because blob_name is unique UUID
            content_settings=content_settings
        )

        logger.info(f"Successfully uploaded '{original_filename}' to blob: {blob_name}")
        return blob_name # Return the unique name assigned to the blob

    except AzureError as e:
        logger.error(f"Azure error during blob upload for {blob_name}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during blob upload for {blob_name}: {e}", exc_info=True)
        return None
    # Note: BlobServiceClient and ContainerClient don't need explicit closing here
    # when created within the function scope like this, unless using 'async with'.
    # If the client were managed globally or via lifespan, closing would be handled there.

# --- Optional: Add functions for download, delete, list etc. later if needed ---
# async def delete_blob(blob_name: str) -> bool: ...
# async def get_blob_sas_url(blob_name: str) -> Optional[str]: ...

