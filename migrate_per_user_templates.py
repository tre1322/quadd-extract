"""
Database migration script to make template names unique per user.

This script:
1. Recreates the processors table with a composite unique constraint on (user_id, name)
2. Migrates existing data to the new table
3. Preserves all existing processors and their relationships

Run this once to upgrade an existing database.
"""
import sqlite3
from pathlib import Path

DB_PATH = "quadd_extract.db"


def migrate_database():
    """Migrate existing database to make template names unique per user."""

    if not Path(DB_PATH).exists():
        print(f"Database {DB_PATH} does not exist. No migration needed.")
        print("The new schema will be created automatically on first run.")
        return

    print(f"Migrating database: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if processors table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='processors'
        """)

        if not cursor.fetchone():
            print("[OK] Processors table doesn't exist yet. No migration needed.")
            return

        # Check current schema - look for the unique constraint
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='processors'")
        current_schema = cursor.fetchone()[0]

        # Check if already migrated
        if "UNIQUE(user_id, name)" in current_schema or "uq_user_processor_name" in current_schema:
            print("[OK] Database already has per-user unique constraint. No migration needed.")
            return

        print("Starting migration to per-user unique template names...")

        # Step 1: Rename the old table
        print("  1. Backing up existing processors table...")
        cursor.execute("ALTER TABLE processors RENAME TO processors_old")

        # Step 2: Create new table with composite unique constraint
        print("  2. Creating new processors table with per-user unique constraint...")
        cursor.execute("""
            CREATE TABLE processors (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                document_type TEXT NOT NULL,
                processor_json TEXT NOT NULL,
                user_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                version INTEGER DEFAULT 1,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                last_used TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, name)
            )
        """)

        # Step 3: Copy data from old table to new table
        print("  3. Migrating existing processor data...")
        cursor.execute("""
            INSERT INTO processors
            (id, name, document_type, processor_json, user_id, created_at, updated_at,
             version, success_count, failure_count, last_used)
            SELECT id, name, document_type, processor_json, user_id, created_at, updated_at,
                   version, success_count, failure_count, last_used
            FROM processors_old
        """)

        rows_migrated = cursor.rowcount
        print(f"     Migrated {rows_migrated} processors")

        # Step 4: Recreate indexes
        print("  4. Recreating indexes...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processors_type ON processors(document_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processors_updated ON processors(updated_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processors_name ON processors(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processors_user ON processors(user_id)")

        # Step 5: Drop old table
        print("  5. Cleaning up old table...")
        cursor.execute("DROP TABLE processors_old")

        conn.commit()
        print("\n[SUCCESS] Migration completed successfully!")
        print(f"  {rows_migrated} processor(s) migrated")
        print("\nTemplates are now unique per user. Multiple users can have templates with the same name.")

    except sqlite3.IntegrityError as e:
        conn.rollback()
        print(f"\n[ERROR] Migration failed due to data conflict: {e}")
        print("\nThis likely means you have duplicate template names for the same user.")
        print("Please resolve duplicate names before running this migration.")

        # Try to restore from backup
        try:
            cursor.execute("DROP TABLE IF EXISTS processors")
            cursor.execute("ALTER TABLE processors_old RENAME TO processors")
            conn.commit()
            print("[OK] Database rolled back to original state")
        except:
            print("[ERROR] Could not rollback. Please restore from backup!")
        raise
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")

        # Try to restore from backup
        try:
            cursor.execute("DROP TABLE IF EXISTS processors")
            cursor.execute("ALTER TABLE processors_old RENAME TO processors")
            conn.commit()
            print("[OK] Database rolled back to original state")
        except:
            print("[ERROR] Could not rollback. Please restore from backup!")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_database()
