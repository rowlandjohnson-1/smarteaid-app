 # app/models/user.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
import uuid # For generating IDs if not using MongoDB ObjectId

# Basic properties shared by all User variations
class UserBase(BaseModel):
    # Using EmailStr ensures the email field is validated as an email
    email: EmailStr = Field(...) # Ellipsis means this field is required
    full_name: Optional[str] = None # Optional field
    is_active: bool = True
    # We will add roles, school associations, etc., later

# Properties required when creating a user (might be handled by Kinde)
class UserCreate(UserBase):
    # Often, user creation details come from the auth provider (Kinde)
    # This model might be simple initially
    pass

# Properties allowed when updating a user
class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    # Add other updatable fields here

# Base model for users stored in the database (includes common DB fields)
class UserInDBBase(UserBase):
    # Assuming we use standard string UUIDs for IDs
    # If using MongoDB ObjectId, this needs adjustment (e.g., using alias)
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id") # Map 'id' to MongoDB's '_id'
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
         # Allows mapping MongoDB's '_id' field to our 'id' field
         populate_by_name = True
         # Handles alias for '_id' field correctly
         # alias_generator = lambda field_name: "_id" if field_name == "id" else field_name
         # Pydantic v2 uses from_attributes instead of orm_mode
         from_attributes = True

# Final User model representing data coming from the database
class User(UserInDBBase):
    pass # Inherits all fields from UserInDBBase

# You might also have a model for user data returned by the API
# class UserPublic(UserBase):
#     id: str # Exclude sensitive fields if necessary
