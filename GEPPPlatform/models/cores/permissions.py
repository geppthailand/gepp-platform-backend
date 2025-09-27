"""
Permission-related models
"""

from sqlalchemy import Column, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from ..base import Base, BaseModel

class PermissionType(Base, BaseModel):
    __tablename__ = 'permission_types'
    
    name = Column(String(255))
    description = Column(Text)

class Permission(Base, BaseModel):
    __tablename__ = 'permissions'
    
    permission_type_id = Column(ForeignKey('permission_types.id'))
    name = Column(String(255))
    description = Column(Text)
    
    permission_type = relationship("PermissionType")