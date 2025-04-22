# app/models/teacher.py
from pydantic import BaseModel, EmailStr, Field, ConfigDict # Added ConfigDict
from typing import Optional, List
from datetime import datetime, timezone # Added timezone
import uuid
# Assuming enums.py is in the same directory or accessible via path
from .enums import TeacherRole, MarketingSource

# Shared base properties
class TeacherBase(BaseModel):
    first_name: str = Field(..., min_length=1, description="Teacher's first name")
    last_name: str = Field(..., min_length=1, description="Teacher's last name")
    # Assuming 'how_did_you_hear' is set during a different process (e.g., signup)
    # If it needs to be part of the profile form, add it here and to TeacherUpdate
    # how_did_you_hear: Optional[MarketingSource] = None
    role: Optional[TeacherRole] = Field(None, description="The primary role of the teacher/user") # Made optional, can be required
    description: Optional[str] = Field(None, description="Optional bio or description")
    school_id: Optional[uuid.UUID] = Field(None, description="UUID of the school the teacher belongs to") # Link to School (UUID)

    # --- NEW Fields added based on ProfilePage.jsx ---
    country: Optional[str] = Field(None, description="Country of the teacher/school")
    state_county: Optional[str] = Field(None, description="State or County of the teacher/school")
    # --- End NEW Fields ---

    is_active: bool = Field(default=True, description="Whether the teacher account is active")
    # Email might be managed by Kinde, but can be stored for reference if needed
    # email: Optional[EmailStr] = Field(None, description="Teacher's email address")

    # Add Pydantic V2 model config here if needed for base behavior
    model_config = ConfigDict(
        use_enum_values=True, # Store enum values (strings) instead of members
    )


# Properties required on creation (user_id likely comes after Kinde signup)
# This might be simpler if profile details are added *after* initial Kinde signup
class TeacherCreate(TeacherBase):
    # You might require certain fields here that are optional in Base
    # For example, maybe first_name and last_name are required on creation
    first_name: str
    last_name: str
    # If email is needed at creation:
    # email: EmailStr
    # kinde_id: str # Kinde ID must be provided when creating the linked teacher record

# Properties stored in DB
class TeacherInDBBase(TeacherBase):
    # Use user_id as the primary identifier, aliased to _id in MongoDB
    user_id: uuid.UUID = Field(..., alias="_id", description="Internal unique identifier (matches Kinde user ID if possible)")
    # kinde_id might be redundant if user_id *is* the kinde 'sub', but included per original model
    kinde_id: Optional[str] = Field(None, description="Stored Kinde 'sub' identifier, if different from user_id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Pydantic V2 configuration
    model_config = ConfigDict(
        populate_by_name=True,       # Allow population by alias ('_id')
        from_attributes=True,        # Allow creating model from DB attributes (like ORM mode)
        arbitrary_types_allowed=True, # Useful for MongoDB types like UUID
        use_enum_values=True,        # Store/retrieve enum values
    )

# Final model representing a Teacher read from DB (API Response)
class Teacher(TeacherInDBBase):
    # Inherits all fields
    pass

# Model for updating (Profile Page uses this)
class TeacherUpdate(BaseModel):
    # All fields are optional for partial updates
    first_name: Optional[str] = Field(None, min_length=1)
    last_name: Optional[str] = Field(None, min_length=1)
    role: Optional[TeacherRole] = Field(None) # Allow updating role
    description: Optional[str] = Field(None)
    school_id: Optional[uuid.UUID] = Field(None) # Allow changing school association
    country: Optional[str] = Field(None) # Allow updating country
    state_county: Optional[str] = Field(None) # Allow updating state/county
    is_active: Optional[bool] = Field(None) # Allow activating/deactivating

    # Pydantic V2 configuration
    model_config = ConfigDict(
        use_enum_values=True, # Ensure enums are handled correctly
    )
