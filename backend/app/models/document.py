# app/models/document.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid
from app.models.enums import FileType, ProcessingStatus # Import Enums

# Shared base properties
class DocumentBase(BaseModel):
    original_filename: str = Field(...)
    storage_blob_path: str = Field(...) # Path in Azure Blob Storage
    file_type: FileType # Use the Enum
    status: ProcessingStatus = ProcessingStatus.UPLOADED # Default status
    student_id: uuid.UUID # Link to the Student model
    assignment_id: uuid.UUID # Link to the Assignment model
    # We can infer class_group/teacher via assignment/student if needed

# Properties required on creation (usually set internally after upload)
class DocumentCreate(DocumentBase):
    pass

# Properties stored in DB
class DocumentInDBBase(DocumentBase):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id")
    upload_timestamp: datetime = Field(default_factory=datetime.utcnow) # Use alias?
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        from_attributes = True

# Final model representing a Document read from DB
class Document(DocumentInDBBase):
    pass

# Model for updating (mainly status)
class DocumentUpdate(BaseModel):
    status: Optional[ProcessingStatus] = None
    original_filename: Optional[str] = None # Maybe allow renaming?
    # Other fields usually immutable after creation