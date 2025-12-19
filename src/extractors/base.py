"""
Base extractor interface.

All extractors (Vision, OCR, etc.) implement this interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from src.schemas.common import DocumentType, ExtractionResult


class BaseExtractor(ABC):
    """Abstract base class for document extractors."""
    
    @abstractmethod
    async def classify_document(self, document_bytes: bytes, filename: str) -> DocumentType:
        """
        Classify the document type.
        
        Args:
            document_bytes: Raw document content
            filename: Original filename (may hint at type)
            
        Returns:
            Detected DocumentType
        """
        pass
    
    @abstractmethod
    async def extract(
        self,
        document_bytes: bytes,
        filename: str,
        document_type: Optional[DocumentType] = None,
    ) -> ExtractionResult:
        """
        Extract structured data from document.
        
        Args:
            document_bytes: Raw document content
            filename: Original filename
            document_type: If known, skip classification
            
        Returns:
            ExtractionResult with structured data
        """
        pass
    
    @abstractmethod
    async def extract_with_schema(
        self,
        document_bytes: bytes,
        filename: str,
        schema: dict[str, Any],
    ) -> ExtractionResult:
        """
        Extract data according to a custom schema.
        
        Args:
            document_bytes: Raw document content
            filename: Original filename
            schema: JSON schema describing expected output
            
        Returns:
            ExtractionResult with data matching schema
        """
        pass
