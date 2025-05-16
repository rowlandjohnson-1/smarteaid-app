# backend/tests/functional/api/v1/endpoints/test_documents_endpoint.py
import pytest
import uuid
import time # For unique names or timestamps if needed
from typing import Dict, Any, Optional
from unittest.mock import AsyncMock # Import AsyncMock
from httpx import AsyncClient, ASGITransport # Required for making requests to the app
from fastapi import FastAPI, status, UploadFile
from pytest_mock import MockerFixture
from io import BytesIO
from datetime import datetime, timezone # Added timezone

import app.services.blob_storage as blob_storage_module # ALIASED IMPORT

# Import app and settings (adjust path if your conftest modifies sys.path differently)
from backend.app.main import app as fastapi_app 
from backend.app.core.config import settings
from app.core.security import get_current_user_payload # For dependency override
from backend.app.models.document import Document, DocumentStatus # For asserting response and types
from backend.app.models.result import Result, ResultStatus # For asserting result creation
from backend.app.models.enums import FileType # For asserting file type

# Mark all tests in this module to use pytest-asyncio
pytestmark = pytest.mark.asyncio

# Use the app_with_mock_auth fixture from the main conftest.py if available and suitable,
# or define a similar one here for document-specific auth mocking if needed.
# For now, we'll assume app_with_mock_auth can be used or we'll mock 'get_current_user_payload' directly.

@pytest.mark.asyncio
async def test_upload_document_success(
    app: FastAPI, # Using the standard app fixture, will override auth manually
    mocker: MockerFixture
):
    """
    Test successful document upload (POST /documents/upload).
    Mocks authentication, blob storage, and CRUD operations.
    """
    api_prefix = settings.API_V1_PREFIX
    upload_url = f"{api_prefix}/documents/upload"

    # 1. Mock Authentication
    test_user_kinde_id = f"user_kinde_id_doc_upload_{uuid.uuid4()}"
    mock_auth_payload = {
        "sub": test_user_kinde_id,
        "iss": "mock_issuer",
        "aud": ["mock_audience"],
        "exp": time.time() + 3600,
        "iat": time.time(),
        "roles": ["teacher"] 
    }
    
    # Override the dependency directly for this test's app instance
    # Assuming 'app' fixture provides a fresh app instance for each test,
    # or that pytest handles teardown correctly.
    async def override_get_current_user_payload() -> Dict[str, Any]:
        return mock_auth_payload
    
    original_override = app.dependency_overrides.get(get_current_user_payload)
    app.dependency_overrides[get_current_user_payload] = override_get_current_user_payload

    # 2. Prepare Test Data
    student_uuid = uuid.uuid4()
    assignment_uuid = uuid.uuid4()
    mock_file_content = b"This is a test PDF content."
    mock_file_name = "test_document.pdf"
    mock_blob_name = f"test_blob_{uuid.uuid4()}.pdf"
    now_utc = datetime.now(timezone.utc) # Define a consistent datetime for mocks

    # 3. Mock External Service Calls and CRUD Operations
    
    # Mock blob storage upload using AsyncMock
    mock_upload_blob = mocker.patch.object( # CHANGED: Use patch.object
        blob_storage_module,          # Use the aliased module import
        'upload_file_to_blob',              # Name of the attribute (function) to patch
        new_callable=AsyncMock, 
        return_value=mock_blob_name
    )

    # Mock crud.create_document
    created_doc_id = uuid.uuid4() 
    mock_created_document_data = {
        "id": created_doc_id,
        "original_filename": mock_file_name,
        "storage_blob_path": mock_blob_name,
        "file_type": FileType.PDF.value, 
        "upload_timestamp": now_utc, 
        "student_id": student_uuid,
        "assignment_id": assignment_uuid,
        "status": DocumentStatus.UPLOADED.value, 
        "teacher_id": test_user_kinde_id,
        "character_count": None,
        "word_count": None,
        "created_at": now_utc, 
        "updated_at": now_utc  
    }
    mock_created_document_instance = Document(**mock_created_document_data)
    # Mock crud.create_document using AsyncMock as it's an async CRUD function
    mock_crud_create_doc = mocker.patch(
        'backend.app.api.v1.endpoints.documents.crud.create_document',
        new_callable=AsyncMock, # Use AsyncMock for async functions
        return_value=mock_created_document_instance
    )

    # Mock crud.create_result using AsyncMock
    created_result_id = uuid.uuid4()
    mock_created_result_data = {
        "id": created_result_id,
        "score": None,
        "status": ResultStatus.PENDING.value,
        "result_timestamp": now_utc, 
        "document_id": created_doc_id, 
        "teacher_id": test_user_kinde_id,
        "paragraph_results": [],
        "error_message": None,
        "created_at": now_utc, 
        "updated_at": now_utc  
    }
    mock_created_result_instance = Result(**mock_created_result_data)
    mock_crud_create_result = mocker.patch(
        'backend.app.api.v1.endpoints.documents.crud.create_result',
        new_callable=AsyncMock, # Use AsyncMock for async functions
        return_value=mock_created_result_instance
    )

    # 4. Prepare form data and file for upload
    form_data = {
        "student_id": str(student_uuid),
        "assignment_id": str(assignment_uuid)
    }
    files_data = {
        "file": (mock_file_name, BytesIO(mock_file_content), "application/pdf")
    }

    # 5. Make the API Request
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            upload_url,
            data=form_data, 
            files=files_data,  
        )
    
    # 6. Assertions
    assert response.status_code == status.HTTP_201_CREATED, (
        f"Expected 201 Created, got {response.status_code}. Response: {response.text}"
    )

    response_data = response.json()

    assert response_data["original_filename"] == mock_file_name
    assert response_data["storage_blob_path"] == mock_blob_name
    assert response_data["file_type"] == FileType.PDF.value
    assert response_data["student_id"] == str(student_uuid)
    assert response_data["assignment_id"] == str(assignment_uuid)
    assert response_data["status"] == DocumentStatus.UPLOADED.value
    assert response_data["teacher_id"] == test_user_kinde_id
    assert "_id" in response_data 
    assert response_data["_id"] == str(created_doc_id) 

    # Verify mock calls
    mock_upload_blob.assert_called_once()
    call_args_upload_blob = mock_upload_blob.call_args[0]
    assert isinstance(call_args_upload_blob[0], UploadFile)
    assert call_args_upload_blob[0].filename == mock_file_name

    mock_crud_create_doc.assert_called_once()
    call_args_create_doc = mock_crud_create_doc.call_args[1]
    document_in_arg = call_args_create_doc['document_in']
    assert document_in_arg.original_filename == mock_file_name
    assert document_in_arg.storage_blob_path == mock_blob_name
    assert document_in_arg.file_type == FileType.PDF 
    assert document_in_arg.student_id == student_uuid
    assert document_in_arg.assignment_id == assignment_uuid
    assert document_in_arg.status == DocumentStatus.UPLOADED
    assert document_in_arg.teacher_id == test_user_kinde_id

    mock_crud_create_result.assert_called_once()
    call_args_create_result = mock_crud_create_result.call_args[1]
    result_in_arg = call_args_create_result['result_in']
    assert result_in_arg.document_id == created_doc_id
    assert result_in_arg.teacher_id == test_user_kinde_id
    assert result_in_arg.status == ResultStatus.PENDING

    # Clean up dependency override
    if original_override:
        app.dependency_overrides[get_current_user_payload] = original_override
    else:
        del app.dependency_overrides[get_current_user_payload]

# @pytest.mark.asyncio
# async def test_get_document(test_client: AsyncClient):
# # Example test for getting a document
# # Assume a document with ID 'some_doc_id' exists and belongs to 'some_teacher_id'
# # headers = {"Authorization": "Bearer your_test_token_if_needed"} # If auth is needed
# # response = await test_client.get("/api/v1/documents/some_doc_id?teacher_id=some_teacher_id", headers=headers)
# # assert response.status_code == 200
# # response_data = response.json()
# # assert response_data["id"] == "some_doc_id"
# pass 