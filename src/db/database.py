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

from src.db.models import Base, ProcessorModel, ExampleModel, ExtractionModel, UserModel, UsageLogModel

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
        processor_json: str,
        user_id: Optional[str] = None
    ) -> str:
        """
        Create a new processor.

        Args:
            processor_id: Unique processor ID (UUID)
            name: Human-readable name
            document_type: Document type this processor handles
            processor_json: Full Processor serialized as JSON
            user_id: User ID who owns this processor (optional)

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
                user_id=user_id,
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
                    'user_id': processor.user_id,  # Include user_id for ownership checks
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
                    'user_id': processor.user_id,  # Include user_id for ownership checks
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
                    'user_id': p.user_id,  # Include user_id for filtering
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
        name: Optional[str] = None,
        document_type: Optional[str] = None,
        processor_json: Optional[str] = None,
        user_id: Optional[str] = None,
        increment_version: bool = True
    ) -> bool:
        """
        Update a processor.

        Args:
            processor_id: Processor ID
            name: Updated name (optional)
            document_type: Updated document type (optional)
            processor_json: Updated processor JSON (optional)
            user_id: Updated user_id (optional, for assigning orphaned templates)
            increment_version: Whether to increment version number

        Returns:
            True if updated, False if not found
        """
        async with self.session_factory() as session:
            # Build update values
            values = {'updated_at': datetime.utcnow()}

            if name is not None:
                values['name'] = name
            if document_type is not None:
                values['document_type'] = document_type
            if processor_json is not None:
                values['processor_json'] = processor_json
            if user_id is not None:
                values['user_id'] = user_id

            stmt = (
                update(ProcessorModel)
                .where(ProcessorModel.id == processor_id)
                .values(**values)
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
    # USER OPERATIONS
    # =========================================================================

    async def create_user(
        self,
        user_id: str,
        email: str,
        password_hash: str,
        name: str,
        role: str = 'user'
    ) -> str:
        """
        Create a new user.

        Args:
            user_id: Unique user ID (UUID)
            email: User email (unique)
            password_hash: Hashed password
            name: User's full name
            role: User role ('user' or 'admin')

        Returns:
            User ID

        Raises:
            IntegrityError: If user with this email already exists
        """
        async with self.session_factory() as session:
            user = UserModel(
                id=user_id,
                email=email,
                password_hash=password_hash,
                name=name,
                role=role,
                created_at=datetime.utcnow()
            )

            session.add(user)

            try:
                await session.commit()
                logger.info(f"Created user: {email} ({user_id})")
                return user_id
            except IntegrityError as e:
                await session.rollback()
                logger.error(f"Failed to create user {email}: {e}")
                raise

    async def get_user(self, user_id: str) -> Optional[dict]:
        """
        Get user by ID.

        Args:
            user_id: User ID

        Returns:
            Dictionary with user data, or None if not found
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            user = result.scalar_one_or_none()

            if user:
                return {
                    'id': user.id,
                    'email': user.email,
                    'password_hash': user.password_hash,
                    'name': user.name,
                    'role': user.role,
                    'created_at': user.created_at
                }
            return None

    async def get_user_by_email(self, email: str) -> Optional[dict]:
        """
        Get user by email.

        Args:
            email: User email

        Returns:
            Dictionary with user data, or None if not found
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.email == email)
            )
            user = result.scalar_one_or_none()

            if user:
                return {
                    'id': user.id,
                    'email': user.email,
                    'password_hash': user.password_hash,
                    'name': user.name,
                    'role': user.role,
                    'created_at': user.created_at
                }
            return None

    async def list_users(self) -> List[dict]:
        """
        List all users.

        Returns:
            List of user dictionaries (without password hashes)
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(UserModel).order_by(UserModel.created_at.desc())
            )
            users = result.scalars().all()

            return [
                {
                    'id': u.id,
                    'email': u.email,
                    'name': u.name,
                    'role': u.role,
                    'created_at': u.created_at
                }
                for u in users
            ]

    async def count_processors_by_user(self, user_id: str) -> int:
        """
        Count number of processors owned by a user.

        Args:
            user_id: User ID

        Returns:
            Number of processors owned by user
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(ProcessorModel).where(ProcessorModel.user_id == user_id)
            )
            processors = result.scalars().all()
            return len(processors)

    async def update_user(
        self,
        user_id: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        role: Optional[str] = None
    ) -> bool:
        """
        Update user details.

        Args:
            user_id: User ID
            name: New name (optional)
            email: New email (optional)
            role: New role (optional)

        Returns:
            True if updated, False if not found

        Raises:
            IntegrityError: If email already exists
        """
        async with self.session_factory() as session:
            updates = {}
            if name is not None:
                updates['name'] = name
            if email is not None:
                updates['email'] = email
            if role is not None:
                updates['role'] = role

            if not updates:
                return False

            stmt = (
                update(UserModel)
                .where(UserModel.id == user_id)
                .values(**updates)
            )

            try:
                result = await session.execute(stmt)
                await session.commit()

                if result.rowcount > 0:
                    logger.info(f"Updated user {user_id}: {updates}")
                    return True
                return False
            except IntegrityError as e:
                await session.rollback()
                logger.error(f"Failed to update user {user_id}: {e}")
                raise

    async def update_user_password(self, user_id: str, new_password_hash: str) -> bool:
        """
        Update user password.

        Args:
            user_id: User ID
            new_password_hash: New hashed password

        Returns:
            True if updated, False if not found
        """
        async with self.session_factory() as session:
            stmt = (
                update(UserModel)
                .where(UserModel.id == user_id)
                .values(password_hash=new_password_hash)
            )

            result = await session.execute(stmt)
            await session.commit()

            if result.rowcount > 0:
                logger.info(f"Updated password for user {user_id}")
                return True
            return False

    async def delete_user(self, user_id: str) -> bool:
        """
        Delete a user.

        Args:
            user_id: User ID

        Returns:
            True if deleted, False if not found
        """
        async with self.session_factory() as session:
            stmt = delete(UserModel).where(UserModel.id == user_id)
            result = await session.execute(stmt)
            await session.commit()

            if result.rowcount > 0:
                logger.info(f"Deleted user {user_id}")
                return True
            return False

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

    # =========================================================================
    # USAGE LOG OPERATIONS
    # =========================================================================

    async def log_usage(
        self,
        user_id: str,
        processor_id: Optional[str],
        processor_name: str,
        document_type: str,
        input_type: str,
        input_tokens: int,
        output_tokens: int,
        success: bool,
        error_message: Optional[str] = None,
        action_type: str = 'transform'
    ) -> str:
        """
        Log API usage for analytics.

        Args:
            user_id: User who made the request
            processor_id: Processor used (nullable if deleted)
            processor_name: Processor name for reference
            document_type: Type of document processed
            input_type: 'pdf' or 'text'
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            success: Whether transformation succeeded
            error_message: Error message if failed
            action_type: 'learn' or 'transform' (default: 'transform')

        Returns:
            Usage log ID
        """
        # Calculate cost (Claude Sonnet 4 pricing)
        # Input: $3 per 1M tokens
        # Output: $15 per 1M tokens
        input_cost = (input_tokens / 1_000_000) * 3.0
        output_cost = (output_tokens / 1_000_000) * 15.0
        total_cost = input_cost + output_cost
        total_tokens = input_tokens + output_tokens

        log_id = str(uuid.uuid4())

        async with self.session_factory() as session:
            usage_log = UsageLogModel(
                id=log_id,
                user_id=user_id,
                processor_id=processor_id,
                processor_name=processor_name,
                document_type=document_type,
                action_type=action_type,
                input_type=input_type,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost=total_cost,
                success=success,
                error_message=error_message,
                created_at=datetime.utcnow()
            )

            session.add(usage_log)
            await session.commit()

        logger.debug(f"Logged usage: {log_id} (user: {user_id}, action: {action_type}, tokens: {total_tokens}, cost: ${total_cost:.4f})")
        return log_id

    async def get_usage_by_user(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[dict]:
        """
        Get all usage logs for a specific user.

        Args:
            user_id: User ID
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of usage log dictionaries
        """
        async with self.session_factory() as session:
            query = select(UsageLogModel).where(UsageLogModel.user_id == user_id)

            if start_date:
                query = query.where(UsageLogModel.created_at >= start_date)
            if end_date:
                query = query.where(UsageLogModel.created_at <= end_date)

            query = query.order_by(UsageLogModel.created_at.desc())

            result = await session.execute(query)
            logs = result.scalars().all()

            return [
                {
                    'id': log.id,
                    'user_id': log.user_id,
                    'processor_id': log.processor_id,
                    'processor_name': log.processor_name,
                    'document_type': log.document_type,
                    'action_type': log.action_type,
                    'input_type': log.input_type,
                    'input_tokens': log.input_tokens,
                    'output_tokens': log.output_tokens,
                    'total_tokens': log.total_tokens,
                    'cost': log.cost,
                    'success': log.success,
                    'error_message': log.error_message,
                    'created_at': log.created_at
                }
                for log in logs
            ]

    async def get_usage_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> dict:
        """
        Get aggregate usage statistics.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with aggregate stats
        """
        async with self.session_factory() as session:
            query = select(UsageLogModel)

            if start_date:
                query = query.where(UsageLogModel.created_at >= start_date)
            if end_date:
                query = query.where(UsageLogModel.created_at <= end_date)

            result = await session.execute(query)
            logs = result.scalars().all()

            total_docs = len(logs)
            successful_docs = sum(1 for log in logs if log.success)
            failed_docs = total_docs - successful_docs
            total_tokens = sum(log.total_tokens for log in logs)
            total_cost = sum(log.cost for log in logs)

            # Count unique users
            unique_users = len(set(log.user_id for log in logs))

            # Count by action type
            learn_count = sum(1 for log in logs if log.action_type == 'learn')
            transform_count = sum(1 for log in logs if log.action_type == 'transform')

            return {
                'total_documents': total_docs,
                'successful_documents': successful_docs,
                'failed_documents': failed_docs,
                'total_tokens': total_tokens,
                'total_cost': total_cost,
                'unique_users': unique_users,
                'learn_count': learn_count,
                'transform_count': transform_count
            }

    async def get_recent_usage(
        self,
        limit: int = 100,
        offset: int = 0,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[dict]:
        """
        Get recent usage logs with pagination.

        Args:
            limit: Maximum number of records to return
            offset: Number of records to skip
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of usage log dictionaries
        """
        async with self.session_factory() as session:
            query = select(UsageLogModel)

            if start_date:
                query = query.where(UsageLogModel.created_at >= start_date)
            if end_date:
                query = query.where(UsageLogModel.created_at <= end_date)

            query = query.order_by(UsageLogModel.created_at.desc())
            query = query.limit(limit).offset(offset)

            result = await session.execute(query)
            logs = result.scalars().all()

            return [
                {
                    'id': log.id,
                    'user_id': log.user_id,
                    'processor_id': log.processor_id,
                    'processor_name': log.processor_name,
                    'document_type': log.document_type,
                    'action_type': log.action_type,
                    'input_type': log.input_type,
                    'input_tokens': log.input_tokens,
                    'output_tokens': log.output_tokens,
                    'total_tokens': log.total_tokens,
                    'cost': log.cost,
                    'success': log.success,
                    'error_message': log.error_message,
                    'created_at': log.created_at
                }
                for log in logs
            ]

    async def get_usage_by_user_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[dict]:
        """
        Get per-user usage summary with aggregates.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of per-user summary dictionaries
        """
        async with self.session_factory() as session:
            # Get all usage logs
            query = select(UsageLogModel)

            if start_date:
                query = query.where(UsageLogModel.created_at >= start_date)
            if end_date:
                query = query.where(UsageLogModel.created_at <= end_date)

            result = await session.execute(query)
            logs = result.scalars().all()

            # Group by user
            user_stats = {}
            for log in logs:
                user_id = log.user_id
                if user_id not in user_stats:
                    user_stats[user_id] = {
                        'user_id': user_id,
                        'document_count': 0,
                        'total_tokens': 0,
                        'total_cost': 0.0,
                        'last_active': log.created_at
                    }

                user_stats[user_id]['document_count'] += 1
                user_stats[user_id]['total_tokens'] += log.total_tokens
                user_stats[user_id]['total_cost'] += log.cost

                # Update last_active if this is more recent
                if log.created_at > user_stats[user_id]['last_active']:
                    user_stats[user_id]['last_active'] = log.created_at

            # Get user names
            for user_id in user_stats.keys():
                user = await self.get_user(user_id)
                if user:
                    user_stats[user_id]['user_name'] = user['name']
                    user_stats[user_id]['user_email'] = user['email']
                else:
                    user_stats[user_id]['user_name'] = 'Unknown'
                    user_stats[user_id]['user_email'] = 'unknown@example.com'

            # Return sorted by total cost descending
            return sorted(
                user_stats.values(),
                key=lambda x: x['total_cost'],
                reverse=True
            )


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
