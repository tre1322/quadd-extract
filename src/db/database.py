"""
Async database layer for processor storage.

Provides CRUD operations for processors, examples, and extractions using
async SQLite with SQLAlchemy.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import uuid

from sqlalchemy import select, text, delete, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.exc import IntegrityError

from src.db.models import Base, ProcessorModel, ExampleModel, ExtractionModel

logger = logging.getLogger(__name__)


class Database:
    """
    Async SQLite database for processors.

    Handles all database operations for storing and retrieving processors,
    examples, and extraction history.
    """

    def __init__(self, db_path: str = "quadd_extract.db"):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.engine = None
        self.session_factory = None
        self._initialized = False

    async def initialize(self):
        """Initialize database and create tables."""
        if self._initialized:
            return

        logger.info(f"Initializing database at {self.db_path}")

        # Create async engine
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{self.db_path}",
            echo=False  # Set to True for SQL logging
        )

        # Create session factory
        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession
        )

        # Create tables using schema.sql
        async with self.engine.begin() as conn:
            # Read schema file
            schema_path = Path(__file__).parent / "schema.sql"
            schema_sql = schema_path.read_text()

            # Execute each statement
            for statement in schema_sql.split(';'):
                statement = statement.strip()
                if statement:
                    await conn.execute(text(statement))

        self._initialized = True
        logger.info("Database initialized successfully")

    async def close(self):
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connections closed")

    # =========================================================================
    # PROCESSOR OPERATIONS
    # =========================================================================

    async def create_processor(
        self,
        processor_id: str,
        name: str,
        document_type: str,
        processor_json: str
    ) -> str:
        """
        Create a new processor.

        Args:
            processor_id: Unique processor ID (UUID)
            name: Human-readable name
            document_type: Document type this processor handles
            processor_json: Full Processor serialized as JSON

        Returns:
            Processor ID

        Raises:
            IntegrityError: If processor with this name already exists
        """
        async with self.session_factory() as session:
            processor = ProcessorModel(
                id=processor_id,
                name=name,
                document_type=document_type,
                processor_json=processor_json,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                version=1,
                success_count=0,
                failure_count=0
            )

            session.add(processor)

            try:
                await session.commit()
                logger.info(f"Created processor: {name} ({processor_id})")
                return processor_id
            except IntegrityError as e:
                await session.rollback()
                logger.error(f"Failed to create processor {name}: {e}")
                raise

    async def get_processor(self, processor_id: str) -> Optional[dict]:
        """
        Get processor by ID.

        Args:
            processor_id: Processor ID

        Returns:
            Dictionary with processor data, or None if not found
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(ProcessorModel).where(ProcessorModel.id == processor_id)
            )
            processor = result.scalar_one_or_none()

            if processor:
                return {
                    'id': processor.id,
                    'name': processor.name,
                    'document_type': processor.document_type,
                    'processor_json': processor.processor_json,
                    'created_at': processor.created_at,
                    'updated_at': processor.updated_at,
                    'version': processor.version,
                    'success_count': processor.success_count,
                    'failure_count': processor.failure_count,
                    'last_used': processor.last_used
                }
            return None

    async def get_processor_by_name(self, name: str) -> Optional[dict]:
        """Get processor by name."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(ProcessorModel).where(ProcessorModel.name == name)
            )
            processor = result.scalar_one_or_none()

            if processor:
                return {
                    'id': processor.id,
                    'name': processor.name,
                    'document_type': processor.document_type,
                    'processor_json': processor.processor_json,
                    'created_at': processor.created_at,
                    'updated_at': processor.updated_at,
                    'version': processor.version,
                    'success_count': processor.success_count,
                    'failure_count': processor.failure_count,
                    'last_used': processor.last_used
                }
            return None

    async def list_processors(self, document_type: Optional[str] = None) -> List[dict]:
        """
        List all processors, optionally filtered by document type.

        Args:
            document_type: Optional filter by document type

        Returns:
            List of processor dictionaries
        """
        async with self.session_factory() as session:
            query = select(ProcessorModel)

            if document_type:
                query = query.where(ProcessorModel.document_type == document_type)

            query = query.order_by(ProcessorModel.updated_at.desc())

            result = await session.execute(query)
            processors = result.scalars().all()

            return [
                {
                    'id': p.id,
                    'name': p.name,
                    'document_type': p.document_type,
                    'processor_json': p.processor_json,
                    'created_at': p.created_at,
                    'updated_at': p.updated_at,
                    'version': p.version,
                    'success_count': p.success_count,
                    'failure_count': p.failure_count,
                    'last_used': p.last_used
                }
                for p in processors
            ]

    async def update_processor(
        self,
        processor_id: str,
        processor_json: str,
        increment_version: bool = True
    ) -> bool:
        """
        Update a processor.

        Args:
            processor_id: Processor ID
            processor_json: Updated processor JSON
            increment_version: Whether to increment version number

        Returns:
            True if updated, False if not found
        """
        async with self.session_factory() as session:
            stmt = (
                update(ProcessorModel)
                .where(ProcessorModel.id == processor_id)
                .values(
                    processor_json=processor_json,
                    updated_at=datetime.utcnow()
                )
            )

            if increment_version:
                stmt = stmt.values(version=ProcessorModel.version + 1)

            result = await session.execute(stmt)
            await session.commit()

            if result.rowcount > 0:
                logger.info(f"Updated processor {processor_id}")
                return True
            return False

    async def delete_processor(self, processor_id: str) -> bool:
        """
        Delete a processor.

        Args:
            processor_id: Processor ID

        Returns:
            True if deleted, False if not found
        """
        async with self.session_factory() as session:
            stmt = delete(ProcessorModel).where(ProcessorModel.id == processor_id)
            result = await session.execute(stmt)
            await session.commit()

            if result.rowcount > 0:
                logger.info(f"Deleted processor {processor_id}")
                return True
            return False

    async def increment_success(self, processor_id: str):
        """Increment success count for a processor."""
        async with self.session_factory() as session:
            stmt = (
                update(ProcessorModel)
                .where(ProcessorModel.id == processor_id)
                .values(
                    success_count=ProcessorModel.success_count + 1,
                    last_used=datetime.utcnow()
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def increment_failure(self, processor_id: str):
        """Increment failure count for a processor."""
        async with self.session_factory() as session:
            stmt = (
                update(ProcessorModel)
                .where(ProcessorModel.id == processor_id)
                .values(
                    failure_count=ProcessorModel.failure_count + 1,
                    last_used=datetime.utcnow()
                )
            )
            await session.execute(stmt)
            await session.commit()

    # =========================================================================
    # EXAMPLE OPERATIONS
    # =========================================================================

    async def save_example(
        self,
        processor_id: Optional[str],
        filename: str,
        document_ir_json: str,
        desired_output: str
    ) -> str:
        """
        Save an example document.

        Args:
            processor_id: Associated processor ID (can be None initially)
            filename: Document filename
            document_ir_json: DocumentIR serialized as JSON
            desired_output: Expected output text

        Returns:
            Example ID
        """
        example_id = str(uuid.uuid4())

        async with self.session_factory() as session:
            example = ExampleModel(
                id=example_id,
                processor_id=processor_id,
                filename=filename,
                document_ir_json=document_ir_json,
                desired_output=desired_output,
                created_at=datetime.utcnow()
            )

            session.add(example)
            await session.commit()

        logger.info(f"Saved example: {filename} ({example_id})")
        return example_id

    async def get_examples_for_processor(self, processor_id: str) -> List[dict]:
        """Get all examples for a processor."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(ExampleModel)
                .where(ExampleModel.processor_id == processor_id)
                .order_by(ExampleModel.created_at.desc())
            )
            examples = result.scalars().all()

            return [
                {
                    'id': e.id,
                    'processor_id': e.processor_id,
                    'filename': e.filename,
                    'document_ir_json': e.document_ir_json,
                    'desired_output': e.desired_output,
                    'created_at': e.created_at
                }
                for e in examples
            ]

    # =========================================================================
    # EXTRACTION OPERATIONS
    # =========================================================================

    async def save_extraction(
        self,
        processor_id: Optional[str],
        filename: str,
        output_text: Optional[str],
        confidence: Optional[float],
        success: bool,
        error_message: Optional[str] = None,
        warnings: Optional[str] = None,
        processing_time_ms: Optional[int] = None
    ) -> str:
        """
        Save an extraction record.

        Args:
            processor_id: Processor used (if any)
            filename: Input filename
            output_text: Extracted output
            confidence: Confidence score
            success: Whether extraction succeeded
            error_message: Error message if failed
            warnings: JSON array of warnings
            processing_time_ms: Processing time in milliseconds

        Returns:
            Extraction ID
        """
        extraction_id = str(uuid.uuid4())

        async with self.session_factory() as session:
            extraction = ExtractionModel(
                id=extraction_id,
                processor_id=processor_id,
                filename=filename,
                output_text=output_text,
                confidence=confidence,
                success=success,
                error_message=error_message,
                warnings=warnings,
                created_at=datetime.utcnow(),
                processing_time_ms=processing_time_ms
            )

            session.add(extraction)
            await session.commit()

        logger.debug(f"Saved extraction record: {extraction_id}")
        return extraction_id

    async def get_recent_extractions(self, limit: int = 100) -> List[dict]:
        """Get recent extraction records."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(ExtractionModel)
                .order_by(ExtractionModel.created_at.desc())
                .limit(limit)
            )
            extractions = result.scalars().all()

            return [
                {
                    'id': e.id,
                    'processor_id': e.processor_id,
                    'filename': e.filename,
                    'output_text': e.output_text,
                    'confidence': e.confidence,
                    'success': e.success,
                    'error_message': e.error_message,
                    'warnings': e.warnings,
                    'created_at': e.created_at,
                    'processing_time_ms': e.processing_time_ms
                }
                for e in extractions
            ]


# Global database instance
_db: Optional[Database] = None


async def get_database(db_path: str = "quadd_extract.db") -> Database:
    """
    Get or create global database instance.

    Args:
        db_path: Path to database file

    Returns:
        Initialized Database instance
    """
    global _db

    if _db is None:
        _db = Database(db_path)
        await _db.initialize()

    return _db
