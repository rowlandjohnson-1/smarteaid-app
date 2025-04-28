# app/models/teacher.py
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, List
from datetime import datetime, timezone
import uuid
# Assuming enums.py is in the same directory or accessible via path
from .enums import TeacherRole, MarketingSource

# Shared base properties
class TeacherBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100, description="Teacher's first name")
    last_name: str = Field(..., min_length=1, max_length=100, description="Teacher's last name")
    # Use EmailStr for validation
    email: EmailStr = Field(..., description="Teacher's email address")
    school_name: Optional[str] = Field(None, min_length=1, max_length=200, description="Name of the school the teacher belongs to")
    role: TeacherRole = Field(default=TeacherRole.TEACHER, description="The primary role of the teacher/user")
    how_did_you_hear: Optional[MarketingSource] = None
    description: Optional[str] = Field(None, description="Optional bio or description")
    country: Optional[str] = Field(None, description="Country of the teacher/school")
    state_county: Optional[str] = Field(None, description="State or County of the teacher/school")
    is_active: bool = Field(default=True, description="Whether the teacher account is active")

    model_config = ConfigDict(
        use_enum_values=True,
    )

# --- CORRECTED TeacherCreate ---
# Properties required on creation - Inherits from TeacherBase
class TeacherCreate(TeacherBase):
    # Inherits: first_name, last_name, email, role (with default), is_active (with default),
    #           how_did_you_hear (optional), description (optional)

    # Make fields required for creation that were optional in Base
    # The frontend validation already requires these.
    school_name: str = Field(..., min_length=1, max_length=200) # Make school_name required
    country: str = Field(...) # Make country required
    state_county: str = Field(...) # Make state_county required
    # Role is already required (with default) in Base.
    # Email is already required in Base.

    # Keep the example if useful
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com", # Inherited
                "school_name": "Example School", # Now required here
                "role": "teacher", # Inherited (uses default if not provided)
                "country": "United Kingdom", # Now required here
                "state_county": "London", # Now required here
                # "how_did_you_hear": "Google", # Example optional inherited field
                # "description": "Experienced educator", # Example optional inherited field
                # "is_active": True # Inherited (uses default if not provided)
            }
        }
    )
# --- END CORRECTION ---

# Properties stored in DB
class TeacherInDBBase(TeacherBase):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id")
    kinde_id: str = Field(..., description="Stored Kinde 'sub' identifier (used for lookups)")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        arbitrary_types_allowed=True,
        use_enum_values=True,
    )

# Final model representing a Teacher read from DB (API Response)
class Teacher(TeacherInDBBase):
    pass

# Model for updating (Profile Page uses this)
class TeacherUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    # email: Optional[EmailStr] = None # Email usually not updatable
    school_name: Optional[str] = Field(None, min_length=1, max_length=200)
    role: Optional[TeacherRole] = None
    description: Optional[str] = Field(None)
    country: Optional[str] = Field(None)
    state_county: Optional[str] = Field(None)
    is_active: Optional[bool] = Field(None)

    model_config = ConfigDict(
        use_enum_values=True,
    )

# Note: No closing ``` included here
