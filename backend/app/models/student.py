# app/models/student.py
from pydantic import BaseModel, Field, EmailStr, constr, ConfigDict # Import ConfigDict for Pydantic V2, EmailStr
from typing import Optional
from datetime import datetime
import uuid

# Shared base properties
class StudentBase(BaseModel):
    first_name: str = Field(..., min_length=1, description="Student's first name")
    last_name: str = Field(..., min_length=1, description="Student's last name")

    # --- ADDED email field ---
    email: Optional[EmailStr] = Field(default=None, description="Student's email address (Optional)")
    # -------------------------

    # Optional external ID provided by the institution/user
    # Using 'external_student_id' which is clearer than just 'student_id' from spec
    external_student_id: Optional[constr(strip_whitespace=True, max_length=16)] = Field( # type: ignore
        default=None,
        # Using alias="external_student_id" is only needed if the Python variable name
        # was different (e.g., if we used 'student_id' in Python for the external one).
        # Since the variable name matches the intended DB field name, alias isn't strictly needed here.
        description="Optional external student ID (max 16 chars, unique if provided)"
    )
    descriptor: Optional[str] = Field(default=None, description="Optional descriptor or note about the student")
    year_group: Optional[str] = Field(default=None, description="Optional year group or grade level")

    # Pydantic V2 model config
    model_config = ConfigDict(
        from_attributes=True,      # Allow creating schema from DB model object
        populate_by_name=True,     # Allow population by alias (e.g., '_id' for 'id')
    )


# Properties required on creation
class StudentCreate(StudentBase):
    # Inherits fields from StudentBase, including the new optional email
    pass

# Properties stored in DB - Intermediate Base including system fields
class StudentInDBBase(StudentBase):
    # Use 'id' in Python, map to '_id' in MongoDB via alias.
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id", description="Internal unique identifier")

    # Timestamps should be set explicitly by CRUD operations
    created_at: datetime = Field(..., description="Timestamp when the student record was created")
    updated_at: datetime = Field(..., description="Timestamp when the student record was last updated")

    # Pydantic V2 configuration inherited includes from_attributes=True, populate_by_name=True
    # arbitrary_types_allowed=True is often needed for MongoDB UUIDs etc.
    model_config = ConfigDict(
       arbitrary_types_allowed=True,
       # Inherit others by default, but can re-declare if needed
       # populate_by_name=True,
       # from_attributes=True,
    )


# Final model representing a Student read from DB (returned by API)
class Student(StudentInDBBase):
    # Inherits all fields from StudentInDBBase: id, created_at, updated_at,
    # and all fields from StudentBase (first_name, last_name, email, etc.)
    pass

# Model for updating - All fields are optional for partial updates
class StudentUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=1, description="Student's first name")
    last_name: Optional[str] = Field(default=None, min_length=1, description="Student's last name")
    # --- ADDED email field ---
    email: Optional[EmailStr] = Field(default=None, description="Student's email address")
    # -------------------------
    external_student_id: Optional[constr(strip_whitespace=True, max_length=16)] = Field( # type: ignore
        default=None,
        description="Optional external student ID (max 16 chars, unique if provided)"
    )
    descriptor: Optional[str] = Field(default=None, description="Optional descriptor or note about the student")
    year_group: Optional[str] = Field(default=None, description="Optional year group or grade level")