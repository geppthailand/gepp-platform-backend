"""
Database configuration and connection management for SQLAlchemy
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager

# Import all models to ensure they're registered with SQLAlchemy
from GEPPPlatform.models.base import Base
from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.models.users.user_related import UserPreference, UserInvitation, UserBank, UserSubscription, UserActivity, UserDevice
from GEPPPlatform.models.cores.roles import SystemRole, SystemPermission
from GEPPPlatform.models.subscriptions.organizations import Organization, OrganizationInfo
from GEPPPlatform.models.subscriptions.subscription_models import SubscriptionPlan, Subscription, OrganizationPermission, OrganizationRole
from GEPPPlatform.models.cores.locations import LocationCountry, LocationProvince, LocationDistrict, LocationSubdistrict
from GEPPPlatform.models.cores.references import Currency, Material, Nationality, PhoneNumberCountryCode

class DatabaseManager:
    _instance = None
    _engine = None
    _SessionLocal = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._engine is None:
            self.setup_database()
    
    def setup_database(self):
        """Setup database connection and session factory"""
        database_url = self._get_database_url()
        
        self._engine = create_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            echo=False  # Set to True for SQL debugging
        )
        
        self._SessionLocal = scoped_session(
            sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self._engine
            )
        )
    
    def _get_database_url(self):
        """Construct database URL from environment variables"""
        db_user = os.environ.get("DB_USER", "postgres")
        db_pass = os.environ.get("DB_PASS", "")
        db_host = os.environ.get("DB_HOST", "localhost")
        db_port = os.environ.get("DB_PORT", "5432")
        db_name = os.environ.get("DB_NAME", "gepp_platform")
        
        return f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    
    def get_engine(self):
        """Get the SQLAlchemy engine"""
        return self._engine
    
    def get_session_factory(self):
        """Get the session factory"""
        return self._SessionLocal
    
    @contextmanager
    def get_session(self):
        """Get a database session with automatic cleanup"""
        session = self._SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def create_tables(self):
        """Create all tables defined in models"""
        Base.metadata.create_all(bind=self._engine)
    
    def drop_tables(self):
        """Drop all tables (use with caution!)"""
        Base.metadata.drop_all(bind=self._engine)

# Global database manager instance
db_manager = DatabaseManager()

# Convenience functions
def get_session():
    """Get a database session context manager"""
    return db_manager.get_session()

def get_db_session():
    """Get a plain database session (for direct use)"""
    return db_manager.get_session_factory()()

def get_engine():
    """Get the database engine"""
    return db_manager.get_engine()

def create_tables():
    """Create all database tables"""
    return db_manager.create_tables()