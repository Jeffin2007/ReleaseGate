"""
Pydantic schemas for Organizations, Users, and Memberships (RBAC).
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

from app.db.models.identity import UserRole


class OrganizationCreate(BaseModel):
    """Payload to create a new multi-tenant organization workspace."""
    name: str = Field(min_length=2, max_length=255, description="Unique organization workspace name")
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9_-]+$", description="URL-safe unique slug")


class OrganizationResponse(BaseModel):
    """Organization workspace details."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    """Payload to register a new user account."""
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", description="Unique email address")
    password: str = Field(min_length=8, description="Plaintext password to hash")
    full_name: Optional[str] = Field(default=None, max_length=255)
    is_superuser: bool = False


class UserResponse(BaseModel):
    """Public user account record."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: Optional[str]
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime


class MembershipCreate(BaseModel):
    """Payload to assign a user to an organization with a specific RBAC role."""
    organization_id: UUID
    user_id: UUID
    role: UserRole = Field(default=UserRole.USER, description="Assigned role: ADMIN, STEWARD, AUDITOR, USER")


class MembershipResponse(BaseModel):
    """Membership record response."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    user_id: UUID
    role: str
    is_active: bool
    created_at: datetime
