# app/models/user.py
from pydantic import BaseModel, EmailStr, Field, ConfigDict # Added ConfigDict
from typing import Optional, List
from datetime import datetime, timezone # Added timezone
import uuid # Keep for potential use, but ID likely comes from Kinde

# Basic properties shared by all User variations
class UserBase(BaseModel):
    # Using EmailStr ensures the email field is validated as an email
    email: EmailStr = Field(...) # Ellipsis means this field is required
    full_name: Optional[str] = None # Optional field
    is_active: bool = True
    # Roles etc. will be added later or handled via Kinde claims

    # Pydantic V2 model config
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

# Properties required when creating a user (might be handled by Kinde)
class UserCreate(UserBase):
    # Often, user creation details come from the auth provider (Kinde)
    # This model might be simple initially
    # Kinde ID will be set separately
    pass

# Properties allowed when updating a user
class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    # is_deleted is not updated via this model
    # Add other updatable fields here

# Base model for users stored in the database (includes common DB fields)
class UserInDBBase(UserBase):
    # ID field should store the Kinde User ID (string)
    # Removed default_factory as the ID comes from Kinde
    id: str = Field(..., alias="_id", description="Kinde User ID (Primary Key)") # MODIFIED

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # --- RBAC Changes Below ---
    is_deleted: bool = Field(default=False, description="Flag for soft delete status") # ADDED
    # --- RBAC Changes Above ---

    # Inherit model_config from Base, add specifics if needed
    model_config = ConfigDict(
        # from_attributes = True # Inherited
        # populate_by_name = True # Inherited
        arbitrary_types_allowed = True # Allow complex types if needed later
    )

# Final User model representing data coming from the database
class User(UserInDBBase):
    # Inherits all fields including is_deleted
    pass

# You might also have a model for user data returned by the API
# class UserPublic(UserBase):
#     id: str # Exclude sensitive fields if necessary
