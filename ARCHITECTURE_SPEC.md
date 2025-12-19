# Quadd Universal Document Transformer - Architecture Specification

## Project Overview

**Goal:** Build a universal document-to-formatted-text transformation system for 100+ newspapers that learns from examples and achieves 95%+ accuracy.

**Current State (v8.4):**
- Hybrid extractor using Tesseract OCR + Claude Vision
- Working: Basketball box scores, Hockey box scores
- Accuracy: ~95% on names, 100% on stats (for known formats)
- Limitation: Hard-coded prompts per document type

**Target State:**
- Universal "learn from example" system
- Newspaper uploads example + desired output → system learns transformation
- Apply learned transformation to new documents of same type
- 95%+ accuracy across all document types

---

## Core Architecture: "Synthesized Rules" Approach

### The Key Insight

> Don't ask the LLM to DO the transformation. Ask it to DESCRIBE the transformation rules. Then apply those rules deterministically.

This separates:
1. **Learning** (LLM generates rules from example)
2. **Execution** (Code applies rules deterministically)
3. **Validation** (Code verifies output)
4. **Rendering** (Template engine formats output)

---

## System Components

### Phase 1: Document Ingestion (IR Builder)

```
PDF Input
    │
    ├──→ [Image Renderer] ──→ Page Images (300 DPI, for Claude Vision)
    │
    ├──→ [Tesseract hOCR] ──→ Text + Bounding Boxes + Font Info
    │
    └──→ [Layout Analyzer] ──→ Blocks, Tables, Headers, Regions

Output: DocumentIR (Intermediate Representation)
```

**DocumentIR Structure:**
```python
@dataclass
class DocumentIR:
    """Intermediate representation of a document with full layout info."""
    filename: str
    page_count: int
    pages: List[PageIR]
    blocks: List[BlockIR]
    tables: List[TableIR]
    layout_signature: str  # Hash for similarity matching
    raw_text: str  # Full OCR text
    
@dataclass
class BlockIR:
    """A text block with position and style info."""
    id: int
    page: int
    text: str
    bbox: Tuple[float, float, float, float]  # x0, y0, x1, y1
    font_size: float
    is_bold: bool
    is_header: bool  # Inferred from size/position
    block_type: str  # "text", "table_cell", "header", etc.

@dataclass
class TableIR:
    """A detected table structure."""
    page: int
    bbox: Tuple[float, float, float, float]
    headers: List[str]
    rows: List[List[str]]
    column_count: int
```

### Phase 2A: Learning (Rule Synthesis)

**Input:**
- DocumentIR of example document
- Page images of example document
- Desired output text (provided by user)

**Process:**

1. **Alignment Step**
   - Map each segment of desired output to source blocks in DocumentIR
   - Identify which blocks/tables contribute to which output sections
   
2. **Rule Synthesis Step**
   - LLM analyzes alignment and generates Processor rules
   - Rules include: anchors, regions, extraction ops, calculations, format template
   
3. **Validation Step**
   - Apply generated rules to example document
   - Compare output to desired output
   - If mismatch > 5%, refine rules

4. **Edge Case Generation**
   - LLM predicts variations (overtime, missing data, extra columns)
   - Updates rules to handle predicted edge cases

**Output:** Processor (stored in database)

### Phase 2B: Processing (Rule Application)

**Input:**
- DocumentIR of new document
- Page images of new document  
- Learned Processor

**Process:**

1. **Apply Rules**
   - Find anchors in document
   - Extract regions based on anchors
   - Run extraction operations
   - Calculate derived fields

2. **Validate**
   - Schema validation (required fields present)
   - Math validation (totals = sum of parts)
   - Completeness check
   - Generate confidence score

3. **Multi-Pass (if confidence < 85%)**
   - Run 2 additional extractions with prompt variations
   - Field-level voting for disputed values
   - Take consensus

4. **Render**
   - Apply Jinja2 template deterministically
   - No LLM creativity in formatting

5. **Verify**
   - Optional second LLM pass to check output against source
   - Flag any discrepancies

**Output:**
- Formatted text
- Confidence score
- Flagged issues (if any)

---

## Processor Data Structure

```python
@dataclass
class Processor:
    """Learned transformation rules for a document type."""
    
    # Identity
    id: str  # UUID
    name: str  # "windom_basketball", "mountain_lake_honor_roll"
    newspaper_id: str  # Which newspaper owns this
    document_type: str  # "basketball", "hockey", "honor_roll", etc.
    created_at: datetime
    updated_at: datetime
    version: int
    
    # Document Fingerprint (for routing)
    layout_signature: str  # Hash of block structure
    text_patterns: List[str]  # Patterns that identify this doc type
    
    # Anchors (landmarks to find in document)
    anchors: List[Anchor]
    
    # Regions (areas between anchors)
    regions: List[Region]
    
    # Extraction Schema
    schema: Dict  # JSON Schema for extracted data
    
    # Extraction Operations
    extraction_ops: List[ExtractionOp]
    
    # Calculations (derived fields)
    calculations: List[Calculation]
    
    # Validation Rules
    validations: List[Validation]
    
    # Format Template (Jinja2)
    format_template: str
    
    # Edge Case Handlers
    edge_cases: List[EdgeCase]
    
    # Examples (for few-shot context)
    examples: List[ProcessorExample]
    
    # Performance Tracking
    success_count: int = 0
    failure_count: int = 0
    last_failure_reason: Optional[str] = None


@dataclass
class Anchor:
    """A landmark pattern to find in documents."""
    name: str  # "period_stats", "player_table_header"
    patterns: List[str]  # ["Q1", "H1", "Period", "1st"]
    backup_patterns: List[str]  # Fallbacks if primary not found
    location_hint: str  # "top_third", "after:game_info", etc.
    required: bool = True


@dataclass
class Region:
    """An area of the document between anchors."""
    name: str  # "away_players", "home_players"
    start_anchor: str  # Reference to Anchor.name
    end_anchor: str  # Reference to Anchor.name
    extraction_type: str  # "table", "key_value", "list"


@dataclass
class ExtractionOp:
    """An operation to extract a field from a region."""
    field: str  # "player.name", "team.score"
    source: str  # "region.away_players.column[0]"
    transform: Optional[str]  # "last_name_only", "to_int", etc.


@dataclass
class Calculation:
    """A derived field calculated from extracted data."""
    field: str  # "team.fg_made"
    formula: str  # "sum(players.fg_made)"


@dataclass
class Validation:
    """A rule to validate extracted data."""
    name: str
    check: str  # Python expression: "team.fg_made == sum(p.fg_made for p in players)"
    message: str  # Error message if check fails
    severity: str  # "error" or "warning"


@dataclass
class EdgeCase:
    """Handler for edge cases not in original example."""
    condition: str  # "len(periods) > 4"  (overtime)
    handler: str  # "append_ot_periods"
    description: str


@dataclass
class ProcessorExample:
    """A stored example for few-shot learning."""
    input_ir_hash: str
    input_text: str  # Truncated for context
    output_text: str
    added_at: datetime
```

---

## Database Schema

```sql
-- Newspapers
CREATE TABLE newspapers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Processors (learned transformations)
CREATE TABLE processors (
    id TEXT PRIMARY KEY,
    newspaper_id TEXT REFERENCES newspapers(id),
    name TEXT NOT NULL,
    document_type TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    processor_json TEXT NOT NULL,  -- Full Processor serialized
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0
);

-- Examples (for learning and few-shot)
CREATE TABLE examples (
    id TEXT PRIMARY KEY,
    processor_id TEXT REFERENCES processors(id),
    input_filename TEXT,
    input_ir_json TEXT,  -- DocumentIR serialized
    output_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Extractions (history of processed documents)
CREATE TABLE extractions (
    id TEXT PRIMARY KEY,
    processor_id TEXT REFERENCES processors(id),
    input_filename TEXT,
    output_text TEXT,
    confidence REAL,
    success BOOLEAN,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Feedback (user corrections)
CREATE TABLE feedback (
    id TEXT PRIMARY KEY,
    extraction_id TEXT REFERENCES extractions(id),
    original_output TEXT,
    corrected_output TEXT,
    feedback_type TEXT,  -- "correction", "approval", "rejection"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## API Endpoints

### Learning API

```
POST /api/processors/learn
{
    "name": "windom_basketball",
    "document_type": "basketball",
    "example_document": <file>,
    "desired_output": "Windom...0 1 1 — 2\nFairmont..."
}

Response:
{
    "processor_id": "abc123",
    "confidence": 0.92,
    "warnings": ["Could not find overtime handler"],
    "test_output": "..."  // Output when applied to example
}
```

### Processing API

```
POST /api/extract
{
    "processor_id": "abc123",  // OR auto-detect
    "document": <file>
}

Response:
{
    "success": true,
    "output": "Windom...formatted text...",
    "confidence": 0.94,
    "warnings": [],
    "needs_review": false
}
```

### Feedback API

```
POST /api/feedback
{
    "extraction_id": "xyz789",
    "feedback_type": "correction",
    "corrected_output": "...fixed text..."
}
```

---

## Implementation Phases

### Phase 1: MVP (Target: 85% accuracy)
- [ ] DocumentIR builder with layout info
- [ ] Basic rule synthesis (anchors, regions, extraction)
- [ ] Simple validation (schema, required fields)
- [ ] Jinja2 rendering
- [ ] SQLite storage for processors
- [ ] Basic web UI

### Phase 2: Hardening (Target: 90% accuracy)
- [ ] Multi-pass extraction with voting
- [ ] Math validation (totals = sums)
- [ ] Edge case generation
- [ ] Confidence scoring
- [ ] "Needs review" flagging

### Phase 3: Production (Target: 95% accuracy)
- [ ] Feedback loop (corrections improve processor)
- [ ] Processor versioning
- [ ] Performance analytics
- [ ] Batch processing
- [ ] Multi-newspaper support

---

## Current Working Code (v8.4)

The existing codebase has:
- `src/extractors/hybrid.py` - Tesseract OCR + Claude Vision extraction
- `src/templates/renderer.py` - Jinja2 template rendering
- `src/api/main.py` - FastAPI endpoints
- `frontend/index.html` - Basic web UI

Key functions to preserve/extend:
- `HybridExtractor._extract_ocr_text()` - Tesseract extraction (works well)
- `HybridExtractor._render_pdf_to_images()` - PDF to images for Claude
- Template rendering logic

---

## Test Documents Available

1. **Basketball** - HUDL box scores (Windom-Worthington.pdf) ✅ Working
2. **Hockey** - HUDL game summaries ✅ Working
3. **Honor Roll** - Various school formats (examples needed)
4. **Legal Notices** - Court records, assumed names (examples needed)

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Name accuracy | 99%+ (Tesseract handles this) |
| Stat accuracy | 100% (validation catches errors) |
| Format accuracy | 98%+ (deterministic templates) |
| Overall accuracy | 95%+ |
| Processing time | < 30 seconds per document |
| Learning time | < 2 minutes per new processor |

---

## Key Insights from Research

1. **Layout information is critical** - Don't throw away bounding boxes
2. **Anchors > Positions** - Find landmarks, not absolute coordinates
3. **Deterministic rendering** - LLM extracts data, template formats it
4. **Validation is non-negotiable** - Math checks catch most errors
5. **Multi-pass voting** - Consensus improves accuracy 5-10%
6. **Feedback loops** - Corrections should improve the system

---

## Contact/Context

This spec was developed through extensive analysis including:
- Current working prototype (v8.4)
- Research on few-shot learning, document understanding
- Consultation with multiple AI systems (Gemini, Grok, ChatGPT, DeepSeek)
- Real-world testing with newspaper documents

The architecture is designed to be:
- **Universal** - Works for any document type
- **Learnable** - Improves from examples
- **Validatable** - Catches its own errors
- **Scalable** - Supports 100+ newspapers
