"""
Common schema models shared across all document types.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    """Supported document types."""
    # Sports
    BASKETBALL = "basketball"
    HOCKEY = "hockey"
    WRESTLING = "wrestling"
    GYMNASTICS = "gymnastics"
    BASEBALL = "baseball"
    FOOTBALL = "football"
    VOLLEYBALL = "volleyball"
    SOCCER = "soccer"
    GOLF = "golf"
    TENNIS = "tennis"
    TRACK = "track"
    CROSS_COUNTRY = "cross_country"
    SWIMMING = "swimming"
    
    # Legal/Public Notices
    ASSUMED_NAME = "assumed_name"
    SUMMONS = "summons"
    PUBLIC_NOTICE = "public_notice"
    
    # School
    HONOR_ROLL = "honor_roll"
    GPA_REPORT = "gpa_report"
    
    # Generic
    UNKNOWN = "unknown"
    TABULAR = "tabular"


class ExtractionResult(BaseModel):
    """Result of document extraction."""
    success: bool
    document_type: DocumentType
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in classification")
    data: dict[str, Any] = Field(default_factory=dict)
    raw_text: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    
    # Metadata
    source_filename: Optional[str] = None
    extraction_timestamp: datetime = Field(default_factory=datetime.utcnow)
    model_used: str = "claude-sonnet-4-20250514"
    tokens_used: Optional[int] = None


class RenderResult(BaseModel):
    """Result of template rendering."""
    success: bool
    newspaper_text: str
    template_id: str
    extraction: ExtractionResult
    warnings: list[str] = Field(default_factory=list)


class DocumentMetadata(BaseModel):
    """Metadata about an uploaded document."""
    filename: str
    content_type: str
    size_bytes: int
    page_count: int = 1
    detected_type: Optional[DocumentType] = None
    upload_timestamp: datetime = Field(default_factory=datetime.utcnow)
