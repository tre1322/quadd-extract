# Quadd Extract

Universal document-to-newspaper-text extraction system. One extraction system for ALL document types.

## Architecture

```
                    ANY Document Input
    (Basketball, Hockey, Honor Roll, Legal Notice, etc.)
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│          UNIVERSAL TEXT EXTRACTION LAYER                │
│                                                         │
│  1. Try embedded text (page.get_text()) - fastest       │
│  2. Fallback to Tesseract OCR (300 DPI) - for scans     │
│                                                         │
│  Output: Raw text string (accurate spelling)            │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│          CLAUDE STRUCTURE ANALYSIS                      │
│                                                         │
│  Input: Image + Extracted Text                          │
│                                                         │
│  Claude's job:                                          │
│  - Classify document type (auto-detect)                 │
│  - Understand layout/structure                          │
│  - Map text to structured JSON                          │
│  - USE extracted text verbatim (no re-reading)          │
│                                                         │
│  Output: Structured JSON                                │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│          TEMPLATE RENDERER                              │
│                                                         │
│  Input: Structured JSON + Template                      │
│  Output: Newspaper-ready text                           │
└─────────────────────────────────────────────────────────┘
```

## Why This Architecture?

**Text Extraction Layer** (Tesseract/embedded text):
- Gets character-perfect accuracy on names and numbers
- No interpretation or "correction" of spelling
- 99% accuracy on player names

**Claude Structure Layer**:
- Understands complex layouts and tables
- Auto-detects document type
- Maps data to correct fields
- Uses pre-extracted text verbatim

## Supported Document Types

### Sports
- [x] Basketball Box Scores
- [x] Hockey Box Scores
- [ ] Wrestling Results
- [ ] Gymnastics Results
- [ ] Football, Baseball, Volleyball, etc.

### Legal/Public Notices
- [ ] Assumed Name Certificates
- [ ] Court Records
- [ ] Summons

### School Reports
- [ ] Honor Rolls
- [ ] GPA Reports

## Quick Start

### 1. Install Tesseract (Recommended for best accuracy)

**Windows:**
Download installer from: https://github.com/UB-Mannheim/tesseract/wiki
Add to PATH after installation.

**macOS:**
```bash
brew install tesseract
```

**Linux:**
```bash
sudo apt-get install tesseract-ocr
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Set API Key

**Windows:**
```cmd
set ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
```

**macOS/Linux:**
```bash
export ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
```

Or create a `.env` file:
```
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
```

### 4. Run

**Windows:**
```cmd
start.bat
```

**macOS/Linux:**
```bash
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Open UI

Navigate to: http://localhost:8000/app

## Project Structure

```
quadd-extract/
├── src/
│   ├── api/              # FastAPI endpoints
│   │   └── main.py       # App entry point
│   ├── extractors/       # Document extraction logic
│   │   ├── hybrid.py     # Universal hybrid extractor (ONE system for all)
│   │   └── base.py       # Base extractor class
│   ├── schemas/          # Pydantic models
│   │   ├── sports.py     # Sports data models
│   │   └── common.py     # Shared models
│   ├── templates/        # Jinja2 templates
│   │   └── renderer.py   # Template rendering engine
│   └── utils/            # Helper functions
├── frontend/             # React UI
│   └── index.html        # Single-page app
├── tests/                # Test suite
├── data/samples/         # Sample documents for testing
├── start.bat             # Windows startup script
├── Dockerfile            # Container deployment
└── requirements.txt
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/app` | GET | Web UI |
| `/extract` | POST | Extract data from uploaded document |
| `/extract/classify` | POST | Classify document type only |
| `/templates` | GET | List available templates |
| `/health` | GET | Health check |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `ANTHROPIC_MODEL` | No | Claude model (default: claude-sonnet-4-20250514) |

## Without Tesseract

The system works without Tesseract installed, but accuracy on names may be lower (~95% vs 99%). Tesseract is strongly recommended for production use.

## License

Proprietary - Quadd.ai
