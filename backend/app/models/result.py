# app/models/result.py
from pydantic import BaseModel, Field, ConfigDict # Added ConfigDict
from typing import Optional
from datetime import datetime, timezone # Added timezone
import uuid
from app.models.enums import ResultStatus # Import Enum

# Shared base properties
class ResultBase(BaseModel):
    document_id: uuid.UUID = Field(..., description="Link to the Document model")
    # Score as float between 0.0 and 1.0 (representing percentage)
    score: Optional[float] = Field(None, ge=0.0, le=1.0, description="AI detection score (probability)")
    status: ResultStatus = Field(default=ResultStatus.PENDING, description="Status of the analysis result")

    # --- NEW FIELDS to store from ML API response ---
    label: Optional[str] = Field(None, description="Classification label from the ML API (e.g., Human-Written, AI-Generated)")
    ai_generated: Optional[bool] = Field(None, description="Boolean flag indicating if ML API classified as AI-generated")
    human_generated: Optional[bool] = Field(None, description="Boolean flag indicating if ML API classified as human-generated")
    # --- END NEW FIELDS ---


# Properties required on creation (usually set internally)
class ResultCreate(ResultBase):
    # Inherits all fields from ResultBase
    # Typically, only document_id and status=PENDING are set initially.
    # Score and other fields are added later.
    pass

# Properties stored in DB
class ResultInDBBase(ResultBase):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id", description="Internal unique identifier for the result")
    # Use result_timestamp for consistency with spec, default to now
    result_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the result was generated or last updated")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the result record was created")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when the result record was last updated")
    deleted_at: Optional[datetime] = Field(default=None) # For soft delete

    # Pydantic V2 Config
    model_config = ConfigDict(
        populate_by_name=True,          # Allow using '_id' alias
        from_attributes=True,           # Allow creating from DB object attributes
        arbitrary_types_allowed=True,   # Allow UUID etc.
        use_enum_values=True            # Store/retrieve enums by their value
    )

# Final model representing a Result read from DB (API Response)
class Result(ResultInDBBase):
    # Inherits all fields
    pass

# Model for updating (mainly score, status, and new ML fields)
class ResultUpdate(BaseModel):
    score: Optional[float] = Field(None, ge=0.0, le=1.0)
    status: Optional[ResultStatus] = None
    # --- NEW FIELDS for update ---
    label: Optional[str] = None
    ai_generated: Optional[bool] = None
    human_generated: Optional[bool] = None
    # --- END NEW FIELDS ---
    # Update result_timestamp when updating the result
    result_timestamp: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Pydantic V2 Config
    model_config = ConfigDict(
        use_enum_values=True
    )

