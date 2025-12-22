#!/usr/bin/env python3
"""
Migration script to add usage tracking to existing database.

This script adds the usage_logs table to an existing QUADD database.
Run this if you're upgrading from a version without usage tracking.
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = "quadd_extract.db"

MIGRATION_SQL = """
-- Usage logs table
-- Tracks API usage for analytics and billing
CREATE TABLE IF NOT EXISTS usage_logs (
    id TEXT PRIMARY KEY,  -- UUID
    user_id TEXT NOT NULL,
    processor_id TEXT,  -- Nullable in case processor is deleted
    processor_name TEXT NOT NULL,  -- Store name in case processor deleted
    document_type TEXT NOT NULL,
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
"""


def main():
    """Run the migration."""
    db_path = Path(DB_PATH)

    if not db_path.exists():
        print(f"Error: Database file '{DB_PATH}' not found.")
        print("Run this script from the project root directory.")
        sys.exit(1)

    print(f"Adding usage tracking to database: {DB_PATH}")

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Check if usage_logs table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='usage_logs'
        """)

        if cursor.fetchone():
            print("✓ usage_logs table already exists - migration not needed")
            conn.close()
            return

        # Execute migration
        print("Creating usage_logs table and indexes...")
        cursor.executescript(MIGRATION_SQL)
        conn.commit()
        conn.close()

        print("✓ Migration successful!")
        print()
        print("Usage tracking is now enabled. Admins can view analytics in the Usage tab.")

    except Exception as e:
        print(f"✗ Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
