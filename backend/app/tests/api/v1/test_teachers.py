# app/tests/api/v1/test_teachers.py
import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient  # For DB checks
from app.core.config import settings  # To get API prefix

# Mark all tests in this module to use pytest-asyncio
pytestmark = pytest.mark.asyncio

# Define a sample teacher payload for reuse
sample_teacher_payload = {
    "first_name": "Api",
    "last_name": "Tester",
    "user_id": "kinde|testuser12345",  # Example Kinde ID
    "how_did_you_hear": "LinkedIn",
    "role": "teacher",
    "description": "Teacher created via API test",
    # "school_id": "some_school_uuid" # Optional: Add if needed and handle school creation
}

async def test_create_teacher_success(
    async_client: AsyncClient, db: AsyncIOMotorClient, mocker
):
    """
    Test successful creation of a teacher via POST /teachers.
    """
    # --- Arrange ---
    # Mock the dependency that checks the user token/payload
    # Assuming your endpoint uses 'get_current_user_payload' from deps
    # Adjust the path 'app.api.deps.get_current_user_payload' if it's different
    mock_user_payload = {
        "sub": sample_teacher_payload["user_id"], # Kinde usually uses 'sub' for user ID
        "iss": "mock_issuer",
        "aud": ["mock_audience"],
        "roles": ["teacher"] # Add roles if your endpoint checks them
        # Add any other claims your dependency might check
    }
    mocker.patch("app.api.deps.get_current_user_payload", return_value=mock_user_payload)

    # --- Act ---
    # Make the API request to create the teacher
    response = await async_client.post(
        f"{settings.API_V1_STR}/teachers",
        json=sample_teacher_payload
    )

    # --- Assert ---
    # 1. Check the HTTP status code (e.g., 200 OK or 201 Created)
    # Adjust based on what your endpoint actually returns on success
    assert response.status_code == 200 or response.status_code == 201

    # 2. Check the response body
    response_data = response.json()
    assert response_data["user_id"] == sample_teacher_payload["user_id"]
    assert response_data["first_name"] == sample_teacher_payload["first_name"]
    assert response_data["last_name"] == sample_teacher_payload["last_name"]
    assert response_data["role"] == sample_teacher_payload["role"]
    # Add checks for other fields returned in the response
    assert "_id" in response_data # Check for MongoDB ID presence

    # 3. Check if the teacher was actually saved in the database
    # Note: Using 'db' fixture which connects to the TEST database
    created_teacher = await db["teachers"].find_one({"user_id": sample_teacher_payload["user_id"]})
    assert created_teacher is not None
    assert created_teacher["first_name"] == sample_teacher_payload["first_name"]
    # Add more DB checks if needed

# --- TODO: Add more tests ---
# test_create_teacher_missing_fields() -> Expect 422
# test_create_teacher_unauthorized() -> Expect 401/403 (mock dependency accordingly)
# test_get_teachers_empty()
# test_get_teachers_with_data()
# test_get_single_teacher_success()
# test_get_single_teacher_not_found() -> Expect 404
# test_update_teacher_success()
# test_update_teacher_not_found() -> Expect 404
# test_delete_teacher_success()
# test_delete_teacher_not_found() -> Expect 404 