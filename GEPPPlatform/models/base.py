"""
Base configuration for all models
"""

from sqlalchemy import Column, Boolean, DateTime, TIMESTAMP, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import enum

Base = declarative_base()

class PlatformEnum(enum.Enum):
    NA = 'NA'
    WEB = 'WEB'
    MOBILE = 'MOBILE'
    API = 'API'
    GEPP_BUSINESS_WEB = 'GEPP_BUSINESS_WEB'
    GEPP_REWARD_APP = 'GEPP_REWARD_APP'
    ADMIN_WEB = 'ADMIN_WEB'
    GEPP_EPR_WEB = 'GEPP_EPR_WEB'

class BaseModel:
    """Base model with common fields"""
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_date = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_date = Column(DateTime(timezone=True))