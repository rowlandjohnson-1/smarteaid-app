# app/models/student.py
from pydantic import BaseModel, Field, constr, ConfigDict # Import ConfigDict for Pydantic V2
from typing import Optional
from datetime import datetime
import uuid

# Shared base properties
class StudentBase(BaseModel):
    first_name: str = Field(..., min_length=1, description="Student's first name")
    last_name: str = Field(..., min_length=1, description="Student's last name")

    # Optional external ID provided by the institution/user
    # Max length 16 chars. Needs a unique sparse index in MongoDB if provided.
    external_student_id: Optional[constr(strip_whitespace=True, max_length=16)] = Field(
        default=None,
        description="Optional external student ID (max 16 chars, unique if provided)"
    )
    descriptor: Optional[str] = Field(default=None, description="Optional descriptor or note about the student")
    year_group: Optional[str] = Field(default=None, description="Optional year group or grade level")

# Properties required on creation
class StudentCreate(StudentBase):
    # Inherits fields from StudentBase
    # Add school_id if needed at creation even if linked via ClassGroup
    # school_id: uuid.UUID # Or maybe not needed here if always added via Class
    pass

# Properties stored in DB - Intermediate Base including system fields
class StudentInDBBase(StudentBase):
    # Use 'id' in Python, map to '_id' in MongoDB.
    # default_factory ensures an ID is generated if not provided (e.g., during creation)
    # The CRUD 'create' function should ideally generate and set this explicitly.
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id", description="Internal unique identifier")

    # Timestamps should be set explicitly by CRUD operations
    # Making them non-optional here ensures they exist when reading from DB
    created_at: datetime = Field(..., description="Timestamp when the student record was created")
    updated_at: datetime = Field(..., description="Timestamp when the student record was last updated")

    # We link students to classes via the ClassGroup model's student_ids list

    # Pydantic V2 configuration
    model_config = ConfigDict(
        populate_by_name=True,       # Allow population by alias ('_id')
        from_attributes=True,        # Allow creating model from ORM attributes (like ORM mode)
        arbitrary_types_allowed=True # Useful for MongoDB types like UUID
    )

# Final model representing a Student read from DB
class Student(StudentInDBBase):
    # Inherits all fields from StudentInDBBase
    pass

# Model for updating - All fields are optional for partial updates
class StudentUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=1, description="Student's first name")
    last_name: Optional[str] = Field(default=None, min_length=1, description="Student's last name")
    external_student_id: Optional[constr(strip_whitespace=True, max_length=16)] = Field(
        default=None,
        description="Optional external student ID (max 16 chars, unique if provided)"
    )
    descriptor: Optional[str] = Field(default=None, description="Optional descriptor or note about the student")
    year_group: Optional[str] = Field(default=None, description="Optional year group or grade level")