from pydantic import BaseModel, HttpUrl, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime

class DocumentType(str, Enum):
    WEBPAGE = "webpage"
    PDF = "pdf"

class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class FlagStatus(str, Enum):
    FLAGGED = "flagged"
    REVIEWED = "reviewed"
    UPDATED = "updated"

# Request Models
class BulkIndexRequest(BaseModel):
    urls: List[HttpUrl]

class FlagRequest(BaseModel):
    changed_law: str
    what_changed: Optional[str] = None
    similarity_threshold: float = 0.3

class UnflagRequest(BaseModel):
    document_ids: List[str]

class UpdateFlagStatusRequest(BaseModel):
    document_id: str
    status: FlagStatus

# Response Models
class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str

class ChangeSuggestion(BaseModel):
    section_text: str
    issue: str
    suggested_change: str
    confidence: float

class FlaggedDocument(BaseModel):
    document_id: str
    url: str
    title: str
    flagged_for_law: str
    what_changed: Optional[str] = None
    change_suggestions: List[ChangeSuggestion] = []
    status: FlagStatus = FlagStatus.FLAGGED
    confidence: float
    flagged_at: datetime
    reviewed_at: Optional[datetime] = None

class FlagResponse(BaseModel):
    job_id: str
    status: str
    total_documents_found: int
    message: str

class FlaggedListResponse(BaseModel):
    flagged_documents: List[FlaggedDocument]
    total: int