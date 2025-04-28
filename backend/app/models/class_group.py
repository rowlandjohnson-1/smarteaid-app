# app/models/class_group.py
# Use ConfigDict from Pydantic V2
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime, timezone # Import timezone for default factory
import uuid

# Shared base properties - REMOVED teacher_id
class ClassGroupBase(BaseModel):
    """Base class for ClassGroup with common attributes."""
    class_name: str = Field(..., description="Name of the class (e.g., 'Math 101', '9th Grade English')")
    academic_year: str = Field(..., description="Academic year (e.g., '2024-2025')")
    school_id: uuid.UUID = Field(..., description="Reference to the School this class belongs to")
    # teacher_id: uuid.UUID = Field(..., description="Reference to the Teacher who teaches this class") # REMOVED from Base

# Properties required on creation - teacher_id is no longer inherited
class ClassGroupCreate(ClassGroupBase):
    """Model for creating a new ClassGroup."""
    # Student IDs are typically managed after the class is created,
    # but allow optional setting at creation if needed by API design.
    # Assuming based on spec doc, it's optional on ClassGroup itself
    student_ids: Optional[List[uuid.UUID]] = Field(default_factory=list, description="List of student IDs enrolled in the class (Optional at creation)")
    pass


# Properties stored in DB - ADDED teacher_id back explicitly here
class ClassGroupInDBBase(ClassGroupBase):
    """Base model for ClassGroup data stored in the database."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id", description="Unique identifier for the class group")
    # Add teacher_id back here as it's stored in the DB
    teacher_id: uuid.UUID = Field(..., description="Reference to the Teacher who teaches this class")
    student_ids: List[uuid.UUID] = Field(default_factory=list, description="List of student IDs enrolled in the class")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When the class group was created")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When the class group was last updated")
    # deleted_at: Optional[datetime] = Field(None) # Add if using soft delete

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        arbitrary_types_allowed=True
    )

# Final model representing a ClassGroup read from DB
class ClassGroup(ClassGroupInDBBase):
    """Complete ClassGroup model for data retrieved from the database."""
    pass

# Model for updating (e.g., changing name, adding/removing students)
class ClassGroupUpdate(BaseModel):
    """Model for updating an existing ClassGroup."""
    class_name: Optional[str] = Field(None, description="Name of the class group")
    academic_year: Optional[str] = Field(None, description="Academic year (e.g., '2024-2025')")
    student_ids: Optional[List[uuid.UUID]] = Field(None, description="List of student IDs in this class")
    # teacher_id: Optional[uuid.UUID] = Field(None, description="Reference to the Teacher who teaches this class") # Keep commented unless needed
    # school_id: Optional[uuid.UUID] = Field(None, description="Reference to the School this class belongs to") # Keep commented unless needed
