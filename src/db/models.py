"""
SQLAlchemy ORM models for the database.
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class ProcessorModel(Base):
    """ORM model for processors table."""
    __tablename__ = 'processors'

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    document_type = Column(String, nullable=False)
    processor_json = Column(Text, nullable=False)
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
