# app/models/assignment.py
from pydantic import BaseModel, Field, ConfigDict # Import ConfigDict for Pydantic V2
from typing import Optional
from datetime import datetime
import uuid

# Shared base properties
class AssignmentBase(BaseModel):
    assignment_name: str = Field(..., min_length=1, description="Name of the assignment")
    # Foreign key linking to the ClassGroup this assignment belongs to
    class_group_id: uuid.UUID = Field(..., description="ID of the ClassGroup this assignment belongs to")
    # Optional due date for the assignment
    due_date: Optional[datetime] = Field(default=None, description="Optional due date for the assignment")

# Properties required on creation
class AssignmentCreate(AssignmentBase):
    # Inherits all fields from AssignmentBase
    pass

# Properties stored in DB - Intermediate Base including system fields
class AssignmentInDBBase(AssignmentBase):
    # Use 'id' in Python, map to '_id' in MongoDB.
    # The CRUD 'create' function should explicitly generate and set this.
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id", description="Internal unique identifier")

    # Timestamps should be set explicitly by CRUD operations
    # Making them non-optional here ensures they exist when reading from DB
    created_at: datetime = Field(..., description="Timestamp when the assignment record was created")
    updated_at: datetime = Field(..., description="Timestamp when the assignment record was last updated")

    # Pydantic V2 configuration
    model_config = ConfigDict(
        populate_by_name=True,       # Allow population by alias ('_id')
        from_attributes=True,        # Allow creating model from ORM attributes (like ORM mode)
        arbitrary_types_allowed=True # Useful for MongoDB types like UUID
    )

# Final model representing an Assignment read from DB
class Assignment(AssignmentInDBBase):
    # Inherits all fields from AssignmentInDBBase
    pass

# Model for updating - All fields are optional for partial updates
# Note: class_group_id is intentionally omitted as per your version, assuming it shouldn't be updated.
class AssignmentUpdate(BaseModel):
    assignment_name: Optional[str] = Field(default=None, min_length=1, description="Name of the assignment")
    due_date: Optional[datetime] = Field(default=None, description="Optional due date for the assignment")