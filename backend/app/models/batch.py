# app/models/batch.py

import uuid
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, List

from app.models.enums import BatchStatus, BatchPriority

class BatchBase(BaseModel):
    user_id: str = Field(..., description="ID of the user who created the batch (Kinde ID format)")
    total_files: int = Field(..., description="Total number of files in the batch")
    completed_files: int = Field(default=0, description="Number of files that completed processing")
    failed_files: int = Field(default=0, description="Number of files that failed processing")
    status: BatchStatus = Field(default=BatchStatus.CREATED, description="Current status of the batch")
    priority: BatchPriority = Field(default=BatchPriority.NORMAL, description="Processing priority of the batch")
    error_message: Optional[str] = Field(default=None, description="Error message if batch failed")

class BatchCreate(BatchBase):
    pass

class BatchUpdate(BaseModel):
    completed_files: Optional[int] = None
    failed_files: Optional[int] = None
    status: Optional[BatchStatus] = None
    error_message: Optional[str] = None

class BatchInDBBase(BatchBase):
    id: uuid.UUID = Field(alias="_id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    deleted_at: Optional[datetime] = Field(default=None)

    class Config:
        from_attributes = True
        populate_by_name = True
        arbitrary_types_allowed = True
        use_enum_values = True

class Batch(BatchInDBBase):
    pass

class BatchWithDocuments(Batch):
    document_ids: List[uuid.UUID] = Field(default_factory=list, description="List of document IDs in this batch")