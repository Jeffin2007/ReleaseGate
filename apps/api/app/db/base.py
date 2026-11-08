"""
SQLAlchemy 2.0 Declarative Base.
All future database entities will inherit from this base class.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy 2.0 ORM models.
    Provides metadata registry for future migrations via Alembic.
    """
    pass
