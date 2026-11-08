"""
Identity, Organization, and Membership Service Layer.
Enforces multi-tenant organization isolation and Role-Based Access Control (RBAC).
"""

import hashlib
import hmac
import os
from typing import List, Optional, Set
import uuid

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.db.models.identity import Membership, Organization, User, UserRole
from app.schemas.identity import (
    MembershipCreate,
    MembershipResponse,
    OrganizationCreate,
    OrganizationResponse,
    UserCreate,
    UserResponse,
)


class IdentityServiceError(Exception):
    """Base exception for identity and organization operations."""
    pass


class OrganizationNotFoundError(IdentityServiceError):
    """Raised when an organization workspace does not exist."""
    pass


class UserNotFoundError(IdentityServiceError):
    """Raised when a user account does not exist."""
    pass


class OrganizationAccessDeniedError(IdentityServiceError):
    """Raised when a user attempts to access an organization they do not belong to."""
    pass


class InsufficientPermissionsError(IdentityServiceError):
    """Raised when a user role lacks permissions for the requested operation."""
    pass


class DuplicateEntityError(IdentityServiceError):
    """Raised when creating an organization or user that already exists."""
    pass


def hash_password(password: str) -> str:
    """Generate a salted PBKDF2-HMAC-SHA256 password hash."""
    salt = os.urandom(16).hex()
    pwd_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000
    ).hex()
    return f"{salt}${pwd_hash}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against salted PBKDF2 hash."""
    try:
        salt, expected_hash = hashed_password.split("$", 1)
        computed_hash = hashlib.pbkdf2_hmac(
            "sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), 100000
        ).hex()
        return hmac.compare_digest(computed_hash, expected_hash)
    except Exception:
        return False


class IdentityService:
    """
    Manages tenant workspaces, user accounts, and RBAC memberships.
    Enforces that users can never access data across organization boundaries.
    """

    # Role hierarchy: ADMIN > STEWARD > USER > AUDITOR (read-only)
    ROLE_PERMISSIONS = {
        UserRole.ADMIN.value: {"read", "write", "admin", "audit", "approve"},
        UserRole.STEWARD.value: {"read", "write", "audit", "approve"},
        UserRole.USER.value: {"read", "write"},
        UserRole.AUDITOR.value: {"read", "audit"},
    }

    # -------------------------------------------------------------
    # Organization Management
    # -------------------------------------------------------------
    def create_organization(self, org_in: OrganizationCreate, db: Session) -> OrganizationResponse:
        """Create a new isolated organization workspace."""
        existing = db.scalar(
            select(Organization).where(
                (Organization.name == org_in.name) | (Organization.slug == org_in.slug)
            )
        )
        if existing:
            raise DuplicateEntityError(
                f"Organization with name '{org_in.name}' or slug '{org_in.slug}' already exists."
            )

        org = Organization(
            id=uuid.uuid4(),
            name=org_in.name.strip(),
            slug=org_in.slug.strip().lower(),
        )
        db.add(org)
        db.commit()
        db.refresh(org)
        return OrganizationResponse.model_validate(org)

    def get_organization(self, org_id: uuid.UUID, db: Session) -> OrganizationResponse:
        """Retrieve organization by UUID."""
        org = db.scalar(select(Organization).where(Organization.id == org_id))
        if not org:
            raise OrganizationNotFoundError(f"Organization with ID {org_id} was not found.")
        return OrganizationResponse.model_validate(org)

    def list_organizations(self, db: Session) -> List[OrganizationResponse]:
        """List active organizations."""
        orgs = db.scalars(select(Organization).where(Organization.is_active == True)).all()
        return [OrganizationResponse.model_validate(o) for o in orgs]

    # -------------------------------------------------------------
    # User Management
    # -------------------------------------------------------------
    def create_user(self, user_in: UserCreate, db: Session) -> UserResponse:
        """Create a new user account with secure password hashing."""
        existing = db.scalar(select(User).where(User.email == user_in.email.lower()))
        if existing:
            raise DuplicateEntityError(f"User with email '{user_in.email}' already exists.")

        user = User(
            id=uuid.uuid4(),
            email=user_in.email.lower().strip(),
            hashed_password=hash_password(user_in.password),
            full_name=user_in.full_name,
            is_superuser=user_in.is_superuser,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return UserResponse.model_validate(user)

    def get_user(self, user_id: uuid.UUID, db: Session) -> UserResponse:
        """Retrieve user by UUID."""
        user = db.scalar(select(User).where(User.id == user_id))
        if not user:
            raise UserNotFoundError(f"User with ID {user_id} was not found.")
        return UserResponse.model_validate(user)

    # -------------------------------------------------------------
    # Membership & RBAC Enforcement
    # -------------------------------------------------------------
    def assign_membership(self, mem_in: MembershipCreate, db: Session) -> MembershipResponse:
        """Assign a user to an organization with a specific RBAC role."""
        org = db.scalar(select(Organization).where(Organization.id == mem_in.organization_id))
        if not org:
            raise OrganizationNotFoundError(f"Organization with ID {mem_in.organization_id} was not found.")

        user = db.scalar(select(User).where(User.id == mem_in.user_id))
        if not user:
            raise UserNotFoundError(f"User with ID {mem_in.user_id} was not found.")

        existing = db.scalar(
            select(Membership).where(
                Membership.organization_id == mem_in.organization_id,
                Membership.user_id == mem_in.user_id,
            )
        )
        if existing:
            existing.role = mem_in.role.value
            db.commit()
            db.refresh(existing)
            return MembershipResponse.model_validate(existing)

        membership = Membership(
            id=uuid.uuid4(),
            organization_id=mem_in.organization_id,
            user_id=mem_in.user_id,
            role=mem_in.role.value,
        )
        db.add(membership)
        db.commit()
        db.refresh(membership)
        return MembershipResponse.model_validate(membership)

    def get_user_membership(
        self, user_id: uuid.UUID, org_id: uuid.UUID, db: Session
    ) -> Optional[Membership]:
        """Fetch active membership record for a user in an organization."""
        return db.scalar(
            select(Membership).where(
                Membership.user_id == user_id,
                Membership.organization_id == org_id,
                Membership.is_active == True,
            )
        )

    def require_organization_access(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        db: Session,
        required_permission: Optional[str] = None,
        allowed_roles: Optional[Set[UserRole]] = None,
    ) -> Membership:
        """
        Enforce multi-tenant organization boundary and role-based permissions:
        1. Verifies user belongs to the target organization (raises OrganizationAccessDeniedError if not).
        2. Verifies user's role satisfies required permission or allowed role set.
        """
        user = db.scalar(select(User).where(User.id == user_id))
        if not user:
            raise UserNotFoundError(f"User with ID {user_id} does not exist.")

        # Superusers can access all workspaces with admin permissions
        if user.is_superuser:
            # Return or synthesize a superuser membership
            existing_mem = self.get_user_membership(user_id, org_id, db)
            if existing_mem:
                return existing_mem
            return Membership(
                id=uuid.uuid4(),
                organization_id=org_id,
                user_id=user_id,
                role=UserRole.ADMIN.value,
            )

        membership = self.get_user_membership(user_id, org_id, db)
        if not membership:
            raise OrganizationAccessDeniedError(
                f"Access denied: User '{user.email}' is not a member of organization '{org_id}'."
            )

        # Check allowed roles if specified
        if allowed_roles:
            role_values = {r.value if isinstance(r, UserRole) else str(r) for r in allowed_roles}
            if membership.role not in role_values:
                raise InsufficientPermissionsError(
                    f"Role '{membership.role}' lacks required role from {role_values} for organization '{org_id}'."
                )

        # Check granular permission if specified
        if required_permission:
            user_permissions = self.ROLE_PERMISSIONS.get(membership.role, set())
            if required_permission not in user_permissions:
                raise InsufficientPermissionsError(
                    f"Role '{membership.role}' lacks '{required_permission}' permission for organization '{org_id}'."
                )

        return membership
