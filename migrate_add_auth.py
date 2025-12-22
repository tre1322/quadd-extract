"""
Database migration script to add authentication support.

This script:
1. Creates the users table
2. Adds user_id column to processors table
3. Creates a default admin user

Run this once to upgrade an existing database.
"""
import asyncio
import sqlite3
import uuid
import bcrypt
from pathlib import Path

DB_PATH = "quadd_extract.db"


def migrate_database():
    """Migrate existing database to add authentication support."""
    
    if not Path(DB_PATH).exists():
        print(f"Database {DB_PATH} does not exist. No migration needed.")
        print("The new schema will be created automatically on first run.")
        return
    
    print(f"Migrating database: {DB_PATH}")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if users table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='users'
        """)
        
        if not cursor.fetchone():
            print("Creating users table...")
            
            # Create users table
            cursor.execute("""
                CREATE TABLE users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX idx_users_email ON users(email)")
            cursor.execute("CREATE INDEX idx_users_role ON users(role)")
            
            print("[OK] Users table created")
        else:
            print("[OK] Users table already exists")
        
        # Check if user_id column exists in processors table
        cursor.execute("PRAGMA table_info(processors)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'user_id' not in columns:
            print("Adding user_id column to processors table...")
            cursor.execute("""
                ALTER TABLE processors ADD COLUMN user_id TEXT
            """)
            cursor.execute("CREATE INDEX idx_processors_user ON processors(user_id)")
            print("[OK] user_id column added")
        else:
            print("[OK] user_id column already exists")
        
        # Create default admin user
        cursor.execute("SELECT id FROM users WHERE email = ?", ('admin@quadd.com',))
        
        if not cursor.fetchone():
            print("Creating default admin user...")
            
            admin_id = str(uuid.uuid4())
            password = "changeme123"
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            cursor.execute("""
                INSERT INTO users (id, email, password_hash, name, role)
                VALUES (?, ?, ?, ?, ?)
            """, (admin_id, 'admin@quadd.com', password_hash, 'Admin', 'admin'))
            
            print("[OK] Default admin user created")
            print("  Email: admin@quadd.com")
            print("  Password: changeme123")
            print("  [WARNING] PLEASE CHANGE THIS PASSWORD AFTER FIRST LOGIN!")
        else:
            print("[OK] Admin user already exists")

        conn.commit()
        print("\n[SUCCESS] Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_database()
