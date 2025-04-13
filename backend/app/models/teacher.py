# app/models/teacher.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
import uuid
from app.models.enums import TeacherRole, MarketingSource # Import Enums

# Shared base properties
class TeacherBase(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    how_did_you_hear: MarketingSource # Use the Enum
    role: TeacherRole                 # Use the Enum
    description: Optional[str] = None
    school_id: Optional[uuid.UUID] = None # Link to School (UUID)
    is_active: bool = True
    # We might add email here if it's separate from Kinde login ID

# Properties required on creation (user_id likely comes after Kinde signup)
class TeacherCreate(TeacherBase):
    pass # Add required fields if different from Base, maybe email if needed

# Properties stored in DB
class TeacherInDBBase(TeacherBase):
    user_id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id") # Our internal ID
    kinde_id: Optional[str] = None # Store the ID from Kinde authentication
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        from_attributes = True

# Final model representing a Teacher read from DB
class Teacher(TeacherInDBBase):
    pass

# Model for updating
class TeacherUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    description: Optional[str] = None
    school_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None
    # Role / how_did_you_hear usually aren't updated, but could be added