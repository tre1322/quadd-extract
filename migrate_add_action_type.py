#!/usr/bin/env python3
"""
Migration script to add action_type column to usage_logs table.

This script adds the action_type column to distinguish between 'learn' and 'transform' actions.
Run this if you're upgrading from a version without action_type tracking.
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = "quadd_extract.db"

MIGRATION_SQL = """
-- Add action_type column to usage_logs
ALTER TABLE usage_logs ADD COLUMN action_type TEXT NOT NULL DEFAULT 'transform';

-- Create index for action_type
CREATE INDEX IF NOT EXISTS idx_usage_logs_action ON usage_logs(action_type);
"""


def main():
    """Run the migration."""
    db_path = Path(DB_PATH)

    if not db_path.exists():
        print(f"Error: Database file '{DB_PATH}' not found.")
        print("Run this script from the project root directory.")
        sys.exit(1)

    print(f"Adding action_type column to usage_logs table: {DB_PATH}")

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Check if action_type column already exists
        cursor.execute("PRAGMA table_info(usage_logs)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'action_type' in columns:
            print("[OK] action_type column already exists - migration not needed")
            conn.close()
            return

        # Execute migration
        print("Adding action_type column and index...")
        cursor.executescript(MIGRATION_SQL)
        conn.commit()
        conn.close()

        print("[OK] Migration successful!")
        print()
        print("Action type tracking is now enabled.")
        print("The system will now distinguish between 'learn' and 'transform' actions in usage logs.")

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
