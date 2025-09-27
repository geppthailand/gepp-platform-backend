"""
Knowledge Management analytics, search, and system management models
Advanced features for KM system administration and usage analytics
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON, Enum as SQLEnum, Integer, Index
from sqlalchemy.types import DECIMAL
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
import enum
import uuid
from datetime import datetime
from ..base import Base, BaseModel

class DocumentApprovalStatus(enum.Enum):
    """Document approval workflow status"""
    PENDING_REVIEW = 'pending_review'        # Awaiting initial review
    UNDER_REVIEW = 'under_review'           # Currently being reviewed
    APPROVED = 'approved'                   # Approved for publication
    REJECTED = 'rejected'                   # Rejected, needs changes
    REVISION_REQUESTED = 'revision_requested' # Changes requested
    PUBLISHED = 'published'                 # Live and accessible
    ARCHIVED = 'archived'                   # Archived/retired
    SUSPENDED = 'suspended'                 # Temporarily suspended

class ReviewPriority(enum.Enum):
    """Document review priority levels"""
    LOW = 'low'
    NORMAL = 'normal'
    HIGH = 'high'
    URGENT = 'urgent'
    CRITICAL = 'critical'

class AdminAction(enum.Enum):
    """Administrative actions on KM content"""
    APPROVE = 'approve'
    REJECT = 'reject'
    REQUEST_REVISION = 'request_revision'
    ACTIVATE = 'activate'
    DEACTIVATE = 'deactivate'
    ARCHIVE = 'archive'
    DELETE = 'delete'
    RESTORE = 'restore'
    QUALITY_REVIEW = 'quality_review'
    EXTRACT_UPDATE = 'extract_update'

class AuditType(enum.Enum):
    """Types of audit activities"""
    CONTENT_REVIEW = 'content_review'
    QUALITY_CHECK = 'quality_check'
    ACCURACY_AUDIT = 'accuracy_audit'
    COMPLIANCE_CHECK = 'compliance_check'
    EXTRACTION_AUDIT = 'extraction_audit'
    ACCESS_REVIEW = 'access_review'
    PERFORMANCE_AUDIT = 'performance_audit'

class SearchType(enum.Enum):
    """Types of KM searches"""
    SEMANTIC = 'semantic'      # Vector similarity search
    KEYWORD = 'keyword'        # Full-text search
    HYBRID = 'hybrid'         # Combination of semantic and keyword
    STRUCTURED = 'structured'  # Filtered search by metadata

class SearchStatus(enum.Enum):
    """Search request status"""
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CACHED = 'cached'

class IndexingStatus(enum.Enum):
    """Vector indexing status"""
    PENDING = 'pending'
    INDEXING = 'indexing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    OUTDATED = 'outdated'

class KmAnalytics(Base, BaseModel):
    """Knowledge Management system analytics and metrics"""
    __tablename__ = 'km_analytics'
    
    # Analytics scope
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))  # Null for system-wide
    analysis_date = Column(DateTime, nullable=False)
    period_type = Column(String(50))  # daily, weekly, monthly, quarterly
    period_start = Column(DateTime)
    period_end = Column(DateTime)
    
    # Content metrics
    total_files = Column(Integer, default=0)
    total_chunks = Column(Integer, default=0)
    total_storage_mb = Column(BigInteger, default=0)
    
    # File type breakdown
    files_by_type = Column(JSON)  # {pdf: 150, docx: 89, ...}
    files_by_category = Column(JSON)  # {policy: 45, technical: 67, ...}
    files_by_owner_type = Column(JSON)  # {GEPP: 123, USER: 456}
    
    # Usage metrics
    total_searches = Column(BigInteger, default=0)
    unique_users = Column(Integer, default=0)
    total_file_views = Column(BigInteger, default=0)
    total_downloads = Column(BigInteger, default=0)
    
    # Search analytics
    search_by_type = Column(JSON)  # {semantic: 1234, keyword: 567, ...}
    average_search_time = Column(DECIMAL(8, 3))  # Seconds
    top_search_queries = Column(JSON)  # Most frequent queries
    search_success_rate = Column(DECIMAL(5, 2))  # Percentage of successful searches
    
    # Performance metrics
    average_response_time = Column(DECIMAL(8, 3))
    peak_concurrent_users = Column(Integer)
    system_uptime_percentage = Column(DECIMAL(5, 2))
    
    # Content quality metrics
    average_content_quality = Column(DECIMAL(3, 2))
    files_needing_review = Column(Integer)
    outdated_content_count = Column(Integer)
    duplicate_content_count = Column(Integer)
    
    # User engagement
    most_active_users = Column(JSON)  # Top users by activity
    most_accessed_content = Column(JSON)  # Top files/chunks by access
    content_ratings = Column(JSON)  # Average ratings by category
    
    # Cost tracking
    embedding_costs = Column(DECIMAL(10, 4))
    storage_costs = Column(DECIMAL(10, 4))
    compute_costs = Column(DECIMAL(10, 4))
    total_operational_cost = Column(DECIMAL(10, 4))
    
    # Growth metrics
    new_files_added = Column(Integer, default=0)
    new_users = Column(Integer, default=0)
    growth_rate = Column(DECIMAL(5, 2))  # Percentage growth
    
    # Recommendations
    optimization_suggestions = Column(JSON)
    capacity_warnings = Column(JSON)
    
    # Relationships
    organization = relationship("Organization")
    
    # Relationships
    organization = relationship("Organization")

class KmSearch(Base, BaseModel):
    """Knowledge Management search requests and caching"""
    __tablename__ = 'km_searches'
    
    # Search identification
    search_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    
    # User and context
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))
    session_id = Column(String(255))  # User session for tracking
    
    # Search query
    query_text = Column(Text, nullable=False)
    query_embedding = Column(Vector(1536))  # Query vector for semantic search
    search_type = Column(SQLEnum(SearchType), nullable=False)
    
    # Search parameters
    filters = Column(JSON)  # Search filters applied
    limit_results = Column(Integer, default=20)
    similarity_threshold = Column(DECIMAL(3, 2), default=0.7)
    
    # Search execution
    status = Column(SQLEnum(SearchStatus), default=SearchStatus.PROCESSING)
    search_started = Column(DateTime)
    search_completed = Column(DateTime)
    execution_time = Column(DECIMAL(8, 3))  # Seconds
    
    # Results
    total_results = Column(Integer, default=0)
    results_returned = Column(Integer, default=0)
    max_similarity_score = Column(DECIMAL(5, 4))
    min_similarity_score = Column(DECIMAL(5, 4))
    
    # Performance metrics
    vector_search_time = Column(DECIMAL(8, 3))
    keyword_search_time = Column(DECIMAL(8, 3))
    ranking_time = Column(DECIMAL(8, 3))
    
    # User interaction
    clicked_results = Column(JSON)  # Which results were clicked
    user_satisfaction = Column(Integer)  # 1-5 rating from user
    feedback_comment = Column(Text)
    
    # Caching
    is_cached = Column(Boolean, default=False)
    cache_key = Column(String(255))
    cache_expires = Column(DateTime)
    cache_hit_count = Column(Integer, default=0)
    
    # Error handling
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    
    # Context information
    search_context = Column(JSON)  # Additional context about the search
    user_intent = Column(String(100))  # Detected user intent
    
    # Relationships
    user_location = relationship("UserLocation")
    organization = relationship("Organization")
    search_results = relationship("KmSearchResult", back_populates="search", cascade="all, delete-orphan")

class KmSearchResult(Base, BaseModel):
    """Individual search results from KM queries"""
    __tablename__ = 'km_search_results'
    
    search_id = Column(BigInteger, ForeignKey('km_searches.id'), nullable=False)
    
    # Result identification
    chunk_id = Column(BigInteger, ForeignKey('km_chunks.id'))
    file_id = Column(BigInteger, ForeignKey('km_files.id'))
    
    # Ranking and relevance
    rank = Column(Integer, nullable=False)  # Position in results (1-based)
    similarity_score = Column(DECIMAL(5, 4))  # Vector similarity score
    keyword_score = Column(DECIMAL(5, 4))    # Keyword match score
    final_score = Column(DECIMAL(5, 4))      # Combined final ranking score
    
    # Result metadata
    result_type = Column(String(50))  # chunk, file, summary
    snippet = Column(Text)  # Highlighted snippet of matching content
    context = Column(Text)   # Surrounding context for the match
    
    # Interaction tracking
    was_clicked = Column(Boolean, default=False)
    click_timestamp = Column(DateTime)
    time_on_result = Column(Integer)  # Seconds spent viewing result
    
    # Relevance feedback
    user_rating = Column(Integer)  # 1-5 rating from user
    relevance_feedback = Column(String(20))  # relevant, not_relevant, partially_relevant
    
    # Additional scoring factors
    recency_score = Column(DECIMAL(3, 2))    # How recent the content is
    authority_score = Column(DECIMAL(3, 2))  # Authority of the source
    popularity_score = Column(DECIMAL(3, 2)) # How often this content is accessed
    
    # Relationships
    search = relationship("KmSearch", back_populates="search_results")
    chunk = relationship("KmChunk")
    file = relationship("KmFile")

class KmUserAccess(Base, BaseModel):
    """User access patterns and permissions for KM content"""
    __tablename__ = 'km_user_access'
    
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    
    # Access levels
    can_search = Column(Boolean, default=True)
    can_upload = Column(Boolean, default=False)
    can_manage_files = Column(Boolean, default=False)
    can_admin = Column(Boolean, default=False)
    
    # Content access restrictions
    accessible_categories = Column(JSON)  # Categories user can access
    restricted_categories = Column(JSON)  # Categories user cannot access
    max_file_size_mb = Column(Integer, default=100)  # Max upload size
    
    # Usage quotas
    daily_search_limit = Column(Integer, default=100)
    monthly_upload_limit = Column(Integer, default=50)  # Files per month
    storage_quota_mb = Column(Integer, default=1000)  # Storage quota for uploads
    
    # Current usage
    searches_today = Column(Integer, default=0)
    uploads_this_month = Column(Integer, default=0)
    storage_used_mb = Column(Integer, default=0)
    
    # Access patterns
    last_search_date = Column(DateTime)
    last_upload_date = Column(DateTime)
    total_searches = Column(BigInteger, default=0)
    total_uploads = Column(BigInteger, default=0)
    
    # Preferred settings
    preferred_search_type = Column(SQLEnum(SearchType), default=SearchType.HYBRID)
    default_filters = Column(JSON)  # User's default search filters
    language_preference = Column(String(10), default='en')
    
    # Notifications
    email_notifications = Column(Boolean, default=True)
    digest_frequency = Column(String(20), default='weekly')  # daily, weekly, monthly
    
    # Relationships
    user_location = relationship("UserLocation")
    organization = relationship("Organization")

class KmAuditLog(Base, BaseModel):
    """Comprehensive audit logging for KM system"""
    __tablename__ = 'km_audit_logs'
    
    # Event identification
    event_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True)
    
    # Actor information
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'))
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))
    session_id = Column(String(255))
    ip_address = Column(String(45))
    user_agent = Column(Text)
    
    # Event details
    action = Column(String(100), nullable=False)  # search, upload, delete, view, etc.
    resource_type = Column(String(50))  # file, chunk, batch, search
    resource_id = Column(BigInteger)
    resource_name = Column(String(500))
    
    # Event context
    event_details = Column(JSON)  # Detailed event information
    before_values = Column(JSON)  # Values before change
    after_values = Column(JSON)   # Values after change
    
    # Success/failure
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    error_code = Column(String(50))
    
    # Performance metrics
    execution_time = Column(DECIMAL(8, 3))  # Seconds
    
    # Risk assessment
    risk_level = Column(String(20))  # low, medium, high, critical
    security_flags = Column(JSON)  # Security-related flags
    
    # Compliance
    compliance_relevant = Column(Boolean, default=False)
    retention_period = Column(Integer)  # Days to retain this log
    
    # Relationships
    user_location = relationship("UserLocation")
    organization = relationship("Organization")

class KmDocumentApproval(Base, BaseModel):
    """Document approval workflow for GEPP internal knowledge management"""
    __tablename__ = 'km_document_approvals'
    
    # Document reference
    file_id = Column(BigInteger, ForeignKey('km_files.id'), nullable=False)
    
    # Approval workflow
    approval_status = Column(SQLEnum(DocumentApprovalStatus), default=DocumentApprovalStatus.PENDING_REVIEW)
    priority = Column(SQLEnum(ReviewPriority), default=ReviewPriority.NORMAL)
    
    # Submitter information
    submitted_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    submitted_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    submission_notes = Column(Text)  # Notes from submitter
    
    # Reviewer assignment
    assigned_reviewer_id = Column(BigInteger, ForeignKey('user_locations.id'))
    assigned_at = Column(DateTime)
    review_deadline = Column(DateTime)
    
    # Review process
    review_started_at = Column(DateTime)
    review_completed_at = Column(DateTime)
    review_duration = Column(Integer)  # Minutes spent reviewing
    
    # Decision and feedback
    decision = Column(SQLEnum(AdminAction))
    decision_made_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    decision_date = Column(DateTime)
    decision_notes = Column(Text)  # Feedback from reviewer
    
    # Revision tracking
    revision_requested = Column(Boolean, default=False)
    revision_notes = Column(Text)
    revision_completed = Column(Boolean, default=False)
    revision_completed_at = Column(DateTime)
    
    # Quality assessment
    content_quality_score = Column(DECIMAL(3, 2))  # 0-5 rating
    accuracy_rating = Column(Integer)  # 1-5 rating
    relevance_rating = Column(Integer)  # 1-5 rating
    completeness_rating = Column(Integer)  # 1-5 rating
    
    # Metadata validation
    metadata_validated = Column(Boolean, default=False)
    tags_validated = Column(Boolean, default=False)
    categorization_validated = Column(Boolean, default=False)
    
    # Publishing information
    published_at = Column(DateTime)
    published_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Audit trail
    workflow_history = Column(JSON)  # Complete workflow history
    
    # Relationships
    file = relationship("KmFile")
    submitted_by = relationship("UserLocation", foreign_keys=[submitted_by_id])
    assigned_reviewer = relationship("UserLocation", foreign_keys=[assigned_reviewer_id])
    decision_made_by = relationship("UserLocation", foreign_keys=[decision_made_by_id])
    published_by = relationship("UserLocation", foreign_keys=[published_by_id])

class KmAdminAction(Base, BaseModel):
    """Administrative actions performed on KM content"""
    __tablename__ = 'km_admin_actions'
    
    # Action identification
    action_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True)
    
    # Target resource
    target_type = Column(String(50), nullable=False)  # file, chunk, batch
    target_id = Column(BigInteger, nullable=False)
    target_name = Column(String(500))
    
    # Action details
    action = Column(SQLEnum(AdminAction), nullable=False)
    action_reason = Column(Text)
    action_details = Column(JSON)  # Additional action parameters
    
    # Actor information
    performed_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    performed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Action context
    approval_id = Column(BigInteger, ForeignKey('km_document_approvals.id'))  # If part of approval workflow
    audit_id = Column(BigInteger, ForeignKey('km_document_audits.id'))  # If part of audit
    
    # Before/after state
    previous_state = Column(JSON)  # State before action
    new_state = Column(JSON)      # State after action
    
    # Action results
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    affected_chunks_count = Column(Integer, default=0)
    
    # Approval and authorization
    requires_approval = Column(Boolean, default=False)
    approved_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    approval_date = Column(DateTime)
    
    # Impact assessment
    impact_level = Column(String(20))  # low, medium, high, critical
    affected_users_count = Column(Integer, default=0)
    rollback_available = Column(Boolean, default=True)
    
    # Relationships
    performed_by = relationship("UserLocation", foreign_keys=[performed_by_id])
    approved_by = relationship("UserLocation", foreign_keys=[approved_by_id])
    approval = relationship("KmDocumentApproval")
    audit = relationship("KmDocumentAudit")

class KmDocumentAudit(Base, BaseModel):
    """Document audit and quality assurance records"""
    __tablename__ = 'km_document_audits'
    
    # Audit identification
    audit_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True)
    
    # Target document
    file_id = Column(BigInteger, ForeignKey('km_files.id'), nullable=False)
    
    # Audit type and scope
    audit_type = Column(SQLEnum(AuditType), nullable=False)
    audit_scope = Column(JSON)  # What aspects were audited
    
    # Auditor information
    auditor_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    audit_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    audit_duration = Column(Integer)  # Minutes spent on audit
    
    # Audit findings
    overall_rating = Column(DECIMAL(3, 2))  # 0-5 overall rating
    findings = Column(JSON)  # Detailed findings
    issues_found = Column(Integer, default=0)
    critical_issues = Column(Integer, default=0)
    
    # Content correctness
    content_accuracy = Column(DECIMAL(3, 2))  # 0-5 rating
    factual_errors_found = Column(Integer, default=0)
    outdated_information = Column(Boolean, default=False)
    missing_information = Column(Boolean, default=False)
    
    # Document extraction quality
    extraction_quality = Column(DECIMAL(3, 2))  # 0-5 rating
    text_extraction_errors = Column(Integer, default=0)
    formatting_preserved = Column(Boolean, default=True)
    tables_extracted_correctly = Column(Boolean, default=True)
    images_processed = Column(Boolean, default=True)
    
    # Metadata quality
    metadata_complete = Column(Boolean, default=True)
    tags_appropriate = Column(Boolean, default=True)
    categorization_correct = Column(Boolean, default=True)
    language_detected_correctly = Column(Boolean, default=True)
    
    # Chunk quality assessment
    chunking_quality = Column(DECIMAL(3, 2))  # 0-5 rating
    chunk_boundaries_appropriate = Column(Boolean, default=True)
    context_preserved = Column(Boolean, default=True)
    duplicate_chunks_found = Column(Integer, default=0)
    
    # Vector embedding quality
    embedding_quality = Column(DECIMAL(3, 2))  # 0-5 rating
    semantic_coherence = Column(DECIMAL(3, 2))  # How well embeddings represent content
    search_relevance = Column(DECIMAL(3, 2))  # How well content appears in relevant searches
    
    # Compliance and security
    compliance_issues = Column(JSON)  # Compliance violations found
    sensitive_data_detected = Column(Boolean, default=False)
    pii_found = Column(Boolean, default=False)
    security_classification = Column(String(50))
    
    # Recommendations
    recommendations = Column(JSON)  # Improvement recommendations
    action_items = Column(JSON)  # Specific actions to take
    reaudit_required = Column(Boolean, default=False)
    reaudit_date = Column(DateTime)  # When to conduct next audit
    
    # Audit status
    audit_status = Column(String(50), default='completed')  # in_progress, completed, cancelled
    follow_up_required = Column(Boolean, default=False)
    follow_up_completed = Column(Boolean, default=False)
    
    # Relationships
    file = relationship("KmFile")
    auditor = relationship("UserLocation")
    actions = relationship("KmAdminAction", back_populates="audit")

class KmContentStatus(Base, BaseModel):
    """Content status tracking for KM files and chunks"""
    __tablename__ = 'km_content_status'
    
    # Target content
    content_type = Column(String(50), nullable=False)  # 'file' or 'chunk'
    content_id = Column(BigInteger, nullable=False)  # ID of file or chunk
    
    # Status information
    current_status = Column(String(50), nullable=False)  # active, inactive, pending, review, archived
    previous_status = Column(String(50))
    status_changed_at = Column(DateTime, default=datetime.utcnow)
    status_changed_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    
    # Status reason and notes
    status_reason = Column(Text)
    admin_notes = Column(Text)
    
    # Visibility controls
    is_visible = Column(Boolean, default=True)
    is_searchable = Column(Boolean, default=True)
    is_downloadable = Column(Boolean, default=True)
    
    # Access restrictions
    restricted_access = Column(Boolean, default=False)
    access_reason = Column(Text)
    access_granted_to = Column(JSON)  # User IDs or roles with special access
    
    # Quality flags
    quality_verified = Column(Boolean, default=False)
    needs_update = Column(Boolean, default=False)
    flagged_for_review = Column(Boolean, default=False)
    
    # Expiration and lifecycle
    expires_at = Column(DateTime)
    archive_at = Column(DateTime)
    delete_at = Column(DateTime)
    
    # Relationships
    status_changed_by = relationship("UserLocation")
    
    def __repr__(self):
        return f"<KmContentStatus {self.content_type}:{self.content_id} - {self.current_status}>"

class KmConfiguration(Base, BaseModel):
    """System configuration for Knowledge Management"""
    __tablename__ = 'km_configurations'
    
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))  # Null for global config
    
    # General settings
    max_file_size_mb = Column(Integer, default=100)
    allowed_file_types = Column(JSON)  # Array of allowed file extensions
    default_chunking_strategy = Column(String(100), default='recursive')
    default_chunk_size = Column(Integer, default=1000)
    default_chunk_overlap = Column(Integer, default=200)
    
    # Embedding settings
    embedding_model = Column(String(100), default='text-embedding-ada-002')
    embedding_dimensions = Column(Integer, default=1536)
    similarity_threshold = Column(DECIMAL(3, 2), default=0.7)
    
    # Search settings
    default_search_type = Column(SQLEnum(SearchType), default=SearchType.HYBRID)
    max_search_results = Column(Integer, default=50)
    enable_search_caching = Column(Boolean, default=True)
    cache_ttl_minutes = Column(Integer, default=60)
    
    # Content management
    enable_auto_tagging = Column(Boolean, default=True)
    enable_duplicate_detection = Column(Boolean, default=True)
    content_moderation_enabled = Column(Boolean, default=False)
    
    # Storage settings
    s3_bucket_permanent = Column(String(255))
    s3_bucket_temporary = Column(String(255))
    s3_region = Column(String(50), default='us-east-1')
    storage_class = Column(String(50), default='STANDARD')
    
    # Processing settings
    batch_processing_enabled = Column(Boolean, default=True)
    max_concurrent_processes = Column(Integer, default=5)
    processing_timeout_minutes = Column(Integer, default=60)
    
    # Security settings
    encryption_enabled = Column(Boolean, default=True)
    virus_scanning_enabled = Column(Boolean, default=True)
    content_filtering_enabled = Column(Boolean, default=False)
    
    # Compliance settings
    audit_logging_enabled = Column(Boolean, default=True)
    retention_policy_days = Column(Integer, default=2555)  # 7 years default
    gdpr_compliance_mode = Column(Boolean, default=False)
    
    # Cost management
    monthly_budget_limit = Column(DECIMAL(10, 2))
    cost_alerts_enabled = Column(Boolean, default=True)
    cost_optimization_enabled = Column(Boolean, default=True)
    
    # Custom settings
    custom_settings = Column(JSON)  # Organization-specific settings
    
    # Relationships
    organization = relationship("Organization")

class KmIndexing(Base, BaseModel):
    """Vector indexing management and optimization"""
    __tablename__ = 'km_indexing'
    
    # Index identification
    index_name = Column(String(100), nullable=False)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))
    
    # Index configuration
    vector_dimensions = Column(Integer, default=1536)
    index_type = Column(String(50), default='ivfflat')  # ivfflat, hnsw, etc.
    distance_metric = Column(String(50), default='cosine')  # cosine, l2, inner_product
    
    # Index parameters
    lists = Column(Integer)  # For IVFFlat
    probes = Column(Integer)  # For IVFFlat
    m = Column(Integer)      # For HNSW
    ef_construction = Column(Integer)  # For HNSW
    ef_search = Column(Integer)        # For HNSW
    
    # Index status
    status = Column(SQLEnum(IndexingStatus), default=IndexingStatus.PENDING)
    total_vectors = Column(BigInteger, default=0)
    indexed_vectors = Column(BigInteger, default=0)
    
    # Performance metrics
    build_started = Column(DateTime)
    build_completed = Column(DateTime)
    build_duration = Column(Integer)  # Seconds
    index_size_mb = Column(BigInteger)
    
    # Query performance
    average_query_time = Column(DECIMAL(8, 3))  # Milliseconds
    queries_per_second = Column(DECIMAL(8, 2))
    
    # Maintenance
    last_rebuilt = Column(DateTime)
    rebuild_frequency_days = Column(Integer, default=30)
    needs_rebuild = Column(Boolean, default=False)
    
    # Statistics
    total_queries = Column(BigInteger, default=0)
    cache_hit_ratio = Column(DECIMAL(5, 2))
    
    # Configuration JSON for complex parameters
    index_config = Column(JSON)
    
    # Relationships
    organization = relationship("Organization")
    
    # Table args for proper indexing
    __table_args__ = (
        Index('idx_km_indexing_org_status', 'organization_id', 'status'),
        {'extend_existing': True}
    )

class KmRecommendation(Base, BaseModel):
    """AI-powered content recommendations"""
    __tablename__ = 'km_recommendations'
    
    # Recommendation context
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))
    
    # Recommendation type
    recommendation_type = Column(String(50))  # similar_content, trending, personalized
    context = Column(JSON)  # Context that triggered the recommendation
    
    # Recommended content
    recommended_chunk_id = Column(BigInteger, ForeignKey('km_chunks.id'))
    recommended_file_id = Column(BigInteger, ForeignKey('km_files.id'))
    
    # Scoring
    relevance_score = Column(DECIMAL(5, 4))
    confidence_score = Column(DECIMAL(3, 2))
    freshness_score = Column(DECIMAL(3, 2))
    
    # User interaction
    shown_to_user = Column(Boolean, default=False)
    clicked_by_user = Column(Boolean, default=False)
    user_rating = Column(Integer)  # 1-5 stars
    
    # Expiration
    expires_on = Column(DateTime)
    
    # Relationships
    user_location = relationship("UserLocation")
    organization = relationship("Organization")
    recommended_chunk = relationship("KmChunk")
    recommended_file = relationship("KmFile")