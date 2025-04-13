# app/models/assignment.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid

# Shared base properties
class AssignmentBase(BaseModel):
    assignment_name: str = Field(...)
    class_group_id: uuid.UUID # Link to the ClassGroup model
    due_date: Optional[datetime] = None

# Properties required on creation
class AssignmentCreate(AssignmentBase):
    pass

# Properties stored in DB
class AssignmentInDBBase(AssignmentBase):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        from_attributes = True

# Final model representing an Assignment read from DB
class Assignment(AssignmentInDBBase):
    pass

# Model for updating
class AssignmentUpdate(BaseModel):
    assignment_name: Optional[str] = None
    due_date: Optional[datetime] = None
    # Usually wouldn't change the class_group_id