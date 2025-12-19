"""
Universal Hybrid Document Extractor.

This is the ONE extraction system for ALL document types.
It combines accurate text extraction (embedded text or Tesseract OCR)
with Claude's structural understanding.

Architecture:
1. Text Extraction Layer - Gets accurate text (names, numbers)
   - First tries embedded PDF text (fastest, most accurate)
   - Falls back to Tesseract OCR at 300 DPI
   
2. Structure Analysis Layer - Claude Vision
   - Classifies document type
   - Understands layout and relationships
   - Maps extracted text to structured JSON
   - NEVER re-reads text - uses extracted text verbatim

3. Output - Structured JSON ready for any template
"""
from __future__ import annotations

import base64
import json
import logging
import os
import shutil
from io import BytesIO
from typing import Any, Optional

import anthropic
import fitz  # PyMuPDF
from PIL import Image

from src.schemas.common import DocumentType, ExtractionResult

logger = logging.getLogger(__name__)


# =============================================================================
# CHECK FOR TESSERACT AVAILABILITY
# =============================================================================

def _find_tesseract() -> Optional[str]:
    """
    Find Tesseract executable on the system.
    Returns the path if found, None otherwise.
    """
    import subprocess
    
    # Debug: Log what we're checking
    logger.info("Searching for Tesseract OCR...")
    
    # First try PATH using shutil.which
    tesseract_path = shutil.which("tesseract")
    if tesseract_path:
        logger.info(f"Found tesseract in PATH: {tesseract_path}")
        return tesseract_path
    else:
        logger.info("tesseract not found in PATH via shutil.which")
    
    # Check common Windows installation paths
    windows_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Tesseract-OCR\tesseract.exe",
    ]
    
    for path in windows_paths:
        logger.info(f"Checking path: {path}")
        if os.path.exists(path):
            logger.info(f"Found tesseract at: {path}")
            return path
        else:
            logger.info(f"Not found: {path}")
    
    # Check if TESSERACT_CMD environment variable is set
    env_path = os.environ.get("TESSERACT_CMD")
    if env_path:
        logger.info(f"TESSERACT_CMD env var set to: {env_path}")
        if os.path.exists(env_path):
            return env_path
    else:
        logger.info("TESSERACT_CMD env var not set")
    
    # Last resort: try running tesseract directly
    try:
        result = subprocess.run(
            ["tesseract", "--version"], 
            capture_output=True, 
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            logger.info(f"tesseract works via subprocess: {result.stdout.split()[1] if result.stdout else 'unknown version'}")
            return "tesseract"  # It's in PATH, just shutil.which didn't find it
    except Exception as e:
        logger.info(f"subprocess tesseract check failed: {e}")
    
    return None

# Run detection at module load time
TESSERACT_PATH = _find_tesseract()
TESSERACT_AVAILABLE = TESSERACT_PATH is not None

if TESSERACT_AVAILABLE:
    try:
        import pytesseract
        # Set the tesseract command path explicitly
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
        logger.info(f"Tesseract OCR is available at: {TESSERACT_PATH}")
    except ImportError:
        TESSERACT_AVAILABLE = False
        logger.warning("pytesseract not installed - OCR fallback disabled")
else:
    logger.warning(
        "Tesseract not found. For best accuracy, install from: "
        "https://github.com/UB-Mannheim/tesseract/wiki"
    )


# =============================================================================
# UNIVERSAL EXTRACTION PROMPT
# =============================================================================

UNIVERSAL_EXTRACTION_PROMPT = """You are a document extraction system. Your job is to:

1. CLASSIFY the document type
2. UNDERSTAND the structure and layout
3. MAP the provided extracted text to a structured JSON format

CRITICAL RULES:
- I am providing you with PRE-EXTRACTED TEXT from the document
- USE THIS TEXT VERBATIM for all names, numbers, and values
- DO NOT re-read or re-interpret text from the image
- DO NOT "correct" spelling of names - use exactly what's in the extracted text
- The image is ONLY for understanding structure and layout

DOCUMENT TYPES TO DETECT:
- basketball: Basketball box score or game statistics
- hockey: Hockey box score or game statistics
- wrestling: Wrestling match results
- gymnastics: Gymnastics meet scores
- baseball: Baseball box score
- football: Football box score
- volleyball: Volleyball box score
- soccer: Soccer box score
- golf: Golf scores
- tennis: Tennis match scores
- track: Track & field results
- cross_country: Cross country results
- swimming: Swimming meet results
- honor_roll: School honor roll list
- assumed_name: Certificate of Assumed Name / DBA filing
- summons: Legal summons or court filing
- court_record: Court records, convictions, fines
- public_notice: Generic public notice
- unknown: Cannot determine type

RESPONSE FORMAT:
{
  "document_type": "basketball",
  "confidence": 0.95,
  "data": {
    // Structure depends on document_type
    // See specific structures below
  }
}

=== BASKETBALL STRUCTURE ===
{
  "sport": "basketball",
  "game_date": "YYYY-MM-DD or null",
  "gender": "boys/girls/mens/womens or null",
  "level": "varsity/jv/freshman or null",
  "home_team": {
    "name": "Team Name (from extracted text)",
    "final_score": 104,
    "period_scores": [51, 53],
    "fouls": 23,
    "total_rebounds": 47,
    "turnovers": 12,
    "players": [
      {
        "name": "Player Name (EXACTLY as in extracted text)",
        "jersey_number": "1",
        "points": 18,
        "fg_made": 8,
        "fg_attempted": 18,
        "three_made": 0,
        "three_attempted": 2,
        "ft_made": 2,
        "ft_attempted": 3,
        "offensive_rebounds": 3,
        "defensive_rebounds": 5,
        "total_rebounds": 8,
        "assists": 5,
        "steals": 1,
        "blocks": 0,
        "turnovers": 3,
        "fouls": 2,
        "minutes": 19,
        "plus_minus": 22
      }
    ]
  },
  "away_team": {
    // Same structure as home_team
  }
}

=== HOCKEY STRUCTURE ===
{
  "sport": "hockey",
  "game_date": "YYYY-MM-DD or null",
  "home_team": {
    "name": "Team Name",
    "final_score": 5,
    "period_scores": [2, 1, 2],
    "shots_on_goal": 35,
    "power_play_goals": 2,
    "power_play_opportunities": 5,
    "players": [
      {"name": "Player Name", "goals": 2, "assists": 1, "points": 3, "shots": 5, "pim": 2, "plus_minus": 3}
    ],
    "goalies": [
      {"name": "Goalie Name", "shots_faced": 30, "saves": 27, "save_percentage": 0.900}
    ]
  },
  "away_team": { /* same structure */ },
  "scoring_plays": [
    {"period": "1st", "time": "5:32", "team": "Team", "scorer": "Player", "assists": ["Player1", "Player2"], "type": "even_strength/power_play/shorthanded", "empty_net": false}
  ]
}

=== HONOR ROLL STRUCTURE ===
{
  "document_type": "honor_roll",
  "school_name": "School Name",
  "term": "Quarter 2 / Semester 1 / etc",
  "year": "2024-2025",
  "honor_levels": [
    {
      "level_name": "A Honor Roll",
      "criteria": "3.8+ GPA",
      "students": [
        {"name": "Student Name (EXACTLY as extracted)", "grade": "7th", "gpa": 3.95}
      ]
    },
    {
      "level_name": "B Honor Roll",
      "criteria": "3.0-3.79 GPA",
      "students": [...]
    }
  ]
}

=== LEGAL NOTICE / COURT RECORD STRUCTURE ===
{
  "document_type": "court_record",
  "court_name": "Court Name",
  "date": "YYYY-MM-DD",
  "records": [
    {
      "name": "Person Name (EXACTLY as extracted)",
      "city": "City Name",
      "charge": "Charge description",
      "fine": 150.00,
      "sentence": "Sentence if any"
    }
  ]
}

=== ASSUMED NAME STRUCTURE ===
{
  "document_type": "assumed_name",
  "business_name": "Business Name",
  "owner_name": "Owner Name",
  "address": "Full Address",
  "filing_date": "YYYY-MM-DD",
  "county": "County Name"
}

REMEMBER:
- Use the EXTRACTED TEXT for all names and values
- Use the IMAGE only for understanding structure
- Copy names EXACTLY - do not correct spelling
- If a field is not present, use null
- Return ONLY valid JSON, no markdown
"""


# =============================================================================
# UNIVERSAL HYBRID EXTRACTOR
# =============================================================================

class HybridExtractor:
    """
    Universal document extractor that works for ALL document types.
    
    Combines:
    - Accurate text extraction (embedded PDF text or Tesseract OCR)
    - Claude Vision for structural understanding
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-20250514"):
        """
        Initialize the universal extractor.
        
        Args:
            api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)
            model: Claude model to use for structure analysis
        """
        # Resolve API key
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found!\n"
                "Please set it before running:\n"
                "  Windows CMD: set ANTHROPIC_API_KEY=sk-ant-api03-...\n"
                "  PowerShell:  $env:ANTHROPIC_API_KEY='sk-ant-api03-...'\n"
                "  Linux/Mac:   export ANTHROPIC_API_KEY=sk-ant-api03-..."
            )
        
        self.client = anthropic.Anthropic(api_key=resolved_key)
        self.model = model
        logger.info(f"HybridExtractor initialized with model: {model}")
        logger.info(f"Tesseract OCR available: {TESSERACT_AVAILABLE}")
    
    # =========================================================================
    # TEXT EXTRACTION LAYER
    # =========================================================================
    
    def _extract_embedded_text(self, pdf_bytes: bytes) -> str:
        """
        Extract embedded text directly from PDF.
        This is the most accurate method when PDFs have text layers.
        """
        text_parts = []
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page_num, page in enumerate(doc):
                page_text = page.get_text()
                if page_text.strip():
                    text_parts.append(f"=== PAGE {page_num + 1} ===\n{page_text}")
            doc.close()
        except Exception as e:
            logger.error(f"Error extracting embedded text: {e}")
            return ""
        
        return "\n\n".join(text_parts)
    
    def _extract_ocr_text(self, pdf_bytes: bytes, dpi: int = 300) -> str:
        """
        Extract text using Tesseract OCR.
        Used as fallback when PDFs don't have embedded text.
        
        Args:
            pdf_bytes: PDF file content
            dpi: Resolution for rendering (300 DPI recommended for OCR)
        """
        if not TESSERACT_AVAILABLE:
            logger.warning("Tesseract not available, cannot perform OCR")
            return ""
        
        import pytesseract
        
        text_parts = []
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page_num, page in enumerate(doc):
                # Render at high DPI for accurate OCR
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                
                # Convert to PIL Image
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                # Run Tesseract OCR
                page_text = pytesseract.image_to_string(img)
                if page_text.strip():
                    text_parts.append(f"=== PAGE {page_num + 1} ===\n{page_text}")
            
            doc.close()
        except Exception as e:
            logger.error(f"Error performing OCR: {e}")
            return ""
        
        return "\n\n".join(text_parts)
    
    def _extract_text(self, document_bytes: bytes, filename: str) -> str:
        """
        Universal text extraction - tries best method for the document.
        
        For PDFs: ALWAYS use Tesseract OCR if available, because embedded text
        often lacks actual content (just headers/numbers, no names).
        """
        # Handle text/plain files directly
        if filename.lower().endswith(('.txt', '.csv', '.tsv')):
            try:
                return document_bytes.decode('utf-8')
            except UnicodeDecodeError:
                return document_bytes.decode('latin-1')
        
        # For images, use OCR if available
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            if TESSERACT_AVAILABLE:
                import pytesseract
                try:
                    img = Image.open(BytesIO(document_bytes))
                    return pytesseract.image_to_string(img)
                except Exception as e:
                    logger.error(f"Error performing OCR on image: {e}")
            return ""
        
        # For PDFs: Prefer Tesseract OCR for accuracy (gets actual names)
        if filename.lower().endswith('.pdf'):
            # Try Tesseract OCR first (most accurate for names)
            if TESSERACT_AVAILABLE:
                logger.info("Using Tesseract OCR for PDF extraction")
                ocr_text = self._extract_ocr_text(document_bytes)
                if ocr_text.strip() and len(ocr_text) > 200:
                    logger.info(f"Using Tesseract OCR text ({len(ocr_text)} chars)")
                    return ocr_text
                else:
                    logger.warning(f"Tesseract OCR returned insufficient text ({len(ocr_text)} chars)")
            
            # Fall back to embedded text if OCR fails
            embedded_text = self._extract_embedded_text(document_bytes)
            if embedded_text.strip():
                logger.info(f"Falling back to embedded PDF text ({len(embedded_text)} chars)")
                return embedded_text
        
        return ""
    
    # =========================================================================
    # IMAGE PREPARATION LAYER
    # =========================================================================
    
    def _pdf_to_images(self, pdf_bytes: bytes, dpi: int = 200) -> list[Image.Image]:
        """Convert PDF pages to PIL Images for Claude Vision."""
        images = []
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page in doc:
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                images.append(img)
            doc.close()
        except Exception as e:
            logger.error(f"Error converting PDF to images: {e}")
            raise
        return images
    
    def _image_to_base64(self, image: Image.Image, format: str = "PNG") -> str:
        """Convert PIL Image to base64 string."""
        buffer = BytesIO()
        image.save(buffer, format=format)
        return base64.standard_b64encode(buffer.getvalue()).decode("utf-8")
    
    def _prepare_image_content(self, document_bytes: bytes, filename: str) -> list[dict]:
        """Prepare document images as Claude content blocks."""
        content_blocks = []
        
        if filename.lower().endswith('.pdf'):
            images = self._pdf_to_images(document_bytes)
            for img in images:
                b64 = self._image_to_base64(img)
                content_blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": b64
                    }
                })
        elif filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            img = Image.open(BytesIO(document_bytes))
            if img.mode != 'RGB':
                img = img.convert('RGB')
            b64 = self._image_to_base64(img)
            media_type = "image/png"
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64
                }
            })
        
        return content_blocks
    
    # =========================================================================
    # CLAUDE STRUCTURE ANALYSIS LAYER
    # =========================================================================
    
    def _analyze_structure(
        self,
        document_bytes: bytes,
        filename: str,
        extracted_text: str,
        document_type_hint: Optional[DocumentType] = None
    ) -> dict:
        """
        Use Claude to analyze document structure and map extracted text to JSON.
        
        Args:
            document_bytes: Raw document content
            filename: Document filename
            extracted_text: Pre-extracted text (from embedded or OCR)
            document_type_hint: Optional hint for document type
        """
        # Prepare image content for Claude
        image_content = self._prepare_image_content(document_bytes, filename)
        
        # Build the prompt
        prompt_parts = [UNIVERSAL_EXTRACTION_PROMPT]
        
        if document_type_hint and document_type_hint != DocumentType.UNKNOWN:
            prompt_parts.append(f"\nHINT: This document is likely a {document_type_hint.value} document.")
        
        prompt_parts.append(f"\n\n=== EXTRACTED TEXT (USE THIS FOR ALL NAMES AND VALUES) ===\n{extracted_text}")
        prompt_parts.append("\n\n=== NOW ANALYZE THE STRUCTURE AND RETURN JSON ===")
        prompt_parts.append("\nCRITICAL: Return ONLY the JSON object. No explanations, no markdown, no text before or after. Just the raw JSON starting with { and ending with }")
        
        full_prompt = "\n".join(prompt_parts)
        
        # Build message content
        content = []
        content.extend(image_content)
        content.append({"type": "text", "text": full_prompt})
        
        # Call Claude
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8192,
                messages=[{"role": "user", "content": content}]
            )
            
            response_text = response.content[0].text
            tokens_used = response.usage.input_tokens + response.usage.output_tokens
            
            # Parse JSON from response - handle various formats
            json_text = response_text.strip()
            
            # Remove markdown code blocks if present
            if "```json" in json_text:
                start = json_text.find("```json") + 7
                end = json_text.find("```", start)
                if end > start:
                    json_text = json_text[start:end].strip()
            elif "```" in json_text:
                start = json_text.find("```") + 3
                end = json_text.find("```", start)
                if end > start:
                    json_text = json_text[start:end].strip()
            
            # If still not valid JSON, try to find JSON object in the text
            if not json_text.startswith("{"):
                # Find the first { and last }
                start_idx = json_text.find("{")
                end_idx = json_text.rfind("}")
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_text = json_text[start_idx:end_idx + 1]
                    logger.info("Extracted JSON from mixed response")
            
            result = json.loads(json_text)
            result["_tokens_used"] = tokens_used
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            logger.error(f"Response was: {response_text[:500]}...")
            return {"document_type": "unknown", "confidence": 0, "data": {}, "error": str(e)}
        except Exception as e:
            logger.error(f"Error calling Claude: {e}")
            return {"document_type": "unknown", "confidence": 0, "data": {}, "error": str(e)}
    
    # =========================================================================
    # MAIN EXTRACTION METHOD
    # =========================================================================
    
    async def extract(
        self,
        document_bytes: bytes,
        filename: str,
        document_type: Optional[DocumentType] = None
    ) -> ExtractionResult:
        """
        Extract structured data from any document.
        
        This is the ONE method to call for ALL document types.
        
        Args:
            document_bytes: Raw document content
            filename: Document filename (used for format detection)
            document_type: Optional hint for document type
            
        Returns:
            ExtractionResult with structured data
        """
        logger.info(f"Extracting from: {filename} ({len(document_bytes)} bytes)")
        
        try:
            # Step 1: Extract text (embedded or OCR)
            extracted_text = self._extract_text(document_bytes, filename)
            logger.info(f"Extracted {len(extracted_text)} characters of text")
            
            # Step 2: Analyze structure with Claude
            result = self._analyze_structure(
                document_bytes,
                filename,
                extracted_text,
                document_type
            )
            
            # Step 3: Build ExtractionResult
            doc_type_str = result.get("document_type", "unknown")
            try:
                detected_type = DocumentType(doc_type_str)
            except ValueError:
                detected_type = DocumentType.UNKNOWN
            
            confidence = result.get("confidence", 0.5)
            data = result.get("data", result)  # Some responses put data at root level
            tokens_used = result.get("_tokens_used", 0)
            
            # If data is nested under document_type key, extract it
            if "data" not in result and doc_type_str != "unknown":
                # The whole result IS the data
                data = {k: v for k, v in result.items() if k not in ["document_type", "confidence", "_tokens_used", "error"]}
            
            return ExtractionResult(
                success=True,
                document_type=detected_type,
                confidence=confidence,
                data=data,
                warnings=[],
                errors=[],
                tokens_used=tokens_used
            )
            
        except Exception as e:
            logger.exception(f"Extraction failed: {e}")
            return ExtractionResult(
                success=False,
                document_type=DocumentType.UNKNOWN,
                confidence=0,
                data={},
                warnings=[],
                errors=[str(e)],
                tokens_used=0
            )


# =============================================================================
# BACKWARD COMPATIBILITY - Alias for existing code
# =============================================================================

# The old VisionExtractor name still works
VisionExtractor = HybridExtractor
