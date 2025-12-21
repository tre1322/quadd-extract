"""
Quadd Extract API

Main FastAPI application for document extraction and formatting.
"""
from __future__ import annotations

# Load .env file FIRST before anything else
from dotenv import load_dotenv
load_dotenv()

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Optional

import anthropic
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel

from src.extractors.hybrid import HybridExtractor, VisionExtractor
from src.schemas.common import DocumentType, ExtractionResult, RenderResult
from src.templates.renderer import TemplateRenderer
from src.db.database import get_database
from src.learning.service import LearningService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# APPLICATION LIFESPAN
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Quadd Extract API...")
    
    # Initialize extractor
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("=" * 60)
        logger.error("ANTHROPIC_API_KEY not set!")
        logger.error("The API will start but extraction will fail.")
        logger.error("")
        logger.error("To fix, set the environment variable:")
        logger.error("  Windows CMD:  set ANTHROPIC_API_KEY=sk-ant-api03-...")
        logger.error("  PowerShell:   $env:ANTHROPIC_API_KEY='sk-ant-api03-...'")
        logger.error("  Linux/Mac:    export ANTHROPIC_API_KEY=sk-ant-api03-...")
        logger.error("=" * 60)
    else:
        logger.info(f"API key found: {api_key[:15]}...")
    
    try:
        app.state.extractor = HybridExtractor(api_key=api_key)
        app.state.renderer = TemplateRenderer()

        # Initialize database
        app.state.db = await get_database()
        logger.info("Database initialized")

        # Initialize learning service
        app.state.learning_service = LearningService(
            db=app.state.db,
            api_key=api_key
        )
        logger.info("Learning service initialized")

        logger.info("Quadd Extract API started successfully")
    except ValueError as e:
        logger.error(f"Failed to initialize extractor: {e}")
        # Still start the app but extraction won't work
        app.state.extractor = None
        app.state.renderer = TemplateRenderer()
        app.state.db = None
        app.state.learning_service = None

    yield

    # Shutdown
    logger.info("Shutting down Quadd Extract API...")
    if app.state.db:
        await app.state.db.close()


# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="Quadd Extract API",
    description="Universal document-to-newspaper-text extraction system",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware - allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, set specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class ExtractRequest(BaseModel):
    """Request model for extraction endpoint."""
    document_type: Optional[str] = None
    template_id: Optional[str] = None


class ExtractResponse(BaseModel):
    """Response model for extraction endpoint."""
    success: bool
    document_type: str
    confidence: float
    newspaper_text: Optional[str] = None
    template_id: Optional[str] = None
    raw_data: dict[str, Any]
    warnings: list[str]
    errors: list[str]
    tokens_used: Optional[int] = None


class TemplateInfo(BaseModel):
    """Template information."""
    id: str
    name: str
    description: str


class DocumentTypeInfo(BaseModel):
    """Document type information."""
    id: str
    name: str
    category: str


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Quadd Extract API",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/app", response_class=HTMLResponse)
async def serve_app():
    """Serve the frontend application."""
    import os
    
    # Try multiple paths to find the frontend
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "index.html"),
        os.path.join(os.getcwd(), "frontend", "index.html"),
        "frontend/index.html",
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    
    # If no file found, return embedded minimal version
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Sports Stats Formatter</title></head>
    <body style="font-family: sans-serif; padding: 40px; text-align: center;">
        <h1>Sports Stats Formatter</h1>
        <p>Frontend file not found. Please ensure frontend/index.html exists.</p>
        <p>API is running at: <a href="/docs">/docs</a></p>
    </body>
    </html>
    """


@app.post("/extract", response_model=ExtractResponse)
async def extract_document(
    file: UploadFile = File(...),
    document_type: Optional[str] = Form(None),
    template_id: Optional[str] = Form(None),
    render: bool = Form(True),
):
    """
    Extract data from an uploaded document.
    
    - **file**: PDF or image file to process
    - **document_type**: Optional hint for document type (basketball, hockey, etc.)
    - **template_id**: Optional template for rendering
    - **render**: Whether to render output (default: True)
    """
    # Check if extractor is available
    if app.state.extractor is None:
        raise HTTPException(
            status_code=503,
            detail="Extraction service unavailable. ANTHROPIC_API_KEY not configured. Please set the environment variable and restart the server."
        )
    
    try:
        # Read file
        content = await file.read()
        filename = file.filename or "document.pdf"
        
        logger.info(f"Processing document: {filename} ({len(content)} bytes)")
        
        # Parse document type if provided
        doc_type = None
        if document_type:
            try:
                doc_type = DocumentType(document_type.lower())
            except ValueError:
                logger.warning(f"Unknown document type: {document_type}")
        
        # Extract
        extractor: HybridExtractor = app.state.extractor
        extraction = await extractor.extract(content, filename, doc_type)
        
        # Render if requested
        newspaper_text = None
        used_template = None
        
        if render and extraction.success:
            renderer: TemplateRenderer = app.state.renderer
            render_result = renderer.render(extraction, template_id)
            
            if render_result.success:
                newspaper_text = render_result.newspaper_text
                used_template = render_result.template_id
                extraction.warnings.extend(render_result.warnings)
        
        return ExtractResponse(
            success=extraction.success,
            document_type=extraction.document_type.value,
            confidence=extraction.confidence,
            newspaper_text=newspaper_text,
            template_id=used_template,
            raw_data=extraction.data,
            warnings=extraction.warnings,
            errors=extraction.errors,
            tokens_used=extraction.tokens_used,
        )
    
    except anthropic.AuthenticationError as e:
        logger.error(f"API authentication failed: {e}")
        raise HTTPException(
            status_code=401,
            detail="API key is invalid or expired. Please check your ANTHROPIC_API_KEY."
        )
    except anthropic.APIConnectionError as e:
        logger.error(f"API connection failed: {e}")
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to Anthropic API. Check your internet connection and firewall settings."
        )
    except Exception as e:
        logger.exception(f"Extraction error: {e}")
        error_msg = str(e)
        if "Connection error" in error_msg:
            error_msg = "Cannot connect to AI service. Please check your internet connection and API key."
        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/extract/classify")
async def classify_document(file: UploadFile = File(...)):
    """
    Classify a document without full extraction.
    
    Returns the detected document type.
    """
    try:
        content = await file.read()
        filename = file.filename or "document.pdf"
        
        extractor: HybridExtractor = app.state.extractor
        doc_type = await extractor.classify_document(content, filename)
        
        return {
            "document_type": doc_type.value,
            "filename": filename,
        }
        
    except Exception as e:
        logger.exception(f"Classification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/extract/raw")
async def extract_raw(
    file: UploadFile = File(...),
    document_type: Optional[str] = Form(None),
):
    """
    Extract raw data without rendering.
    
    Returns the raw extracted JSON data.
    """
    try:
        content = await file.read()
        filename = file.filename or "document.pdf"
        
        doc_type = None
        if document_type:
            try:
                doc_type = DocumentType(document_type.lower())
            except ValueError:
                pass
        
        extractor: HybridExtractor = app.state.extractor
        extraction = await extractor.extract(content, filename, doc_type)
        
        return {
            "success": extraction.success,
            "document_type": extraction.document_type.value,
            "confidence": extraction.confidence,
            "data": extraction.data,
            "warnings": extraction.warnings,
            "errors": extraction.errors,
            "tokens_used": extraction.tokens_used,
        }
        
    except Exception as e:
        logger.exception(f"Extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/render")
async def render_data(
    data: dict[str, Any],
    document_type: str,
    template_id: Optional[str] = None,
):
    """
    Render pre-extracted data using a template.
    
    Useful for re-rendering with different templates.
    """
    try:
        # Create a mock extraction result
        extraction = ExtractionResult(
            success=True,
            document_type=DocumentType(document_type.lower()),
            confidence=1.0,
            data=data,
        )
        
        renderer: TemplateRenderer = app.state.renderer
        result = renderer.render(extraction, template_id)
        
        return {
            "success": result.success,
            "newspaper_text": result.newspaper_text,
            "template_id": result.template_id,
            "warnings": result.warnings,
        }
        
    except Exception as e:
        logger.exception(f"Render error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/templates", response_model=list[TemplateInfo])
async def list_templates(document_type: Optional[str] = None):
    """
    List available templates.
    
    Optionally filter by document type.
    """
    renderer: TemplateRenderer = app.state.renderer
    
    doc_type = None
    if document_type:
        try:
            doc_type = DocumentType(document_type.lower())
        except ValueError:
            pass
    
    templates = renderer.list_templates(doc_type)
    return [TemplateInfo(**t) for t in templates]


@app.get("/templates/{template_id}")
async def get_template(template_id: str):
    """Get details of a specific template."""
    renderer: TemplateRenderer = app.state.renderer
    template = renderer.get_template(template_id)
    
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")
    
    return {
        "id": template["id"],
        "name": template["name"],
        "description": template.get("description", ""),
        "document_types": [dt.value for dt in template.get("document_types", [])],
        "template": template["template"],
    }


@app.put("/templates/{template_id}")
async def update_template(
    template_id: str,
    name: str,
    template: str,
    document_types: list[str],
    description: str = "",
):
    """
    Create or update a custom template.
    """
    renderer: TemplateRenderer = app.state.renderer
    
    doc_types = []
    for dt in document_types:
        try:
            doc_types.append(DocumentType(dt.lower()))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid document type: {dt}")
    
    renderer.register_template(
        template_id=template_id,
        name=name,
        template=template,
        document_types=doc_types,
        description=description,
    )
    
    return {"status": "ok", "template_id": template_id}


@app.get("/document-types", response_model=list[DocumentTypeInfo])
async def list_document_types():
    """List all supported document types."""
    
    categories = {
        "sports": [
            DocumentType.BASKETBALL,
            DocumentType.HOCKEY,
            DocumentType.WRESTLING,
            DocumentType.GYMNASTICS,
            DocumentType.BASEBALL,
            DocumentType.FOOTBALL,
            DocumentType.VOLLEYBALL,
            DocumentType.SOCCER,
            DocumentType.GOLF,
            DocumentType.TENNIS,
            DocumentType.TRACK,
            DocumentType.CROSS_COUNTRY,
            DocumentType.SWIMMING,
        ],
        "legal": [
            DocumentType.ASSUMED_NAME,
            DocumentType.SUMMONS,
            DocumentType.PUBLIC_NOTICE,
        ],
        "school": [
            DocumentType.HONOR_ROLL,
            DocumentType.GPA_REPORT,
        ],
        "other": [
            DocumentType.TABULAR,
            DocumentType.UNKNOWN,
        ],
    }
    
    result = []
    for category, types in categories.items():
        for doc_type in types:
            result.append(DocumentTypeInfo(
                id=doc_type.value,
                name=doc_type.value.replace("_", " ").title(),
                category=category,
            ))
    
    return result


# =============================================================================
# PHASE 1: LEARNING ENDPOINTS
# =============================================================================

@app.post("/api/processors/learn")
async def learn_processor(
    name: str = Form(...),
    document_type: str = Form(...),
    example_file: UploadFile = File(...),
    desired_output: str = Form(...),
):
    """
    Learn a new processor from an example document.

    This is the core Phase 1 learning endpoint. Upload an example document
    and provide the desired output, and the system will generate extraction
    rules that can be applied to similar documents.
    """
    learning_service: LearningService = app.state.learning_service
    if not learning_service:
        raise HTTPException(status_code=500, detail="Learning service not initialized")

    try:
        # Read file content
        content = await example_file.read()

        # Learn processor
        result = await learning_service.learn_from_example(
            document_bytes=content,
            filename=example_file.filename or "document.pdf",
            desired_output=desired_output,
            document_type=document_type,
            name=name
        )

        return {
            "status": "success",
            "processor_id": result['processor_id'],
            "example_id": result['example_id'],
            "test_success": result['success'],
            "test_output": result['test_output'],
            "stats": {
                "anchors": result['anchors_count'],
                "regions": result['regions_count'],
                "extraction_ops": result['extraction_ops_count'],
                "learning_time_ms": result['learning_time_ms']
            }
        }

    except Exception as e:
        logger.exception(f"Failed to learn processor: {e}")
        raise HTTPException(status_code=500, detail=f"Learning failed: {str(e)}")


@app.post("/api/extract/with-processor")
async def extract_with_processor(
    processor_id: str = Form(...),
    file: UploadFile = File(...),
):
    """
    Extract data from a document using a learned processor.

    Use a previously learned processor to extract structured data from
    a new document of the same type.
    """
    learning_service: LearningService = app.state.learning_service
    if not learning_service:
        raise HTTPException(status_code=500, detail="Learning service not initialized")

    try:
        # Read file content
        content = await file.read()

        # Extract using processor
        result = await learning_service.extract_with_processor(
            document_bytes=content,
            filename=file.filename or "document.pdf",
            processor_id=processor_id
        )

        return {
            "status": "success" if result['success'] else "error",
            "extraction_id": result['extraction_id'],
            "data": result['data'],
            "error_message": result.get('error_message'),
            "processing_time_ms": result['processing_time_ms']
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Extraction failed: {e}")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")


@app.get("/api/processors")
async def list_processors(document_type: Optional[str] = None):
    """
    List all learned processors.

    Optionally filter by document type.
    """
    db = app.state.db
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")

    try:
        processors = await db.list_processors(document_type=document_type)

        return {
            "processors": [
                {
                    "id": p['id'],
                    "name": p['name'],
                    "document_type": p['document_type'],
                    "version": p['version'],
                    "created_at": p['created_at'].isoformat() if p['created_at'] else None,
                    "updated_at": p['updated_at'].isoformat() if p['updated_at'] else None,
                    "success_count": p['success_count'],
                    "failure_count": p['failure_count'],
                    "last_used": p['last_used'].isoformat() if p['last_used'] else None
                }
                for p in processors
            ]
        }

    except Exception as e:
        logger.exception(f"Failed to list processors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/processors/{processor_id}")
async def get_processor_details(processor_id: str):
    """
    Get details of a specific processor.

    Returns the full processor configuration including anchors, regions,
    extraction ops, and validations.
    """
    db = app.state.db
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")

    try:
        processor_data = await db.get_processor(processor_id)

        if not processor_data:
            raise HTTPException(status_code=404, detail=f"Processor not found: {processor_id}")

        # Parse processor JSON to get details
        import json
        processor_json = json.loads(processor_data['processor_json'])

        return {
            "id": processor_data['id'],
            "name": processor_data['name'],
            "document_type": processor_data['document_type'],
            "version": processor_data['version'],
            "created_at": processor_data['created_at'].isoformat() if processor_data['created_at'] else None,
            "updated_at": processor_data['updated_at'].isoformat() if processor_data['updated_at'] else None,
            "success_count": processor_data['success_count'],
            "failure_count": processor_data['failure_count'],
            "last_used": processor_data['last_used'].isoformat() if processor_data['last_used'] else None,
            "anchors": processor_json.get('anchors', []),
            "regions": processor_json.get('regions', []),
            "extraction_ops": processor_json.get('extraction_ops', []),
            "validations": processor_json.get('validations', []),
            "template_id": processor_json.get('template_id', 'generic'),
            "template": processor_json.get('template')
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get processor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/processors/{processor_id}")
async def delete_processor(processor_id: str):
    """
    Delete a processor.

    This will also delete associated examples and extraction history.
    """
    db = app.state.db
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")

    try:
        success = await db.delete_processor(processor_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Processor not found: {processor_id}")

        return {"status": "success", "message": f"Processor {processor_id} deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete processor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# SIMPLE TRANSFORMER ENDPOINTS
# =============================================================================

@app.post("/api/simple/learn")
async def simple_learn(
    name: str = Form(...),
    document_type: str = Form(...),
    example_file: UploadFile = File(...),
    desired_output: str = Form(...),
):
    """
    Learn transformation using Simple Transformer.

    Simple LLM-based approach:
    1. Extract raw text from PDF
    2. Store example input/output pair
    3. Use LLM to transform new documents the same way

    No complex column mapping, anchors, or regions.
    """
    try:
        # Import here to avoid circular dependencies
        from src.simple_transformer import SimpleTransformerDB
        import uuid

        # Generate processor ID
        processor_id = str(uuid.uuid4())

        # Read file
        pdf_bytes = await example_file.read()

        # Create simple transformer
        simple_transformer = SimpleTransformerDB(
            db=app.state.db,
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

        # Learn from example
        result = await simple_transformer.learn_from_example(
            processor_id=processor_id,
            name=name,
            input_pdf_bytes=pdf_bytes,
            desired_output=desired_output
        )

        logger.info(f"Simple transformer learned: {processor_id}")

        return {
            "status": "success",
            "processor_id": processor_id,
            "name": name,
            "document_type": document_type,
            "input_length": result['input_length'],
            "output_length": result['output_length']
        }

    except Exception as e:
        logger.exception(f"Simple learning failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/simple/transform")
async def simple_transform(
    processor_id: str = Form(...),
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
):
    """
    Transform document using Simple Transformer.

    Accepts EITHER:
    - file (PDF upload) - uses OCR + Vision
    - text (pasted text) - uses text directly, no OCR needed

    Uses a previously learned processor to transform a new document.
    """
    try:
        from src.simple_transformer import SimpleTransformerDB

        # Validate input
        if not file and not text:
            raise HTTPException(status_code=400, detail="Please provide either a PDF file or pasted text")
        if file and text:
            raise HTTPException(status_code=400, detail="Please provide either a PDF file OR pasted text, not both")

        # Create simple transformer
        simple_transformer = SimpleTransformerDB(
            db=app.state.db,
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

        # Transform based on input type
        if file:
            # PDF upload - use OCR + Vision
            pdf_bytes = await file.read()
            result = await simple_transformer.transform(
                processor_id=processor_id,
                new_pdf_bytes=pdf_bytes
            )
            logger.info(f"Simple transformation (PDF) complete: {processor_id}")
        else:
            # Text input - use text directly
            result = await simple_transformer.transform_text(
                processor_id=processor_id,
                new_text=text
            )
            logger.info(f"Simple transformation (text) complete: {processor_id}")

        return {
            "status": "success",
            "processor_id": processor_id,
            "output": result['output'],
            "tokens_used": result['tokens_used']
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Simple transformation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/simple/processors")
async def list_simple_processors():
    """
    List ALL processors (including old ones).

    Returns list of all processors with id, name, type, and created date.
    Allows users to manage and delete old processors.
    """
    try:
        # Get all processors from database (no filtering)
        all_processors = await app.state.db.list_processors()

        # Return all processors with their info
        processors_list = []
        for proc in all_processors:
            processors_list.append({
                'id': proc['id'],
                'name': proc['name'],
                'document_type': proc['document_type'],
                'created_at': proc.get('created_at', 'Unknown'),
                'success_count': proc.get('success_count', 0),
                'failure_count': proc.get('failure_count', 0)
            })

        logger.info(f"Listed {len(processors_list)} processors (all types)")

        return {
            "status": "success",
            "processors": processors_list
        }

    except Exception as e:
        logger.exception(f"Failed to list processors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/simple/processors/{processor_id}")
async def update_simple_processor(
    processor_id: str,
    name: Optional[str] = Form(None),
    desired_output: Optional[str] = Form(None)
):
    """
    Update a simple transformer processor's name or example output.

    Can update name, desired_output, or both.
    Does not require re-uploading the PDF.
    """
    try:
        from src.processors.models import Processor
        import json

        # Get existing processor
        processor_data = await app.state.db.get_processor(processor_id)
        if not processor_data:
            raise HTTPException(status_code=404, detail=f"Processor '{processor_id}' not found")

        processor = Processor.from_json(processor_data['processor_json'])

        # Update name if provided
        if name is not None:
            processor.name = name

        # Update desired output if provided
        if desired_output is not None:
            # Parse template to get current data
            template_data = json.loads(processor.template)

            # Update output_text
            template_data['output_text'] = desired_output

            # Save back to template
            processor.template = json.dumps(template_data)

        # Save updated processor
        processor_json = processor.to_json()

        await app.state.db.update_processor(
            processor_id=processor_id,
            name=processor.name if name is not None else processor_data['name'],
            document_type=processor.document_type,
            processor_json=processor_json
        )

        logger.info(f"Updated processor: {processor_id}")

        return {
            "status": "success",
            "processor_id": processor_id,
            "message": "Processor updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update processor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/simple/processors/{processor_id}")
async def delete_simple_processor(processor_id: str):
    """
    Delete a simple transformer processor.

    Permanently removes the processor from the database.
    """
    try:
        # Check if processor exists
        processor_data = await app.state.db.get_processor(processor_id)
        if not processor_data:
            raise HTTPException(status_code=404, detail=f"Processor '{processor_id}' not found")

        # Delete processor
        await app.state.db.delete_processor(processor_id)

        logger.info(f"Deleted processor: {processor_id}")

        return {
            "status": "success",
            "processor_id": processor_id,
            "message": "Processor deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete processor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/simple/processors/bulk-delete")
async def bulk_delete_processors(
    processor_ids: list[str]
):
    """
    Delete multiple processors at once.

    Accepts a list of processor IDs and deletes them all.
    """
    try:
        deleted_count = 0
        failed_ids = []

        for processor_id in processor_ids:
            try:
                # Check if processor exists
                processor_data = await app.state.db.get_processor(processor_id)
                if processor_data:
                    await app.state.db.delete_processor(processor_id)
                    deleted_count += 1
                    logger.info(f"Deleted processor: {processor_id}")
                else:
                    failed_ids.append(processor_id)
            except Exception as e:
                logger.error(f"Failed to delete processor {processor_id}: {e}")
                failed_ids.append(processor_id)

        return {
            "status": "success",
            "deleted_count": deleted_count,
            "failed_count": len(failed_ids),
            "failed_ids": failed_ids,
            "message": f"Deleted {deleted_count} processor(s)"
        }

    except Exception as e:
        logger.exception(f"Bulk delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ERROR HANDLERS
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
