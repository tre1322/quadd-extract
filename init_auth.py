"""
Initialize authentication system.

This script creates the default admin user if it doesn't exist.
Useful for fresh installations or resetting the admin account.
"""
import asyncio
import uuid
import bcrypt
from src.db.database import get_database
from src.db.models import UserModel


async def init_auth():
    """Initialize authentication system with default admin user."""
    
    print("Initializing authentication system...")
    
    # Get database connection
    db = await get_database()
    
    # Check if admin user exists
    async with db.session_factory() as session:
        from sqlalchemy import select
        
        result = await session.execute(
            select(UserModel).where(UserModel.email == 'admin@quadd.com')
        )
        existing_admin = result.scalar_one_or_none()
        
        if existing_admin:
            print("✓ Admin user already exists")
            print(f"  Email: {existing_admin.email}")
            print(f"  Name: {existing_admin.name}")
            print(f"  Role: {existing_admin.role}")
            return
        
        # Create default admin user
        print("Creating default admin user...")
        
        admin_id = str(uuid.uuid4())
        password = "changeme123"
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        admin_user = UserModel(
            id=admin_id,
            email='admin@quadd.com',
            password_hash=password_hash,
            name='Admin',
            role='admin'
        )
        
        session.add(admin_user)
        await session.commit()
        
        print("✓ Default admin user created successfully!")
        print("\n" + "="*60)
        print("DEFAULT ADMIN CREDENTIALS")
        print("="*60)
        print(f"Email:    admin@quadd.com")
        print(f"Password: changeme123")
        print("="*60)
        print("\n⚠️  SECURITY WARNING:")
        print("Please change this password immediately after first login!")
        print("This is a temporary password for initial setup only.")
        print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(init_auth())
