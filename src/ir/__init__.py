"""
Document Intermediate Representation (IR) module.

This module provides structures for representing documents with full layout information,
including text blocks, bounding boxes, tables, and page metadata.
"""
from src.ir.document_ir import (
    BoundingBox,
    TextBlock,
    TableCell,
    Table,
    DocumentIR,
)
from src.ir.builder import IRBuilder

__all__ = [
    "BoundingBox",
    "TextBlock",
    "TableCell",
    "Table",
    "DocumentIR",
    "IRBuilder",
]
