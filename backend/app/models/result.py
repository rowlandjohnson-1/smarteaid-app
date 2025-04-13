# app/models/result.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid
from app.models.enums import ResultStatus # Import Enum

# Shared base properties
class ResultBase(BaseModel):
    document_id: uuid.UUID = Field(...) # Link to the Document model
    # Score as float between 0.0 and 1.0 (representing percentage)
    score: Optional[float] = Field(None, ge=0.0, le=1.0)
    status: ResultStatus = ResultStatus.PENDING # Default status

# Properties required on creation (usually set by the AI process)
class ResultCreate(ResultBase):
    pass

# Properties stored in DB
class ResultInDBBase(ResultBase):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id")
    result_timestamp: datetime = Field(default_factory=datetime.utcnow) # Alias for created_at?
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        from_attributes = True

# Final model representing a Result read from DB
class Result(ResultInDBBase):
    pass

# Model for updating (mainly score and status)
class ResultUpdate(BaseModel):
    score: Optional[float] = Field(None, ge=0.0, le=1.0)
    status: Optional[ResultStatus] = None