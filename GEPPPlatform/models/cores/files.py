"""
Files - Centralized file storage management
Tracks all uploaded files with their S3 URLs and metadata
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, Enum, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
import enum
from datetime import datetime
from ..base import Base, BaseModel


class FileType(enum.Enum):
    """File type categorization"""
    transaction_image = 'transaction_image'
    transaction_record_image = 'transaction_record_image'
    profile_image = 'profile_image'
    document = 'document'
    other = 'other'


class FileStatus(enum.Enum):
    """File status tracking"""
    pending = 'pending'  # File record created, waiting for upload
    uploaded = 'uploaded'  # File successfully uploaded to S3
    processing = 'processing'  # File being processed (e.g., image optimization)
    failed = 'failed'  # Upload or processing failed
    deleted = 'deleted'  # File marked for deletion


class File(Base, BaseModel):
    """
    Centralized file storage table
    Stores S3 URLs and metadata for all uploaded files
    """
    __tablename__ = 'files'

    # File identification
    file_type = Column(Enum(FileType), nullable=False, default=FileType.other)
    status = Column(Enum(FileStatus), nullable=False, default=FileStatus.pending)

    # S3 storage information
    url = Column(Text, nullable=False)  # Full S3 URL
    s3_key = Column(Text, nullable=False)  # S3 key/path
    s3_bucket = Column(String(255), nullable=True)  # S3 bucket name

    # File metadata
    original_filename = Column(String(500), nullable=True)
    file_size = Column(BigInteger, nullable=True)  # Size in bytes
    mime_type = Column(String(100), nullable=True)

    # Ownership and access control
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False, index=True)
    uploader_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False, index=True)

    # Related entity tracking (optional, for reporting and cleanup)
    related_entity_type = Column(String(100), nullable=True)  # e.g., 'transaction', 'transaction_record', 'user'
    related_entity_id = Column(BigInteger, nullable=True)  # ID of the related entity

    # Additional metadata (JSONB for flexibility)
    # Note: Using 'file_metadata' as attribute name because 'metadata' is reserved by SQLAlchemy
    file_metadata = Column('metadata', JSONB, nullable=False, default={})  # Store extra info like dimensions, duration, etc.

    # Processing information
    processing_error = Column(Text, nullable=True)  # Error message if processing failed
    upload_completed_at = Column(BigInteger, nullable=True)  # Timestamp when upload was completed

    # Relationships
    organization = relationship("Organization", foreign_keys=[organization_id])
    uploader = relationship("UserLocation", foreign_keys=[uploader_id])

    # Indexes for efficient queries
    __table_args__ = (
        Index('idx_files_org_type', 'organization_id', 'file_type'),
        Index('idx_files_status', 'status'),
        Index('idx_files_related_entity', 'related_entity_type', 'related_entity_id'),
        Index('idx_files_uploader', 'uploader_id'),
        Index('idx_files_created_date', 'created_date'),
    )

    def __repr__(self):
        return f"<File(id={self.id}, type={self.file_type.value}, status={self.status.value}, org={self.organization_id})>"

    def mark_uploaded(self, file_size: int = None, mime_type: str = None):
        """Mark file as successfully uploaded"""
        self.status = FileStatus.uploaded
        self.upload_completed_at = int(datetime.now().timestamp())
        if file_size:
            self.file_size = file_size
        if mime_type:
            self.mime_type = mime_type

    def mark_failed(self, error_message: str):
        """Mark file upload/processing as failed"""
        self.status = FileStatus.failed
        self.processing_error = error_message

    def to_dict(self):
        """Convert file to dictionary for API responses"""
        return {
            'id': self.id,
            'file_type': self.file_type.value,
            'status': self.status.value,
            'url': self.url,
            's3_key': self.s3_key,
            's3_bucket': self.s3_bucket,
            'original_filename': self.original_filename,
            'file_size': self.file_size,
            'mime_type': self.mime_type,
            'organization_id': self.organization_id,
            'uploader_id': self.uploader_id,
            'related_entity_type': self.related_entity_type,
            'related_entity_id': self.related_entity_id,
            'metadata': self.file_metadata,
            'is_active': self.is_active,
            'created_date': self.created_date.isoformat() if self.created_date else None,
            'updated_date': self.updated_date.isoformat() if self.updated_date else None,
            'upload_completed_at': self.upload_completed_at
        }
