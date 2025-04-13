# app/models/class_group.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid

# Shared base properties
class ClassGroupBase(BaseModel):
    class_name: str = Field(...)
    academic_year: str = Field(...) # e.g., "2024-2025"
    school_id: uuid.UUID # Link to the School model
    teacher_id: uuid.UUID # Link to the Teacher model

# Properties required on creation
class ClassGroupCreate(ClassGroupBase):
    # Student IDs likely added/managed separately, not at initial creation
    pass

# Properties stored in DB
class ClassGroupInDBBase(ClassGroupBase):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id")
    student_ids: List[uuid.UUID] = Field(default_factory=list) # List of internal Student IDs
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        from_attributes = True

# Final model representing a ClassGroup read from DB
class ClassGroup(ClassGroupInDBBase):
    pass

# Model for updating (e.g., changing name, adding/removing students)
class ClassGroupUpdate(BaseModel):
    class_name: Optional[str] = None
    academic_year: Optional[str] = None
    # Usually don't change school/teacher, manage students separately
    # student_ids: Optional[List[uuid.UUID]] = None # Add methods to manage students