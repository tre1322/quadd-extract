"""
SQLAlchemy ORM models for the database.
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class UserModel(Base):
    """ORM model for users table."""
    __tablename__ = 'users'

    id = Column(String, primary_key=True)  # UUID
    email = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False, default='user')  # 'user' or 'admin'
    created_at = Column(DateTime, default=datetime.utcnow)


class ProcessorModel(Base):
    """ORM model for processors table."""
    __tablename__ = 'processors'

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    document_type = Column(String, nullable=False)
    processor_json = Column(Text, nullable=False)
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=True)  # Link to user
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    version = Column(Integer, default=1)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    last_used = Column(DateTime, nullable=True)


class ExampleModel(Base):
    """ORM model for examples table."""
    __tablename__ = 'examples'

    id = Column(String, primary_key=True)
    processor_id = Column(String, ForeignKey('processors.id', ondelete='CASCADE'), nullable=True)
    filename = Column(String, nullable=False)
    document_ir_json = Column(Text, nullable=False)
    desired_output = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ExtractionModel(Base):
    """ORM model for extractions table."""
    __tablename__ = 'extractions'

    id = Column(String, primary_key=True)
    processor_id = Column(String, ForeignKey('processors.id', ondelete='SET NULL'), nullable=True)
    filename = Column(String, nullable=False)
    output_text = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)
    warnings = Column(Text, nullable=True)  # JSON array
    created_at = Column(DateTime, default=datetime.utcnow)
    processing_time_ms = Column(Integer, nullable=True)


class UsageLogModel(Base):
    """ORM model for usage_logs table."""
    __tablename__ = 'usage_logs'

    id = Column(String, primary_key=True)  # UUID
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    processor_id = Column(String, ForeignKey('processors.id', ondelete='SET NULL'), nullable=True)
    processor_name = Column(String, nullable=False)
    document_type = Column(String, nullable=False)
    action_type = Column(String, nullable=False, default='transform')  # 'learn' or 'transform'
    input_type = Column(String, nullable=False)  # 'pdf' or 'text'
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    total_tokens = Column(Integer, nullable=False)
    cost = Column(Float, nullable=False)  # USD
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
