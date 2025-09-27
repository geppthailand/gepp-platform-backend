"""
Translation models
"""

from sqlalchemy import Column, String, Text
from ..base import Base, BaseModel

class Translation(Base, BaseModel):
    __tablename__ = 'translations'
    
    key = Column(String(255))
    locale_code = Column(String(10))
    value = Column(Text)