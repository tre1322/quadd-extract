"""
Authentication utilities for JWT token handling and password verification.
"""
import os
import jwt
import bcrypt
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, Header, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# JWT Configuration
JWT_SECRET = os.getenv('JWT_SECRET', 'dev-secret-change-in-production-please')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24

# Warn if using default JWT secret
if JWT_SECRET == 'dev-secret-change-in-production-please':
    logger.warning("=" * 80)
    logger.warning("WARNING: Using default JWT_SECRET!")
    logger.warning("This is INSECURE for production. Set JWT_SECRET environment variable.")
    logger.warning("Generate a secure secret with: python -c 'import secrets; print(secrets.token_urlsafe(32))'")
    logger.warning("=" * 80)

# Security scheme for Swagger UI
security = HTTPBearer()


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
        password: Plain text password
        
    Returns:
        Hashed password string
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.
    
    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password to check against
        
    Returns:
        True if password matches, False otherwise
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False


def create_access_token(user_id: str, email: str, role: str) -> str:
    """
    Create a JWT access token.
    
    Args:
        user_id: User ID
        email: User email
        role: User role ('user' or 'admin')
        
    Returns:
        JWT token string
    """
    expires = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    
    payload = {
        'sub': user_id,  # Subject (user ID)
        'email': email,
        'role': role,
        'exp': expires,  # Expiration time
        'iat': datetime.utcnow()  # Issued at
    }
    
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded payload dict, or None if invalid
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


async def get_current_user_from_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    FastAPI dependency to get current user from JWT token.
    
    Extracts and validates the JWT token from the Authorization header.
    
    Args:
        credentials: HTTP Bearer credentials from request
        
    Returns:
        User payload dict with 'sub' (user_id), 'email', 'role'
        
    Raises:
        HTTPException: 401 if token is missing or invalid
    """
    token = credentials.credentials
    
    payload = decode_access_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )
    
    return payload


async def get_current_user(
    user_data: dict = Depends(get_current_user_from_token)
) -> dict:
    """
    FastAPI dependency to get current authenticated user.
    
    Returns:
        User data dict with user_id, email, role
        
    Raises:
        HTTPException: 401 if not authenticated
    """
    return {
        'user_id': user_data['sub'],
        'email': user_data['email'],
        'role': user_data['role']
    }


async def get_admin_user(
    user_data: dict = Depends(get_current_user)
) -> dict:
    """
    FastAPI dependency to get current admin user.
    
    Requires the user to be authenticated AND have admin role.
    
    Returns:
        User data dict with user_id, email, role
        
    Raises:
        HTTPException: 401 if not authenticated, 403 if not admin
    """
    if user_data['role'] != 'admin':
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required"
        )
    
    return user_data


# Optional: dependency for optional authentication
async def get_current_user_optional(
    authorization: Optional[str] = Header(None)
) -> Optional[dict]:
    """
    FastAPI dependency to get current user if authenticated, None otherwise.
    
    Useful for endpoints that work differently based on authentication status.
    
    Returns:
        User data dict if authenticated, None otherwise
    """
    if not authorization:
        return None
    
    if not authorization.startswith('Bearer '):
        return None
    
    token = authorization.replace('Bearer ', '')
    payload = decode_access_token(token)
    
    if payload is None:
        return None
    
    return {
        'user_id': payload['sub'],
        'email': payload['email'],
        'role': payload['role']
    }
