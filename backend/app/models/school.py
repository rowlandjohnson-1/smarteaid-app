# app/models/school.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid

# Shared base properties
class SchoolBase(BaseModel):
    school_name: str = Field(..., min_length=1)
    school_state_region: Optional[str] = None
    school_country: str = Field(..., min_length=2) # e.g., ISO country code or name

# Properties required on creation
class SchoolCreate(SchoolBase):
    pass

# Properties stored in DB
class SchoolInDBBase(SchoolBase):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True # Allow alias for _id
        from_attributes = True # Pydantic V2 alias for orm_mode

# Final model representing a School read from DB
class School(SchoolInDBBase):
    pass

# Model for updating
class SchoolUpdate(BaseModel):
    school_name: Optional[str] = None
    school_state_region: Optional[str] = None
    school_country: Optional[str] = None