# app/models/class_group.py
# Use ConfigDict from Pydantic V2
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime, timezone # Import timezone for default factory
import uuid

# Shared base properties
class ClassGroupBase(BaseModel):
    """Base class for ClassGroup with common attributes."""
    class_name: str = Field(..., description="Name of the class (e.g., 'Math 101', '9th Grade English')")
    academic_year: str = Field(..., description="Academic year (e.g., '2024-2025')")
    school_id: uuid.UUID = Field(..., description="Reference to the School this class belongs to")
    teacher_id: uuid.UUID = Field(..., description="Reference to the Teacher who teaches this class")

    # Add Pydantic V2 model config here if needed for base behavior,
    # otherwise it will be inherited by models below.
    # model_config = ConfigDict(...)


# Properties required on creation
class ClassGroupCreate(ClassGroupBase):
    """Model for creating a new ClassGroup."""
    # Student IDs are typically managed after the class is created,
    # but allow optional setting at creation if needed by API design.
    # Assuming based on spec doc, it's optional on ClassGroup itself
    student_ids: Optional[List[uuid.UUID]] = Field(default_factory=list, description="List of student IDs enrolled in the class (Optional at creation)")
    pass


# Properties stored in DB
class ClassGroupInDBBase(ClassGroupBase):
    """Base model for ClassGroup data stored in the database."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id", description="Unique identifier for the class group")
    # student_ids should be non-optional when reading from DB, default to empty list
    student_ids: List[uuid.UUID] = Field(default_factory=list, description="List of student IDs enrolled in the class")
    # Use default_factory for consistent timestamp generation
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When the class group was created")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When the class group was last updated")
    # deleted_at: Optional[datetime] = Field(None) # Add if using soft delete

    # --- UPDATED: Pydantic V2 Configuration ---
    model_config = ConfigDict(
        populate_by_name=True,      # Allow population by alias ('_id')
        from_attributes=True,       # Allow creating model from DB attributes (like orm_mode)
        arbitrary_types_allowed=True# Allow types like UUID with certain drivers
    )
    # --- END UPDATE ---

# Final model representing a ClassGroup read from DB
class ClassGroup(ClassGroupInDBBase):
    """Complete ClassGroup model for data retrieved from the database."""
    # Inherits id, timestamps, student_ids, and base fields
    pass

# Model for updating (e.g., changing name, adding/removing students)
class ClassGroupUpdate(BaseModel):
    """Model for updating an existing ClassGroup."""
    class_name: Optional[str] = Field(None, description="Name of the class group") # Use Field with None default
    academic_year: Optional[str] = Field(None, description="Academic year (e.g., '2024-2025')")
    # Allow updating the full list of students via the update operation
    student_ids: Optional[List[uuid.UUID]] = Field(None, description="List of student IDs in this class")
    # Typically we wouldn't change these, but allow if needed
    teacher_id: Optional[uuid.UUID] = Field(None, description="Reference to the Teacher who teaches this class")
    school_id: Optional[uuid.UUID] = Field(None, description="Reference to the School this class belongs to")

    # No specific config needed for update model usually