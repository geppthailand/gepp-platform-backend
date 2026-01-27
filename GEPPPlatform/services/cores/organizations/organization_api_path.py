"""
Organization API Path Management

Utilities for generating and managing organization API paths for custom API access.
"""

import hashlib
import secrets
from sqlalchemy.orm import Session
from GEPPPlatform.models.subscriptions.organizations import Organization


def generate_api_path() -> str:
    """
    Generate a secure random API path for an organization.
    
    Returns:
        A 32-character URL-safe random string
    """
    # Generate 24 random bytes and encode as URL-safe base64 (32 chars)
    # Using secrets module for cryptographically strong randomness
    random_bytes = secrets.token_bytes(24)
    # Convert to hex string (48 chars) and take first 32
    return hashlib.sha256(random_bytes).hexdigest()[:32]


def set_organization_api_path(db_session: Session, organization_id: int) -> str:
    """
    Generate and set a unique API path for an organization.
    
    Args:
        db_session: Database session
        organization_id: The organization ID
        
    Returns:
        The generated API path
        
    Raises:
        ValueError: If organization not found or already has an api_path
    """
    org = db_session.query(Organization).filter(
        Organization.id == organization_id
    ).first()
    
    if not org:
        raise ValueError(f"Organization {organization_id} not found")
    
    if org.api_path:
        raise ValueError(f"Organization {organization_id} already has api_path: {org.api_path}")
    
    # Generate unique api_path
    max_attempts = 10
    for _ in range(max_attempts):
        api_path = generate_api_path()
        
        # Check if unique
        existing = db_session.query(Organization).filter(
            Organization.api_path == api_path
        ).first()
        
        if not existing:
            org.api_path = api_path
            db_session.commit()
            return api_path
    
    raise ValueError("Failed to generate unique api_path after multiple attempts")


def get_organization_by_api_path(db_session: Session, api_path: str) -> Organization:
    """
    Look up an organization by its API path.
    
    Args:
        db_session: Database session
        api_path: The API path to search for
        
    Returns:
        Organization if found, None otherwise
    """
    return db_session.query(Organization).filter(
        Organization.api_path == api_path,
        Organization.deleted_date.is_(None)
    ).first()
