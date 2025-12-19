-- Quadd Extract Database Schema
-- SQLite database for storing processors, examples, and extraction history

-- Processors table
-- Stores learned transformation rules for document types
CREATE TABLE IF NOT EXISTS processors (
    id TEXT PRIMARY KEY,  -- UUID
    name TEXT NOT NULL UNIQUE,  -- Human-readable name like "windom_basketball"
    document_type TEXT NOT NULL,  -- "basketball", "hockey", etc.
    processor_json TEXT NOT NULL,  -- Full Processor serialized as JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_used TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_processors_type ON processors(document_type);
CREATE INDEX IF NOT EXISTS idx_processors_updated ON processors(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_processors_name ON processors(name);

-- Examples table
-- Stores example documents used for learning processors
CREATE TABLE IF NOT EXISTS examples (
    id TEXT PRIMARY KEY,
    processor_id TEXT,
    filename TEXT NOT NULL,
    document_ir_json TEXT NOT NULL,  -- Full DocumentIR as JSON
    desired_output TEXT NOT NULL,  -- Expected formatted output
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(processor_id) REFERENCES processors(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_examples_processor ON examples(processor_id);
CREATE INDEX IF NOT EXISTS idx_examples_created ON examples(created_at DESC);

-- Extractions table
-- Audit trail of all document extractions
CREATE TABLE IF NOT EXISTS extractions (
    id TEXT PRIMARY KEY,
    processor_id TEXT,
    filename TEXT NOT NULL,
    output_text TEXT,
    confidence REAL,
    success BOOLEAN,
    error_message TEXT,
    warnings TEXT,  -- JSON array of warnings
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processing_time_ms INTEGER,
    FOREIGN KEY(processor_id) REFERENCES processors(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_extractions_processor ON extractions(processor_id);
CREATE INDEX IF NOT EXISTS idx_extractions_created ON extractions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_extractions_success ON extractions(success);
