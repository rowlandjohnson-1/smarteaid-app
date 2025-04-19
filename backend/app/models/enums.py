# app/models/enums.py

from enum import Enum

# --- User/Teacher Related Enums ---

class TeacherRole(str, Enum):
    """Enumeration for different roles a teacher/user might have."""
    TEACHER = "teacher"
    TUTOR = "tutor"
    LECTURER = "lecturer"
    ADMIN = "admin"
    OTHER = "other"

class MarketingSource(str, Enum):
    """Enumeration for how a user heard about the service."""
    GOOGLE = "Google"
    FACEBOOK = "Facebook"
    LINKEDIN = "Linkedin"
    CONFERENCE = "Conference"
    REFERRAL = "Referral"
    OTHER = "Other"

# --- Document/File Related Enums ---

class FileType(str, Enum):
    """Enumeration for supported document/file types."""
    PDF = "pdf"
    DOCX = "docx"
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg" # Added common alias
    TXT = "txt"
    TEXT = "text" # Added for potential copy-paste input type

class DocumentStatus(str, Enum):
    """Enumeration for the processing status of a document."""
    UPLOADED = "uploaded"   # File received and stored
    QUEUED = "queued"       # Queued for AI analysis
    PROCESSING = "processing" # Actively being analyzed by ML model
    COMPLETED = "completed"   # Analysis finished, result available
    ERROR = "error"         # An error occurred during processing

# --- Result Related Enums ---

class ResultStatus(str, Enum):
    """Enumeration for the status of an AI detection result."""
    PENDING = "pending"     # Analysis requested but not yet started/completed
    ASSESSING = "assessing"   # Analysis in progress
    COMPLETED = "completed"   # Analysis complete, score available
    ERROR = "error"         # Error during analysis, score may be unavailable

