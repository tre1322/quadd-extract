-- Quadd Extract Database Schema
-- SQLite database for storing processors, examples, and extraction history

-- Users table
-- Stores user accounts for authentication
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,  -- UUID
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',  -- 'user' or 'admin'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- Processors table
-- Stores learned transformation rules for document types
CREATE TABLE IF NOT EXISTS processors (
    id TEXT PRIMARY KEY,  -- UUID
    name TEXT NOT NULL,  -- Human-readable name like "windom_basketball"
    document_type TEXT NOT NULL,  -- "basketball", "hockey", etc.
    processor_json TEXT NOT NULL,  -- Full Processor serialized as JSON
    user_id TEXT,  -- Link to user who created this processor
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_used TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, name)  -- Template names must be unique per user
);

CREATE INDEX IF NOT EXISTS idx_processors_type ON processors(document_type);
CREATE INDEX IF NOT EXISTS idx_processors_updated ON processors(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_processors_name ON processors(name);
CREATE INDEX IF NOT EXISTS idx_processors_user ON processors(user_id);

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

-- Usage logs table
-- Tracks API usage for analytics and billing
CREATE TABLE IF NOT EXISTS usage_logs (
    id TEXT PRIMARY KEY,  -- UUID
    user_id TEXT NOT NULL,
    processor_id TEXT,  -- Nullable in case processor is deleted
    processor_name TEXT NOT NULL,  -- Store name in case processor deleted
    document_type TEXT NOT NULL,
    action_type TEXT NOT NULL DEFAULT 'transform',  -- 'learn' or 'transform'
    input_type TEXT NOT NULL,  -- 'pdf' or 'text'
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    total_tokens INTEGER NOT NULL,
    cost REAL NOT NULL,  -- Calculated cost in USD
    success BOOLEAN NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(processor_id) REFERENCES processors(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_usage_logs_user ON usage_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_logs_processor ON usage_logs(processor_id);
CREATE INDEX IF NOT EXISTS idx_usage_logs_created ON usage_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_logs_success ON usage_logs(success);
CREATE INDEX IF NOT EXISTS idx_usage_logs_action ON usage_logs(action_type);
