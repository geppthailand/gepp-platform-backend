"""
Knowledge Management Module
Comprehensive document management and RAG (Retrieval-Augmented Generation) system
with pgvector support for semantic search
"""

# Core models
from .files import (
    OwnerType, FileType, FileCategory, ProcessingStatus,
    KmFile, KmChunk, KmFileTag, KmChunkTag
)

# Temporary processing
from .temp_processing import (
    TempFileBatch, TempFile, TempChunk, BatchProcessingStatus
)

# Management and analytics
from .management import (
    KmAnalytics, KmSearch, KmSearchResult, KmUserAccess,
    KmAuditLog, KmConfiguration, KmIndexing, SearchType, SearchStatus,
    DocumentApprovalStatus, ReviewPriority, AdminAction, AuditType,
    KmDocumentApproval, KmAdminAction, KmDocumentAudit, KmContentStatus
)

__all__ = [
    # Core models
    'OwnerType', 'FileType', 'FileCategory', 'ProcessingStatus',
    'KmFile', 'KmChunk', 'KmFileTag', 'KmChunkTag',
    
    # Temporary processing
    'TempFileBatch', 'TempFile', 'TempChunk', 'BatchProcessingStatus',
    
    # Management models
    'KmAnalytics', 'KmSearch', 'KmSearchResult', 'KmUserAccess',
    'KmAuditLog', 'KmConfiguration', 'KmIndexing', 'SearchType', 'SearchStatus',
    
    # Admin console models
    'DocumentApprovalStatus', 'ReviewPriority', 'AdminAction', 'AuditType',
    'KmDocumentApproval', 'KmAdminAction', 'KmDocumentAudit', 'KmContentStatus'
]