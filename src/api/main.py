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
from typing import Any, Optional, List
import json

import anthropic
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from pydantic import BaseModel
import uuid

from src.extractors.hybrid import HybridExtractor, VisionExtractor
from src.schemas.common import DocumentType, ExtractionResult, RenderResult
from src.templates.renderer import TemplateRenderer
from src.db.database import get_database
from src.learning.service import LearningService
from src.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    get_admin_user,
    get_current_user_optional
)
import bcrypt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# AUTHENTICATION INITIALIZATION
# =============================================================================

async def init_default_admin(db):
    """Initialize default admin user if it doesn't exist."""
    from sqlalchemy import select
    from src.db.models import UserModel

    try:
        # Check if admin user exists
        async with db.session_factory() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.email == 'admin@quadd.com')
            )
            existing_admin = result.scalar_one_or_none()

            if existing_admin:
                logger.info("✓ Admin user already exists")
                logger.info(f"  Email: {existing_admin.email}")
                logger.info(f"  Name: {existing_admin.name}")
                logger.info(f"  Role: {existing_admin.role}")
                return

            # Create default admin user
            logger.info("Creating default admin user...")

            admin_id = str(uuid.uuid4())
            password = "changeme123"
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            admin_user = UserModel(
                id=admin_id,
                email='admin@quadd.com',
                password_hash=password_hash,
                name='Admin',
                role='admin'
            )

            session.add(admin_user)
            await session.commit()

            logger.info("✓ Default admin user created successfully!")
            logger.info("=" * 60)
            logger.info("DEFAULT ADMIN CREDENTIALS")
            logger.info("=" * 60)
            logger.info("Email:    admin@quadd.com")
            logger.info("Password: changeme123")
            logger.info("=" * 60)
            logger.info("")
            logger.info("⚠️  SECURITY WARNING:")
            logger.info("Please change this password immediately after first login!")
            logger.info("This is a temporary password for initial setup only.")
            logger.info("=" * 60)

    except Exception as e:
        logger.exception(f"Failed to initialize admin user: {e}")
        raise


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
        db_path = os.getenv('DATABASE_PATH', 'quadd_extract.db')
        logger.info(f"Initializing database at: {db_path}")
        app.state.db = await get_database(db_path)
        logger.info(f"Database initialized successfully at: {db_path}")

        # Initialize authentication system - create default admin user if needed
        logger.info("Initializing authentication system...")
        await init_default_admin(app.state.db)

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
    except Exception as e:
        logger.exception(f"Failed to initialize application: {e}")
        # Set to None to indicate initialization failure
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
# CORS Configuration
# For production, set ALLOWED_ORIGINS environment variable to your Railway domain
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins != ["*"] else ["*"],
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


class LoginRequest(BaseModel):
    """Login request model."""
    email: str
    password: str


class RegisterRequest(BaseModel):
    """User registration request model."""
    email: str
    password: str
    name: str
    role: str = "user"  # 'user' or 'admin'


class UserResponse(BaseModel):
    """User response model (no password)."""
    id: str
    email: str
    name: str
    role: str


class LoginResponse(BaseModel):
    """Login response with token and user info."""
    token: str
    user: UserResponse


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    """Root endpoint - redirect to login page."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/login")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================

@app.post("/api/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Authenticate user and return JWT token.

    Validates email/password and returns a JWT token valid for 24 hours.
    """
    try:
        # Check if database is initialized
        if not app.state.db:
            logger.error("Login attempt but database not initialized!")
            raise HTTPException(
                status_code=503,
                detail="Database not initialized. Please check server logs."
            )

        # Get user by email
        logger.debug(f"Login attempt for email: {request.email}")
        user = await app.state.db.get_user_by_email(request.email)

        if not user:
            logger.warning(f"Login failed: User not found for email: {request.email}")
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password"
            )

        # Verify password
        password_valid = verify_password(request.password, user['password_hash'])
        if not password_valid:
            logger.warning(f"Login failed: Invalid password for email: {request.email}")
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password"
            )

        # Create access token
        token = create_access_token(
            user_id=user['id'],
            email=user['email'],
            role=user['role']
        )

        logger.info(f"User logged in successfully: {user['email']}")

        return LoginResponse(
            token=token,
            user=UserResponse(
                id=user['id'],
                email=user['email'],
                name=user['name'],
                role=user['role']
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Login failed with unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")


@app.post("/api/auth/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """
    Logout endpoint (token invalidation).

    Note: With JWT, actual invalidation requires a token blacklist.
    This endpoint exists for consistency and future enhancements.
    Client should discard the token.
    """
    logger.info(f"User logged out: {current_user['email']}")
    return {"message": "Logged out successfully"}


@app.get("/api/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """
    Get current authenticated user information.

    Requires valid JWT token in Authorization header.
    """
    # Get full user info from database
    user = await app.state.db.get_user(current_user['user_id'])

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        id=user['id'],
        email=user['email'],
        name=user['name'],
        role=user['role']
    )


@app.post("/api/auth/register", response_model=UserResponse)
async def register_user(
    request: RegisterRequest,
    admin_user: dict = Depends(get_admin_user)
):
    """
    Register a new user (admin only).

    Requires admin JWT token. Creates a new user account.
    """
    try:
        # Validate role
        if request.role not in ['user', 'admin']:
            raise HTTPException(
                status_code=400,
                detail="Role must be 'user' or 'admin'"
            )

        # Hash password
        password_hash = hash_password(request.password)

        # Create user
        user_id = str(uuid.uuid4())

        await app.state.db.create_user(
            user_id=user_id,
            email=request.email,
            password_hash=password_hash,
            name=request.name,
            role=request.role
        )

        logger.info(f"New user registered by admin {admin_user['email']}: {request.email}")

        return UserResponse(
            id=user_id,
            email=request.email,
            name=request.name,
            role=request.role
        )

    except Exception as e:
        logger.exception(f"User registration failed: {e}")
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=400, detail="Email already registered")
        raise HTTPException(status_code=500, detail="Registration failed")


@app.get("/api/auth/users")
async def list_users(admin_user: dict = Depends(get_admin_user)):
    """
    List all users with template counts (admin only).

    Requires admin JWT token. Returns all users with their details and number of templates.
    """
    try:
        # Get all users
        users = await app.state.db.list_users()

        # Add template count for each user
        users_with_counts = []
        for user in users:
            template_count = await app.state.db.count_processors_by_user(user['id'])
            users_with_counts.append({
                'id': user['id'],
                'email': user['email'],
                'name': user['name'],
                'role': user['role'],
                'created_at': user['created_at'].isoformat() if user['created_at'] else None,
                'template_count': template_count
            })

        return {
            'status': 'success',
            'users': users_with_counts
        }

    except Exception as e:
        logger.exception(f"Failed to list users: {e}")
        raise HTTPException(status_code=500, detail="Failed to list users")


class UpdateUserRequest(BaseModel):
    """Request model for updating user details."""
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None


@app.put("/api/auth/users/{user_id}")
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    admin_user: dict = Depends(get_admin_user)
):
    """
    Update user details (admin only).

    Requires admin JWT token. Can update name, email, and/or role.
    """
    try:
        # Validate role if provided
        if request.role and request.role not in ['user', 'admin']:
            raise HTTPException(
                status_code=400,
                detail="Role must be 'user' or 'admin'"
            )

        # Check if user exists
        user = await app.state.db.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Update user
        success = await app.state.db.update_user(
            user_id=user_id,
            name=request.name,
            email=request.email,
            role=request.role
        )

        if not success:
            raise HTTPException(status_code=400, detail="No changes made")

        logger.info(f"User {user_id} updated by admin {admin_user['email']}")

        # Return updated user
        updated_user = await app.state.db.get_user(user_id)

        return {
            'status': 'success',
            'user': {
                'id': updated_user['id'],
                'email': updated_user['email'],
                'name': updated_user['name'],
                'role': updated_user['role']
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update user: {e}")
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=400, detail="Email already in use")
        raise HTTPException(status_code=500, detail="Failed to update user")


class ResetPasswordRequest(BaseModel):
    """Request model for resetting password."""
    new_password: str


@app.put("/api/auth/users/{user_id}/password")
async def reset_user_password(
    user_id: str,
    request: ResetPasswordRequest,
    admin_user: dict = Depends(get_admin_user)
):
    """
    Reset user password (admin only).

    Requires admin JWT token. Sets a new password for the specified user.
    """
    try:
        # Check if user exists
        user = await app.state.db.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Hash new password
        new_password_hash = hash_password(request.new_password)

        # Update password
        success = await app.state.db.update_user_password(user_id, new_password_hash)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to update password")

        logger.info(f"Password reset for user {user_id} by admin {admin_user['email']}")

        return {
            'status': 'success',
            'message': 'Password updated successfully'
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to reset password: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset password")


@app.delete("/api/auth/users/{user_id}")
async def delete_user(
    user_id: str,
    admin_user: dict = Depends(get_admin_user)
):
    """
    Delete user (admin only).

    Requires admin JWT token. Admins cannot delete themselves.
    """
    try:
        # Check if trying to delete self
        if user_id == admin_user['user_id']:
            raise HTTPException(
                status_code=400,
                detail="You cannot delete your own account"
            )

        # Check if user exists
        user = await app.state.db.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Delete user
        success = await app.state.db.delete_user(user_id)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete user")

        logger.info(f"User {user_id} ({user['email']}) deleted by admin {admin_user['email']}")

        return {
            'status': 'success',
            'message': f"User {user['email']} deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete user: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete user")


# =============================================================================
# FRONTEND & UTILITY ENDPOINTS
# =============================================================================

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


@app.get("/login", response_class=HTMLResponse)
async def serve_login():
    """Serve the login page."""
    import os

    # Try multiple paths to find the login page
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "login.html"),
        os.path.join(os.getcwd(), "frontend", "login.html"),
        "frontend/login.html",
    ]

    for path in possible_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()

    # If no file found, return error
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Login - Universal Document Learning</title></head>
    <body style="font-family: sans-serif; padding: 40px; text-align: center;">
        <h1>Login Page Not Found</h1>
        <p>Please ensure frontend/login.html exists.</p>
    </body>
    </html>
    """


@app.get("/help", response_class=HTMLResponse)
async def serve_help():
    """Serve the help page."""
    import os

    # Try multiple paths to find the help page
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "help.html"),
        os.path.join(os.getcwd(), "frontend", "help.html"),
        "frontend/help.html",
    ]

    for path in possible_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()

    # If no file found, return error
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Help - Universal Document Learning</title></head>
    <body style="font-family: sans-serif; padding: 40px; text-align: center;">
        <h1>Help Page Not Found</h1>
        <p>Please ensure frontend/help.html exists.</p>
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


@app.post("/api/extract/tournament")
async def extract_tournament(
    processor_id: str = Form(...),
    files: List[UploadFile] = File(...),
    teams: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Generic document extraction with entity filtering.

    Uses the LEARNED template system (not sport-specific code) to transform
    documents, with optional filtering by entity names (teams, schools, etc.).

    This is charter-compliant: The transformation logic comes from user-provided
    examples (learned templates), not hardcoded sport/document knowledge.

    Args:
        processor_id: ID of previously learned template
        files: List of document files (PDFs or images)
        teams: JSON array of entity names to filter for (e.g., team names)
        current_user: Authenticated user

    Returns:
        Transformed output filtered by specified entities

    Example:
        User first creates template via "Learn New" with example output.
        Then uses this endpoint to apply that template with entity filtering.
    """
    try:
        from src.simple_transformer import SimpleTransformerDB

        # Parse entity names (teams, schools, etc.)
        entity_names = json.loads(teams)

        if not entity_names or len(entity_names) == 0:
            raise HTTPException(
                status_code=400,
                detail="At least one entity name (team, school, etc.) is required"
            )

        # Get processor info
        processor_data = await app.state.db.get_processor(processor_id)
        if not processor_data:
            raise HTTPException(status_code=404, detail="Template not found. Please create a template first via 'Learn New' tab.")

        processor_name = processor_data['name']
        document_type = processor_data['document_type']

        logger.info(f"Tournament extraction using template '{processor_name}' for entities: {entity_names}")
        logger.info(f"Processing {len(files)} file(s)")

        # Create simple transformer (uses learned template)
        simple_transformer = SimpleTransformerDB(
            db=app.state.db,
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

        # Process all files and collect results
        all_results = []
        total_input_tokens = 0
        total_output_tokens = 0

        for file in files:
            file_bytes = await file.read()
            filename = file.filename or "document.pdf"

            logger.info(f"Processing {filename}...")

            # Transform using the learned template
            # Note: Entity filtering should be taught during template creation
            # User creates example showing output filtered to specific entities
            # System learns to filter similarly for new entity names
            result = await simple_transformer.transform(
                processor_id=processor_id,
                new_file_bytes=file_bytes,
                filename=filename
            )

            if result and result.get('output'):
                all_results.append(result['output'])
                total_input_tokens += result.get('input_tokens', 0)
                total_output_tokens += result.get('output_tokens', 0)
            else:
                logger.warning(f"No output from {filename}")

        if not all_results:
            raise HTTPException(
                status_code=500,
                detail="Failed to extract data from files. Please check if files are valid and template is appropriate."
            )

        # Combine results
        combined_results = "\n\n".join(all_results)

        # Apply entity filtering and consolidation (generic post-processing)
        entity_list = ", ".join([f"'{e}'" for e in entity_names])

        if len(files) > 1:
            # Multiple files: consolidate and filter
            filter_prompt = f"""Process these results from multiple document pages:

TASKS:
1. Filter: Include ONLY entries related to these entities: {entity_list}
   - Use flexible matching (partial names OK - e.g., "Albert Lea" matches "Albert Lea Area")

2. CRITICAL - Perspective Rule: Output should follow the FILTERED ENTITY'S path/journey/results from THEIR perspective
   - If filtering for entity X, show X's results/journey, REGARDLESS of outcomes (wins, losses, rankings, etc.)
   - Do NOT switch to opponents/competitors/other entities just because they had better outcomes
   - Examples:
     * Tournament: Filter for Team A → Show Team A's matches (even if they lost)
     * Company report: Filter for Sales Dept → Show Sales Dept metrics (even if they underperformed)
     * School rankings: Filter for School A → Show School A's results (even if they ranked low)

3. Consolidate: Remove duplicate entries for the same entity
4. Maintain: Keep the original output format
5. Sort: By entity name

Input results:

{combined_results}

Filtered and consolidated results:"""
        else:
            # Single file: just filter
            filter_prompt = f"""Filter these results to include ONLY entries related to these entities: {entity_list}

CRITICAL - Perspective Rule:
- Output should follow the FILTERED ENTITY'S path/journey/results from THEIR perspective
- Show the entity's results REGARDLESS of outcomes (wins, losses, rankings, performance, etc.)
- Do NOT switch to opponents/competitors/other entities just because they had better outcomes

Examples of correct filtering:
- Tournament: Filter for "Team A" → Show Team A's matches even if they lost
- Company report: Filter for "Sales Dept" → Show Sales Dept even if they underperformed
- Rankings: Filter for "School A" → Show School A even if they ranked low

Use flexible matching - partial names are OK (e.g., "Albert Lea" matches "Albert Lea Area").

Maintain the original output format.

Input results:

{combined_results}

Filtered results:"""

        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        filter_response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": filter_prompt
            }]
        )

        final_results = filter_response.content[0].text
        total_input_tokens += filter_response.usage.input_tokens
        total_output_tokens += filter_response.usage.output_tokens

        total_tokens = total_input_tokens + total_output_tokens
        logger.info(f"Tournament extraction successful. Total tokens used: {total_tokens}")

        # Log usage
        await app.state.db.log_usage(
            user_id=current_user['user_id'],
            processor_id=processor_id,
            processor_name=processor_name,
            document_type=document_type,
            input_type='pdf',
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            success=True,
            error_message=None,
            action_type='transform'
        )

        return {
            "success": True,
            "results": final_results,
            "teams": entity_names,
            "files_processed": len(files),
            "tokens_used": total_tokens
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid entity names JSON format")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Tournament extraction error: {e}")
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
async def list_processors(
    document_type: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    List learned processors for current user.

    Regular users see only their own templates.
    Admin users see all templates.
    Orphaned templates (user_id = NULL) are excluded.

    Optionally filter by document type.
    """
    db = app.state.db
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")

    try:
        all_processors = await db.list_processors(document_type=document_type)

        # Filter processors based on user role
        if current_user['role'] == 'admin':
            # Admins see all templates (but exclude orphaned ones)
            filtered_processors = [
                p for p in all_processors
                if p.get('user_id') is not None  # Exclude orphaned templates
            ]
        else:
            # Regular users see only their own templates
            filtered_processors = [
                p for p in all_processors
                if p.get('user_id') == current_user['user_id']
            ]

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
                for p in filtered_processors
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
    example_file: Optional[UploadFile] = File(None),
    source_text: Optional[str] = Form(None),
    desired_output: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Learn transformation using Simple Transformer.

    Requires authentication. Template will be associated with the current user.

    Accepts EITHER:
    - example_file (PDF, Image, Word, Excel, TXT, CSV) - for document sources
    - source_text (pasted text) - for text sources (hockey stats, etc.)

    Simple LLM-based approach:
    1. Extract raw text/images from document or use pasted text
    2. Store example input/output pair
    3. Use LLM to transform new documents the same way

    No complex column mapping, anchors, or regions.
    """
    try:
        # Validate input
        if not example_file and not source_text:
            raise HTTPException(
                status_code=400,
                detail="Please provide either a file upload (PDF, Word, Excel, TXT, CSV, or Image) or pasted source text"
            )
        if example_file and source_text:
            raise HTTPException(
                status_code=400,
                detail="Please provide either a file upload OR pasted source text, not both"
            )

        # Import here to avoid circular dependencies
        from src.simple_transformer import SimpleTransformerDB

        # Generate processor ID
        processor_id = str(uuid.uuid4())

        # Create simple transformer
        simple_transformer = SimpleTransformerDB(
            db=app.state.db,
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

        # Learn from file or text
        success = True
        error_message = None
        input_type = 'text'

        try:
            if example_file:
                # File upload (PDF, Word, Excel, CSV, TXT, Image, etc.)
                file_bytes = await example_file.read()
                result = await simple_transformer.learn_from_example(
                    processor_id=processor_id,
                    name=name,
                    input_file_bytes=file_bytes,
                    desired_output=desired_output,
                    user_id=current_user['user_id'],
                    filename=example_file.filename
                )
                input_type = result.get('file_type', 'pdf')
                logger.info(f"Simple transformer learned from {input_type} file: {processor_id}")
            else:
                # Text input (pasted)
                result = await simple_transformer.learn_from_text(
                    processor_id=processor_id,
                    name=name,
                    input_text=source_text,
                    desired_output=desired_output,
                    user_id=current_user['user_id']
                )
                input_type = 'text'
                logger.info(f"Simple transformer learned from text: {processor_id}")
        except Exception as e:
            success = False
            error_message = str(e)
            raise

        finally:
            # Log usage for learning (currently no tokens used during learning, only during transform)
            # This tracks template creation activity
            await app.state.db.log_usage(
                user_id=current_user['user_id'],
                processor_id=processor_id,
                processor_name=name,
                document_type=document_type,
                input_type=input_type,
                input_tokens=0,  # Learning doesn't call Claude API yet
                output_tokens=0,  # Only transform does
                success=success,
                error_message=error_message,
                action_type='learn'
            )

        return {
            "status": "success",
            "processor_id": processor_id,
            "name": name,
            "document_type": document_type,
            "input_length": result['input_length'],
            "output_length": result['output_length']
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Simple learning failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/simple/transform")
async def simple_transform(
    processor_id: str = Form(...),
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Transform document using Simple Transformer.

    Requires authentication. Tracks usage for analytics.

    Accepts EITHER:
    - file (PDF upload) - uses OCR + Vision
    - text (pasted text) - uses text directly, no OCR needed

    Uses a previously learned processor to transform a new document.
    """
    try:
        from src.simple_transformer import SimpleTransformerDB

        # Validate input
        if not file and not text:
            raise HTTPException(status_code=400, detail="Please provide either a file upload (PDF, Word, Excel, TXT, CSV, or Image) or pasted text")
        if file and text:
            raise HTTPException(status_code=400, detail="Please provide either a file upload OR pasted text, not both")

        # Get processor info for logging
        processor_data = await app.state.db.get_processor(processor_id)
        if not processor_data:
            raise HTTPException(status_code=404, detail="Processor not found")

        processor_name = processor_data['name']
        document_type = processor_data['document_type']
        input_type = 'text'

        # Create simple transformer
        simple_transformer = SimpleTransformerDB(
            db=app.state.db,
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

        # Transform based on input type
        success = False
        error_message = None
        result = None

        try:
            if file:
                # File upload (PDF, Word, Excel, CSV, TXT, Image, etc.)
                file_bytes = await file.read()
                result = await simple_transformer.transform(
                    processor_id=processor_id,
                    new_file_bytes=file_bytes,
                    filename=file.filename
                )
                # Detect input type from filename
                from src.simple_transformer import SimpleTransformer
                temp_transformer = SimpleTransformer(api_key=os.getenv("ANTHROPIC_API_KEY"))
                input_type = temp_transformer.detect_file_type(file_bytes, file.filename)
                logger.info(f"Simple transformation ({input_type}) complete: {processor_id}")
            else:
                # Text input - use text directly
                result = await simple_transformer.transform_text(
                    processor_id=processor_id,
                    new_text=text
                )
                logger.info(f"Simple transformation (text) complete: {processor_id}")

            success = True

        except Exception as transform_error:
            success = False
            error_message = str(transform_error)
            raise

        finally:
            # Log usage (even if transformation failed)
            if result:
                # Extract token usage from Claude API response
                input_tokens = result.get('input_tokens', 0)
                output_tokens = result.get('output_tokens', 0)

                await app.state.db.log_usage(
                    user_id=current_user['user_id'],
                    processor_id=processor_id,
                    processor_name=processor_name,
                    document_type=document_type,
                    input_type=input_type,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    success=success,
                    error_message=error_message,
                    action_type='transform'
                )

        # Return output to user (NO token/cost info for regular users)
        return {
            "status": "success",
            "processor_id": processor_id,
            "output": result['output']
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Simple transformation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/simple/processors")
async def list_simple_processors(current_user: dict = Depends(get_current_user)):
    """
    List processors for current user.

    Regular users see only their own templates.
    Admin users see all templates (excluding orphaned ones).
    Orphaned templates (user_id = NULL) are excluded for all users.
    """
    try:
        # Get all processors from database
        all_processors = await app.state.db.list_processors()

        # Filter by user (admin sees all, regular users see only their own)
        if current_user['role'] == 'admin':
            # Admins see all templates (but exclude orphaned ones)
            filtered_processors = [
                proc for proc in all_processors
                if proc.get('user_id') is not None  # Exclude orphaned templates
            ]
        else:
            # Regular users see only their own processors
            filtered_processors = [
                proc for proc in all_processors
                if proc.get('user_id') == current_user['user_id']
            ]

        # Return processors with their info
        processors_list = []
        for proc in filtered_processors:
            processors_list.append({
                'id': proc['id'],
                'name': proc['name'],
                'document_type': proc['document_type'],
                'created_at': proc.get('created_at', 'Unknown'),
                'success_count': proc.get('success_count', 0),
                'failure_count': proc.get('failure_count', 0)
            })

        logger.info(f"Listed {len(processors_list)} processors for user {current_user['email']}")

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
    desired_output: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Update a simple transformer processor's name or example output.

    Requires authentication and ownership verification.
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

        # Verify ownership (admin can update any, regular user only their own)
        if current_user['role'] != 'admin' and processor_data.get('user_id') != current_user['user_id']:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to update this template"
            )

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
            name=processor.name if name is not None else None,
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
async def delete_simple_processor(
    processor_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a simple transformer processor.

    Requires authentication and ownership verification.
    Permanently removes the processor from the database.
    """
    try:
        # Check if processor exists
        processor_data = await app.state.db.get_processor(processor_id)
        if not processor_data:
            raise HTTPException(status_code=404, detail=f"Processor '{processor_id}' not found")

        # Verify ownership (admin can delete any, regular user only their own)
        if current_user['role'] != 'admin' and processor_data.get('user_id') != current_user['user_id']:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to delete this template"
            )

        # Delete processor
        await app.state.db.delete_processor(processor_id)

        logger.info(f"Deleted processor: {processor_id} by user {current_user['email']}")

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
    processor_ids: list[str],
    current_user: dict = Depends(get_current_user)
):
    """
    Delete multiple processors at once.

    Requires authentication. Users can only delete their own templates.
    Admins can delete any templates.
    """
    try:
        deleted_count = 0
        failed_ids = []
        permission_denied = []

        for processor_id in processor_ids:
            try:
                # Check if processor exists and verify ownership
                processor_data = await app.state.db.get_processor(processor_id)

                if not processor_data:
                    failed_ids.append(processor_id)
                    continue

                # Verify ownership (admin can delete any, regular user only their own)
                if current_user['role'] != 'admin' and processor_data.get('user_id') != current_user['user_id']:
                    permission_denied.append(processor_id)
                    continue

                # Delete processor
                await app.state.db.delete_processor(processor_id)
                deleted_count += 1
                logger.info(f"Deleted processor: {processor_id} by user {current_user['email']}")
            except Exception as e:
                logger.error(f"Failed to delete processor {processor_id}: {e}")
                failed_ids.append(processor_id)

        return {
            "status": "success",
            "deleted_count": deleted_count,
            "failed_count": len(failed_ids),
            "permission_denied_count": len(permission_denied),
            "failed_ids": failed_ids,
            "permission_denied_ids": permission_denied,
            "message": f"Deleted {deleted_count} processor(s)"
        }

    except Exception as e:
        logger.exception(f"Bulk delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ADMIN ENDPOINTS - USAGE ANALYTICS
# =============================================================================

@app.get("/api/admin/usage/summary")
async def get_usage_summary(
    days: Optional[int] = None,
    admin_user: dict = Depends(get_admin_user)
):
    """
    Get aggregate usage statistics (admin only).

    Optional query parameter:
    - days: Filter to last N days (e.g., 1, 7, 30)
    """
    try:
        from datetime import datetime, timedelta

        # Calculate date range
        start_date = None
        end_date = None

        if days:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

        # Get summary
        summary = await app.state.db.get_usage_summary(
            start_date=start_date,
            end_date=end_date
        )

        return {
            "status": "success",
            "summary": summary,
            "date_range": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None,
                "days": days
            }
        }

    except Exception as e:
        logger.exception(f"Failed to get usage summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/usage/by-user")
async def get_usage_by_user(
    days: Optional[int] = None,
    admin_user: dict = Depends(get_admin_user)
):
    """
    Get per-user usage breakdown (admin only).

    Optional query parameter:
    - days: Filter to last N days (e.g., 1, 7, 30)
    """
    try:
        from datetime import datetime, timedelta

        # Calculate date range
        start_date = None
        end_date = None

        if days:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

        # Get per-user summary
        user_summaries = await app.state.db.get_usage_by_user_summary(
            start_date=start_date,
            end_date=end_date
        )

        return {
            "status": "success",
            "users": user_summaries,
            "date_range": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None,
                "days": days
            }
        }

    except Exception as e:
        logger.exception(f"Failed to get usage by user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/usage/recent")
async def get_recent_usage(
    limit: int = 100,
    offset: int = 0,
    days: Optional[int] = None,
    admin_user: dict = Depends(get_admin_user)
):
    """
    Get recent usage activity log with pagination (admin only).

    Query parameters:
    - limit: Max records to return (default 100)
    - offset: Number of records to skip (default 0)
    - days: Filter to last N days (optional)
    """
    try:
        from datetime import datetime, timedelta

        # Calculate date range
        start_date = None
        end_date = None

        if days:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

        # Get recent logs
        logs = await app.state.db.get_recent_usage(
            limit=limit,
            offset=offset,
            start_date=start_date,
            end_date=end_date
        )

        # Add user names
        logs_with_users = []
        for log in logs:
            user = await app.state.db.get_user(log['user_id'])
            logs_with_users.append({
                **log,
                'user_name': user['name'] if user else 'Unknown',
                'user_email': user['email'] if user else 'unknown@example.com',
                'created_at': log['created_at'].isoformat() if log['created_at'] else None
            })

        return {
            "status": "success",
            "logs": logs_with_users,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "count": len(logs_with_users)
            },
            "date_range": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None,
                "days": days
            }
        }

    except Exception as e:
        logger.exception(f"Failed to get recent usage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ADMIN ENDPOINTS - ORPHANED TEMPLATE MANAGEMENT
# =============================================================================

@app.get("/api/admin/orphaned-templates")
async def list_orphaned_templates(admin_user: dict = Depends(get_admin_user)):
    """
    List all orphaned templates (user_id = NULL).

    Admin only. These are templates created before the auth system was added.
    """
    try:
        all_processors = await app.state.db.list_processors()

        # Filter for orphaned templates
        orphaned = [
            p for p in all_processors
            if p.get('user_id') is None
        ]

        logger.info(f"Found {len(orphaned)} orphaned templates")

        return {
            "status": "success",
            "count": len(orphaned),
            "templates": [
                {
                    "id": p['id'],
                    "name": p['name'],
                    "document_type": p['document_type'],
                    "created_at": p['created_at'].isoformat() if p['created_at'] else None,
                    "success_count": p.get('success_count', 0),
                    "failure_count": p.get('failure_count', 0)
                }
                for p in orphaned
            ]
        }

    except Exception as e:
        logger.exception(f"Failed to list orphaned templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/orphaned-templates")
async def delete_orphaned_templates(admin_user: dict = Depends(get_admin_user)):
    """
    Delete all orphaned templates (user_id = NULL).

    Admin only. Permanently removes templates created before auth system.
    """
    try:
        all_processors = await app.state.db.list_processors()

        # Filter for orphaned templates
        orphaned = [
            p for p in all_processors
            if p.get('user_id') is None
        ]

        deleted_count = 0
        failed_ids = []

        for proc in orphaned:
            try:
                await app.state.db.delete_processor(proc['id'])
                deleted_count += 1
                logger.info(f"Deleted orphaned template: {proc['id']} ({proc['name']})")
            except Exception as e:
                logger.error(f"Failed to delete orphaned template {proc['id']}: {e}")
                failed_ids.append(proc['id'])

        return {
            "status": "success",
            "deleted_count": deleted_count,
            "failed_count": len(failed_ids),
            "failed_ids": failed_ids,
            "message": f"Deleted {deleted_count} orphaned template(s)"
        }

    except Exception as e:
        logger.exception(f"Failed to delete orphaned templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class AssignTemplatesRequest(BaseModel):
    """Request model for assigning orphaned templates."""
    user_id: str


@app.post("/api/admin/orphaned-templates/assign")
async def assign_orphaned_templates(
    request: AssignTemplatesRequest,
    admin_user: dict = Depends(get_admin_user)
):
    """
    Assign all orphaned templates to a specific user.

    Admin only. Useful for assigning old templates to admin account.
    """
    try:
        # Verify target user exists
        target_user = await app.state.db.get_user(request.user_id)
        if not target_user:
            raise HTTPException(status_code=404, detail="Target user not found")

        all_processors = await app.state.db.list_processors()

        # Filter for orphaned templates
        orphaned = [
            p for p in all_processors
            if p.get('user_id') is None
        ]

        assigned_count = 0
        failed_ids = []

        for proc in orphaned:
            try:
                # Update user_id in database
                await app.state.db.update_processor(
                    processor_id=proc['id'],
                    user_id=request.user_id,
                    increment_version=False  # Don't increment version for ownership change
                )
                assigned_count += 1
                logger.info(f"Assigned orphaned template {proc['id']} ({proc['name']}) to user {request.user_id}")
            except Exception as e:
                logger.error(f"Failed to assign template {proc['id']}: {e}")
                failed_ids.append(proc['id'])

        return {
            "status": "success",
            "assigned_count": assigned_count,
            "failed_count": len(failed_ids),
            "failed_ids": failed_ids,
            "target_user": target_user['email'],
            "message": f"Assigned {assigned_count} template(s) to {target_user['email']}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to assign orphaned templates: {e}")
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
