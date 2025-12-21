"""
DocumentIR Builder - extracts text blocks with bounding boxes from documents.

Uses Tesseract OCR with image_to_data() to get bounding box information for
every text element in the document. Normalizes coordinates and infers layout
properties like headers, tables, and block types.
"""
from __future__ import annotations

import hashlib
import logging
import os
from io import BytesIO
from typing import List, Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image

from src.ir.document_ir import (
    BoundingBox,
    TextBlock,
    TableCell,
    Table,
    DocumentIR,
)

logger = logging.getLogger(__name__)

# Check for Tesseract availability
try:
    import pytesseract
    from pytesseract import Output
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("pytesseract not available - IRBuilder will fail")


class IRBuilder:
    """
    Builds DocumentIR from PDF documents using Tesseract OCR.

    Extracts text blocks with bounding boxes, normalizes coordinates,
    infers block types, and detects tables.
    """

    def __init__(self, dpi: int = 300):
        """
        Initialize IRBuilder.

        Args:
            dpi: Resolution for rendering PDFs (300 recommended for OCR)
        """
        if not TESSERACT_AVAILABLE:
            raise RuntimeError(
                "pytesseract is required for IRBuilder. "
                "Install with: pip install pytesseract"
            )

        self.dpi = dpi

    def build(self, document_bytes: bytes, filename: str) -> DocumentIR:
        """
        Build DocumentIR from a document.

        Args:
            document_bytes: Raw document content
            filename: Document filename (used for format detection)

        Returns:
            DocumentIR with extracted blocks and tables
        """
        if filename.lower().endswith('.pdf'):
            return self._build_from_pdf(document_bytes, filename)
        elif filename.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
            return self._build_from_image(document_bytes, filename)
        else:
            raise ValueError(f"Unsupported file type: {filename}")

    def _build_from_pdf(self, pdf_bytes: bytes, filename: str) -> DocumentIR:
        """Build IR from PDF document."""
        logger.info(f"Building DocumentIR from PDF: {filename}")

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        all_blocks = []
        all_tables = []
        page_dims = []
        raw_text_parts = []

        for page_num, page in enumerate(doc):
            logger.debug(f"Processing page {page_num + 1}/{len(doc)}")

            # Get page dimensions
            page_width = page.rect.width
            page_height = page.rect.height
            page_dims.append((page_width, page_height))

            # Extract blocks using PyMuPDF's native text extraction
            blocks = self._extract_blocks_from_pymupdf(
                page, page_num, (page_width, page_height)
            )

            # ADD: Use OCR for left column to get player names (rendered as images)
            # Only for pages that likely have player tables (page 1+)
            if page_num >= 1:
                ocr_blocks = self._extract_name_column_with_ocr(
                    page, page_num, (page_width, page_height)
                )
                blocks.extend(ocr_blocks)

            all_blocks.extend(blocks)

            # Extract tables (simple heuristic for Phase 1)
            tables = self._detect_tables_simple(blocks, page_num)
            all_tables.extend(tables)

            # Build raw text
            page_text = "\n".join(b.text for b in blocks)
            raw_text_parts.append(f"=== PAGE {page_num + 1} ===\n{page_text}")

        # Save page count before closing
        page_count = len(doc)
        doc.close()

        raw_text = "\n\n".join(raw_text_parts)
        layout_hash = self._compute_layout_hash(all_blocks)

        logger.info(
            f"Extracted {len(all_blocks)} blocks, {len(all_tables)} tables "
            f"from {page_count} pages"
        )

        return DocumentIR(
            filename=os.path.basename(filename),
            page_count=len(page_dims),
            blocks=all_blocks,
            tables=all_tables,
            raw_text=raw_text,
            layout_hash=layout_hash,
            page_dimensions=page_dims,
            dpi=self.dpi,
            extraction_method="pymupdf"
        )

    def _extract_name_column_with_ocr(
        self,
        page: fitz.Page,
        page_num: int,
        page_dims: Tuple[float, float]
    ) -> List[TextBlock]:
        """
        Extract player names from the left column using OCR.

        Player names are rendered as images in the PDF, not as text,
        so PyMuPDF can't extract them. We use Tesseract OCR on the
        name column area specifically.

        Args:
            page: PyMuPDF Page object
            page_num: Page number (0-indexed)
            page_dims: (width, height) of page in points

        Returns:
            List of TextBlock objects containing player names
        """
        from PIL import Image

        page_width, page_height = page_dims

        # Render page to high-res image for OCR
        pix = page.get_pixmap(dpi=self.dpi)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Crop to name column area (left ~15% of page)
        # Name column is roughly x: 0-120 points in a 612pt-wide page
        name_col_width_pct = 0.20  # 20% of page width
        crop_box = (0, 0, int(img.width * name_col_width_pct), img.height)
        name_col_img = img.crop(crop_box)

        # Run Tesseract OCR
        ocr_data = pytesseract.image_to_data(name_col_img, output_type=Output.DICT)

        blocks = []
        block_id = 1000  # Start at high number to avoid conflicts with PyMuPDF blocks

        for i in range(len(ocr_data['text'])):
            text = ocr_data['text'][i].strip()
            if not text:
                continue

            conf = int(ocr_data['conf'][i])
            if conf < 30:  # Skip low-confidence results
                continue

            # Skip header text
            if text in ['Name', 'Boys', 'Varsity', 'Basketball', "Basketball's", 'Stats',
                       'Player', 'High', "High's", 'School', "School's"]:
                continue

            # Get bounding box in pixels
            left = ocr_data['left'][i]
            top = ocr_data['top'][i]
            width = ocr_data['width'][i]
            height = ocr_data['height'][i]

            # Convert to points (scale from cropped image coords to page coords)
            scale_x = page_width * name_col_width_pct / name_col_img.width
            scale_y = page_height / name_col_img.height

            left_pt = left * scale_x
            top_pt = top * scale_y
            width_pt = width * scale_x
            height_pt = height * scale_y

            # Normalize to 0-1 coordinate space
            x0 = left_pt / page_width
            y0 = top_pt / page_height
            x1 = (left_pt + width_pt) / page_width
            y1 = (top_pt + height_pt) / page_height

            bbox = BoundingBox(
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
                page=page_num
            )

            block = TextBlock(
                id=f"page{page_num}_ocr{block_id}",
                text=text,
                bbox=bbox,
                confidence=float(conf),
                font_size=height_pt,
                is_bold=False,
                block_type="text"
            )

            blocks.append(block)
            block_id += 1

        logger.debug(f"OCR extracted {len(blocks)} name blocks from page {page_num}")
        return blocks

    def _extract_blocks_from_pymupdf(
        self,
        page: fitz.Page,
        page_num: int,
        page_dims: Tuple[float, float]
    ) -> List[TextBlock]:
        """
        Extract text blocks with bounding boxes using PyMuPDF.

        Args:
            page: PyMuPDF Page object
            page_num: Page number (0-indexed)
            page_dims: (width, height) of page in points

        Returns:
            List of TextBlock objects
        """
        # Get words with positions
        words = page.get_text("words")

        page_width, page_height = page_dims

        blocks = []
        block_id = 0

        for word in words:
            x0, y0, x1, y1, text, block_no, line_no, word_no = word

            # Skip empty text
            text = text.strip()
            if not text:
                continue

            # Normalize coordinates to 0-1 space
            norm_x0 = x0 / page_width
            norm_y0 = y0 / page_height
            norm_x1 = x1 / page_width
            norm_y1 = y1 / page_height

            # Estimate font size from height
            height_pt = y1 - y0
            font_size = height_pt

            bbox = BoundingBox(
                x0=norm_x0,
                y0=norm_y0,
                x1=norm_x1,
                y1=norm_y1,
                page=page_num
            )

            block_type = self._infer_block_type(text, bbox, font_size)

            block = TextBlock(
                id=f"page{page_num}_block{block_id}",
                text=text,
                bbox=bbox,
                confidence=100.0,  # PyMuPDF extraction is reliable
                font_size=font_size,
                is_bold=False,  # Could be enhanced later
                block_type=block_type
            )

            blocks.append(block)
            block_id += 1

        return blocks

    def _build_from_image(self, image_bytes: bytes, filename: str) -> DocumentIR:
        """Build IR from image file."""
        logger.info(f"Building DocumentIR from image: {filename}")

        img = Image.open(BytesIO(image_bytes))
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # Image dimensions
        page_width, page_height = img.size
        page_dims = [(page_width, page_height)]

        # Extract blocks
        blocks = self._extract_blocks_from_tesseract(img, 0, (page_width, page_height))

        # Extract tables
        tables = self._detect_tables_simple(blocks, 0)

        # Build raw text
        raw_text = "\n".join(b.text for b in blocks)

        layout_hash = self._compute_layout_hash(blocks)

        logger.info(f"Extracted {len(blocks)} blocks, {len(tables)} tables from image")

        return DocumentIR(
            filename=os.path.basename(filename),
            page_count=1,
            blocks=blocks,
            tables=tables,
            raw_text=raw_text,
            layout_hash=layout_hash,
            page_dimensions=page_dims,
            dpi=self.dpi,
            extraction_method="tesseract"
        )

    def _extract_blocks_from_tesseract(
        self,
        image: Image.Image,
        page_num: int,
        page_dims: Tuple[float, float]
    ) -> List[TextBlock]:
        """
        Extract text blocks with bounding boxes using Tesseract.

        Uses pytesseract.image_to_data() to get detailed layout information
        including bounding boxes and confidence scores.

        Args:
            image: PIL Image to extract from
            page_num: Page number (0-indexed)
            page_dims: (width, height) of page in points

        Returns:
            List of TextBlock objects
        """
        # Get detailed data with bounding boxes
        data = pytesseract.image_to_data(image, output_type=Output.DICT)

        page_width, page_height = page_dims

        blocks = []
        block_id = 0

        # Iterate through all detected text elements
        for i in range(len(data['text'])):
            text = data['text'][i].strip()
            if not text:
                continue

            conf = int(data['conf'][i])
            if conf < 0:  # Tesseract uses -1 for no confidence
                continue

            # Get bounding box in pixels
            left = data['left'][i]
            top = data['top'][i]
            width = data['width'][i]
            height = data['height'][i]

            # Convert pixels to points (Tesseract uses image pixels)
            # Image is at self.dpi, page dims are in points (72 DPI)
            scale_x = page_width / image.width
            scale_y = page_height / image.height

            left_pt = left * scale_x
            top_pt = top * scale_y
            width_pt = width * scale_x
            height_pt = height * scale_y

            # Normalize to 0-1 coordinate space
            x0 = left_pt / page_width
            y0 = top_pt / page_height
            x1 = (left_pt + width_pt) / page_width
            y1 = (top_pt + height_pt) / page_height

            # Estimate font size from height (rough approximation)
            font_size = height_pt * 72 / self.dpi

            bbox = BoundingBox(
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
                page=page_num
            )

            block_type = self._infer_block_type(text, bbox, font_size)

            block = TextBlock(
                id=f"page{page_num}_block{block_id}",
                text=text,
                bbox=bbox,
                confidence=float(conf),
                font_size=font_size,
                is_bold=False,  # Tesseract doesn't easily provide font weight
                block_type=block_type
            )

            blocks.append(block)
            block_id += 1

        logger.debug(f"Extracted {len(blocks)} text blocks from page {page_num}")
        return blocks

    def _infer_block_type(self, text: str, bbox: BoundingBox, font_size: float) -> str:
        """
        Infer block type from content and layout.

        Args:
            text: Block text content
            bbox: Block bounding box
            font_size: Estimated font size in points

        Returns:
            Block type: "header", "number", "text"
        """
        # Headers are large and near top
        if font_size > 14 and bbox.y0 < 0.15:
            return "header"

        # Numbers (single digits or stats like "10-15")
        text_clean = text.replace('-', '').replace('/', '').replace('.', '')
        if text_clean.isdigit() or (len(text) <= 5 and any(c.isdigit() for c in text)):
            return "number"

        # Default
        return "text"

    def _detect_tables_simple(self, blocks: List[TextBlock], page_num: int) -> List[Table]:
        """
        Simple table detection via grid alignment.

        Uses a heuristic approach: if multiple rows of blocks align in
        consistent columns, treat it as a table.

        This is Phase 1 implementation - Phase 2 can add ML-based detection.

        Args:
            blocks: Text blocks from the page
            page_num: Page number

        Returns:
            List of detected tables
        """
        # Filter to blocks on this page
        page_blocks = [b for b in blocks if b.bbox.page == page_num]

        if len(page_blocks) < 9:  # Need at least 3x3 grid
            return []

        # Group blocks by approximate row (y-coordinate clustering)
        rows = self._cluster_by_y(page_blocks, tolerance=0.015)

        if len(rows) < 3:  # Need at least 3 rows
            return []

        # For each row, find column alignment
        # If multiple rows have same column structure, it's likely a table
        tables = []

        # Simple heuristic: check if top 3-5 rows have aligned columns
        if len(rows) >= 3:
            top_rows = rows[:min(5, len(rows))]

            # Get x-positions from first row
            first_row_x = sorted([b.bbox.center_x for b in top_rows[0]])

            # Check if other rows align with these columns
            aligned_rows = [top_rows[0]]
            for row in top_rows[1:]:
                row_x = sorted([b.bbox.center_x for b in row])
                if self._columns_align(first_row_x, row_x, tolerance=0.03):
                    aligned_rows.append(row)

            # If we have 3+ aligned rows, call it a table
            if len(aligned_rows) >= 3:
                table = self._build_table_from_rows(aligned_rows, page_num)
                if table:
                    tables.append(table)

        return tables

    def _cluster_by_y(self, blocks: List[TextBlock], tolerance: float = 0.015) -> List[List[TextBlock]]:
        """
        Group blocks into rows by y-coordinate.

        Args:
            blocks: Blocks to cluster
            tolerance: Vertical alignment tolerance

        Returns:
            List of rows (each row is a list of blocks)
        """
        if not blocks:
            return []

        # Sort by y-coordinate
        sorted_blocks = sorted(blocks, key=lambda b: b.bbox.center_y)

        rows = []
        current_row = [sorted_blocks[0]]
        current_y = sorted_blocks[0].bbox.center_y

        for block in sorted_blocks[1:]:
            if abs(block.bbox.center_y - current_y) <= tolerance:
                # Same row
                current_row.append(block)
            else:
                # New row
                rows.append(sorted(current_row, key=lambda b: b.bbox.x0))
                current_row = [block]
                current_y = block.bbox.center_y

        # Add last row
        if current_row:
            rows.append(sorted(current_row, key=lambda b: b.bbox.x0))

        return rows

    def _columns_align(self, cols1: List[float], cols2: List[float], tolerance: float = 0.03) -> bool:
        """Check if two sets of column x-positions align."""
        if len(cols1) != len(cols2):
            return False

        for x1, x2 in zip(cols1, cols2):
            if abs(x1 - x2) > tolerance:
                return False

        return True

    def _build_table_from_rows(self, rows: List[List[TextBlock]], page_num: int) -> Optional[Table]:
        """Build a Table object from aligned rows."""
        if not rows:
            return None

        # Determine column count (max across rows)
        num_cols = max(len(row) for row in rows)
        num_rows = len(rows)

        # Get overall bounding box
        all_blocks = [b for row in rows for b in row]
        min_x = min(b.bbox.x0 for b in all_blocks)
        min_y = min(b.bbox.y0 for b in all_blocks)
        max_x = max(b.bbox.x1 for b in all_blocks)
        max_y = max(b.bbox.y1 for b in all_blocks)

        table_bbox = BoundingBox(x0=min_x, y0=min_y, x1=max_x, y1=max_y, page=page_num)

        # Build cells
        cells = []
        for row_idx, row in enumerate(rows):
            for col_idx, block in enumerate(row):
                cell = TableCell(
                    row=row_idx,
                    col=col_idx,
                    text=block.text,
                    bbox=block.bbox,
                    is_header=(row_idx == 0)  # First row is header
                )
                cells.append(cell)

        table_id = f"page{page_num}_table{len(cells)}"

        return Table(
            id=table_id,
            bbox=table_bbox,
            cells=cells,
            rows=num_rows,
            cols=num_cols
        )

    def _compute_layout_hash(self, blocks: List[TextBlock]) -> str:
        """
        Compute hash of layout structure for similarity matching.

        Uses block positions and sizes (not content) to create a fingerprint
        that can match documents with similar layouts but different content.

        Args:
            blocks: Text blocks from document

        Returns:
            MD5 hash of layout structure
        """
        # Use first 50 blocks to create fingerprint
        structure = []
        for b in blocks[:50]:
            structure.append(
                f"{b.bbox.x0:.2f},{b.bbox.y0:.2f},"
                f"{b.bbox.width:.2f},{b.bbox.height:.2f},"
                f"{b.block_type}"
            )

        structure_str = "|".join(structure)
        return hashlib.md5(structure_str.encode()).hexdigest()
