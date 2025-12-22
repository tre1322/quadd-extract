"""
Reset admin password.

This script resets the admin user's password.
Run this if you've forgotten the admin password.
"""
import asyncio
import bcrypt
from src.db.database import get_database
from src.db.models import UserModel


async def reset_admin():
    """Reset admin user password."""
    
    print("Resetting admin password...")
    
    # Get database connection
    db = await get_database()
    
    async with db.session_factory() as session:
        from sqlalchemy import select
        
        result = await session.execute(
            select(UserModel).where(UserModel.email == 'admin@quadd.com')
        )
        admin = result.scalar_one_or_none()
        
        if not admin:
            print("ERROR: Admin user not found!")
            print("Run init_auth.py first to create the admin user.")
            return
        
        # Reset password
        new_password = "changeme123"
        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        admin.password_hash = password_hash
        await session.commit()
        
        print("✓ Admin password reset successfully!")
        print("\n" + "="*60)
        print("ADMIN CREDENTIALS")
        print("="*60)
        print(f"Email:    admin@quadd.com")
        print(f"Password: changeme123")
        print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(reset_admin())
