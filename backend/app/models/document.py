# app/models/document.py

import uuid
from pydantic import BaseModel, Field, field_validator # Added field_validator
from datetime import datetime, timezone # Added timezone
from typing import Optional

# Import Enums with correct names
from app.models.enums import FileType, DocumentStatus # Corrected: DocumentStatus

# --- Base Model ---
class DocumentBase(BaseModel):
    original_filename: str = Field(..., description="Original name of the uploaded file")
    storage_blob_path: str = Field(..., description="Path or name of the file in blob storage")
    file_type: FileType = Field(..., description="Detected type of the file (PDF, DOCX, etc.)")
    upload_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: DocumentStatus = Field(default=DocumentStatus.UPLOADED, description="Processing status of the document")
    student_id: uuid.UUID = Field(..., description="ID of the student associated with this document")
    assignment_id: uuid.UUID = Field(..., description="ID of the assignment associated with this document")

    # Ensure status is stored/retrieved as its value if needed, handled by Config below
    # @field_validator('status', mode='before')
    # @classmethod
    # def validate_status_enum(cls, v):
    #     if isinstance(v, DocumentStatus):
    #         return v.value
    #     return v

# --- Model for Creation (received via API) ---
class DocumentCreate(DocumentBase):
    # All fields from Base are needed for creation
    pass

# --- Model for Update (received via API) ---
# Typically only status might be updated via API, or maybe other fields later
class DocumentUpdate(BaseModel):
    status: Optional[DocumentStatus] = Field(None, description="New processing status")
    # Add other updatable fields here if needed, e.g.:
    # original_filename: Optional[str] = None

# --- Model for Database (includes internal fields) ---
class DocumentInDBBase(DocumentBase):
    id: uuid.UUID = Field(alias="_id") # Use '_id' alias for MongoDB
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Add soft delete field if using that pattern consistently
    deleted_at: Optional[datetime] = Field(default=None)

    class Config:
        from_attributes = True # Pydantic V2 replaces orm_mode
        populate_by_name = True # Allow using '_id' alias
        arbitrary_types_allowed = True # If using complex types like ObjectId directly
        use_enum_values = True # Ensure enums are handled correctly (e.g., stored as values)

# --- Model for API Response ---
class Document(DocumentInDBBase):
    # This model represents the data returned by the API
    pass

