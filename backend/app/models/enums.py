# app/models/enums.py
from enum import Enum

class TeacherRole(str, Enum):
    TEACHER = "teacher"
    TUTOR = "tutor"
    LECTURER = "lecturer"
    ADMIN = "admin"
    OTHER = "other"

class MarketingSource(str, Enum):
    GOOGLE = "Google"
    FACEBOOK = "Facebook"
    LINKEDIN = "Linkedin"
    CONFERENCE = "Conference"
    REFERRAL = "Referral"
    OTHER = "Other"

class FileType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    PNG = "png"
    JPG = "jpg"
    TXT = "txt" # Assuming plain text input is also stored as a 'document'

class ProcessingStatus(str, Enum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"

class ResultStatus(str, Enum):
    PENDING = "pending"
    ASSESSING = "assessing" # Or processing? Using your term.
    COMPLETED = "completed"
    ERROR = "error"