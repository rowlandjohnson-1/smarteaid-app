# app/models/class_group.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid

# Shared base properties
class ClassGroupBase(BaseModel):
    """Base class for ClassGroup with common attributes."""
    class_name: str = Field(..., description="Name of the class (e.g., 'Math 101', '9th Grade English')")
    academic_year: str = Field(..., description="Academic year (e.g., '2024-2025')")
    school_id: uuid.UUID = Field(..., description="Reference to the School this class belongs to")
    teacher_id: uuid.UUID = Field(..., description="Reference to the Teacher who teaches this class")

# Properties required on creation
class ClassGroupCreate(ClassGroupBase):
    """Model for creating a new ClassGroup."""
    # Student IDs are typically managed after the class is created
    pass

# Properties stored in DB
class ClassGroupInDBBase(ClassGroupBase):
    """Base model for ClassGroup data stored in the database."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id", description="Unique identifier for the class group")
    student_ids: List[uuid.UUID] = Field(default_factory=list, description="List of student IDs enrolled in the class")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When the class group was created")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="When the class group was last updated")

    class Config:
        populate_by_name = True
        from_attributes = True

# Final model representing a ClassGroup read from DB
class ClassGroup(ClassGroupInDBBase):
    """Complete ClassGroup model for data retrieved from the database."""
    pass

# Model for updating (e.g., changing name, adding/removing students)
class ClassGroupUpdate(BaseModel):
    """Model for updating an existing ClassGroup."""
    class_name: Optional[str] = None
    academic_year: Optional[str] = None
    # Allow updating the full list of students via the update operation
    student_ids: Optional[List[uuid.UUID]] = None
    # Typically we wouldn't change these, but could be needed in some scenarios
    teacher_id: Optional[uuid.UUID] = None
    school_id: Optional[uuid.UUID] = None