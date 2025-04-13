# app/models/student.py
from pydantic import BaseModel, Field, constr
from typing import Optional
from datetime import datetime
import uuid

# Shared base properties
class StudentBase(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    # Store the external ID if provided, limit its length
    external_student_id: Optional[constr(max_length=16)] = None
    descriptor: Optional[str] = None
    year_group: Optional[str] = None

# Properties required on creation
class StudentCreate(StudentBase):
    # Add school_id if needed at creation even if linked via ClassGroup
    # school_id: uuid.UUID # Or maybe not needed here if always added via Class
    pass

# Properties stored in DB
class StudentInDBBase(StudentBase):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id") # Our internal unique ID
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    # We link students to classes via the ClassGroup model

    class Config:
        populate_by_name = True
        from_attributes = True

# Final model representing a Student read from DB
class Student(StudentInDBBase):
    pass

# Model for updating
class StudentUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    external_student_id: Optional[constr(max_length=16)] = None
    descriptor: Optional[str] = None
    year_group: Optional[str] = None