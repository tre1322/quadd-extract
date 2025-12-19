"""
Document Intermediate Representation (IR) data structures.

Provides classes for representing documents with full layout information including
bounding boxes, text blocks, tables, and page metadata.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple


@dataclass
class BoundingBox:
    """
    Normalized bounding box in 0-1 coordinate space.

    Coordinates are normalized to page dimensions to make layout patterns
    transferable across different resolutions and page sizes.
    """
    x0: float  # Left edge (0-1)
    y0: float  # Top edge (0-1)
    x1: float  # Right edge (0-1)
    y1: float  # Bottom edge (0-1)
    page: int  # Page number (0-indexed)

    @property
    def width(self) -> float:
        """Width of the bounding box."""
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        """Height of the bounding box."""
        return self.y1 - self.y0

    @property
    def center_x(self) -> float:
        """X coordinate of the center."""
        return (self.x0 + self.x1) / 2

    @property
    def center_y(self) -> float:
        """Y coordinate of the center."""
        return (self.y0 + self.y1) / 2

    @property
    def area(self) -> float:
        """Area of the bounding box."""
        return self.width * self.height

    def overlaps(self, other: BoundingBox) -> bool:
        """Check if this box overlaps with another box."""
        if self.page != other.page:
            return False
        return not (self.x1 < other.x0 or self.x0 > other.x1 or
                   self.y1 < other.y0 or self.y0 > other.y1)

    def contains_point(self, x: float, y: float) -> bool:
        """Check if a point is inside this bounding box."""
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1


@dataclass
class TextBlock:
    """
    A block of text with layout information.

    Represents a single text element extracted from a document, including
    its content, position, confidence score, and inferred properties.
    """
    id: str  # Unique ID like "page0_block5"
    text: str
    bbox: BoundingBox
    confidence: float  # OCR confidence 0-100
    font_size: Optional[float] = None  # Estimated from bbox height in points
    is_bold: bool = False  # Inferred from tesseract (if available)
    block_type: str = "text"  # "text", "title", "header", "number"

    @property
    def is_likely_header(self) -> bool:
        """Heuristic: large font in top 20% of page."""
        return (self.font_size or 0) > 14 and self.bbox.y0 < 0.2

    @property
    def is_numeric(self) -> bool:
        """Check if text is purely numeric."""
        return self.text.strip().replace('.', '').replace('-', '').isdigit()

    def __repr__(self) -> str:
        return f"TextBlock(id='{self.id}', text='{self.text[:30]}...', bbox=({self.bbox.x0:.2f}, {self.bbox.y0:.2f}))"


@dataclass
class TableCell:
    """A cell in a detected table."""
    row: int
    col: int
    text: str
    bbox: BoundingBox
    is_header: bool = False

    def __repr__(self) -> str:
        return f"TableCell({self.row},{self.col}): '{self.text}'"


@dataclass
class Table:
    """
    A detected table structure.

    Represents a grid-aligned table with cells, rows, and columns.
    """
    id: str
    bbox: BoundingBox
    cells: List[TableCell] = field(default_factory=list)
    rows: int = 0
    cols: int = 0

    def get_cell(self, row: int, col: int) -> Optional[str]:
        """Get text of a specific cell."""
        for cell in self.cells:
            if cell.row == row and cell.col == col:
                return cell.text
        return None

    def get_row(self, row: int) -> List[str]:
        """Get all cells in a row."""
        row_cells = [c for c in self.cells if c.row == row]
        row_cells.sort(key=lambda c: c.col)
        return [c.text for c in row_cells]

    def get_column(self, col: int) -> List[str]:
        """Get all cells in a column."""
        col_cells = [c for c in self.cells if c.col == col]
        col_cells.sort(key=lambda c: c.row)
        return [c.text for c in col_cells]

    def get_headers(self) -> List[str]:
        """Get all header cells (typically first row)."""
        return [c.text for c in self.cells if c.is_header]

    def to_dict(self) -> List[List[str]]:
        """Convert table to 2D list."""
        if not self.cells:
            return []

        # Build 2D array
        result = [['' for _ in range(self.cols)] for _ in range(self.rows)]
        for cell in self.cells:
            if 0 <= cell.row < self.rows and 0 <= cell.col < self.cols:
                result[cell.row][cell.col] = cell.text
        return result

    def __repr__(self) -> str:
        return f"Table(id='{self.id}', rows={self.rows}, cols={self.cols}, cells={len(self.cells)})"


@dataclass
class DocumentIR:
    """
    Intermediate representation of a document with full layout information.

    This is the core data structure that bridges raw OCR output with structured
    extraction. It preserves all layout information while providing query methods
    for finding text blocks, tables, and regions.
    """
    filename: str
    page_count: int
    blocks: List[TextBlock]
    tables: List[Table]
    raw_text: str  # Full OCR text (backward compat)
    layout_hash: str  # Hash of block structure for similarity matching

    # Metadata
    page_dimensions: List[Tuple[float, float]]  # (width, height) per page
    dpi: int = 300
    extraction_method: str = "tesseract"  # or "embedded"

    def get_blocks_in_region(self, bbox: BoundingBox) -> List[TextBlock]:
        """Get all blocks that overlap with a bounding box."""
        return [block for block in self.blocks if block.bbox.overlaps(bbox)]

    def get_blocks_by_page(self, page: int) -> List[TextBlock]:
        """Get all blocks on a specific page."""
        return [block for block in self.blocks if block.bbox.page == page]

    def get_blocks_by_type(self, block_type: str) -> List[TextBlock]:
        """Get all blocks of a specific type."""
        return [b for b in self.blocks if b.block_type == block_type]

    def find_text(self, pattern: str, case_sensitive: bool = False) -> List[TextBlock]:
        """Find blocks containing text pattern."""
        if not case_sensitive:
            pattern = pattern.lower()

        result = []
        for block in self.blocks:
            text = block.text if case_sensitive else block.text.lower()
            if pattern in text:
                result.append(block)
        return result

    def find_text_exact(self, pattern: str, case_sensitive: bool = True) -> List[TextBlock]:
        """Find blocks with exact text match."""
        result = []
        for block in self.blocks:
            text = block.text if case_sensitive else block.text.lower()
            pattern_cmp = pattern if case_sensitive else pattern.lower()
            if text == pattern_cmp:
                result.append(block)
        return result

    def get_blocks_near(self, reference: TextBlock, max_distance: float = 0.1) -> List[TextBlock]:
        """
        Get blocks near a reference block.

        Args:
            reference: Reference block
            max_distance: Maximum distance in normalized coordinates (0-1)
        """
        result = []
        ref_center_x = reference.bbox.center_x
        ref_center_y = reference.bbox.center_y

        for block in self.blocks:
            if block.id == reference.id or block.bbox.page != reference.bbox.page:
                continue

            # Calculate distance
            dx = block.bbox.center_x - ref_center_x
            dy = block.bbox.center_y - ref_center_y
            distance = (dx**2 + dy**2)**0.5

            if distance <= max_distance:
                result.append(block)

        return result

    def get_blocks_in_column(self, reference: TextBlock, tolerance: float = 0.02) -> List[TextBlock]:
        """
        Get blocks aligned in the same column as reference block.

        Args:
            reference: Reference block
            tolerance: Horizontal alignment tolerance (0-1)
        """
        result = []
        ref_x = reference.bbox.center_x

        for block in self.blocks:
            if block.id == reference.id or block.bbox.page != reference.bbox.page:
                continue

            if abs(block.bbox.center_x - ref_x) <= tolerance:
                result.append(block)

        return sorted(result, key=lambda b: b.bbox.y0)

    def get_blocks_in_row(self, reference: TextBlock, tolerance: float = 0.02) -> List[TextBlock]:
        """
        Get blocks aligned in the same row as reference block.

        Args:
            reference: Reference block
            tolerance: Vertical alignment tolerance (0-1)
        """
        result = []
        ref_y = reference.bbox.center_y

        for block in self.blocks:
            if block.id == reference.id or block.bbox.page != reference.bbox.page:
                continue

            if abs(block.bbox.center_y - ref_y) <= tolerance:
                result.append(block)

        return sorted(result, key=lambda b: b.bbox.x0)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        data = asdict(self)
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> DocumentIR:
        """Deserialize from JSON string."""
        data = json.loads(json_str)

        # Convert nested dicts back to dataclasses
        data['blocks'] = [
            TextBlock(
                id=b['id'],
                text=b['text'],
                bbox=BoundingBox(**b['bbox']),
                confidence=b['confidence'],
                font_size=b.get('font_size'),
                is_bold=b.get('is_bold', False),
                block_type=b.get('block_type', 'text')
            )
            for b in data['blocks']
        ]

        data['tables'] = [
            Table(
                id=t['id'],
                bbox=BoundingBox(**t['bbox']),
                cells=[
                    TableCell(
                        row=c['row'],
                        col=c['col'],
                        text=c['text'],
                        bbox=BoundingBox(**c['bbox']),
                        is_header=c.get('is_header', False)
                    )
                    for c in t['cells']
                ],
                rows=t['rows'],
                cols=t['cols']
            )
            for t in data['tables']
        ]

        return cls(**data)

    def __repr__(self) -> str:
        return f"DocumentIR(filename='{self.filename}', pages={self.page_count}, blocks={len(self.blocks)}, tables={len(self.tables)})"
