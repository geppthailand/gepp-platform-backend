"""
Knowledge Management core models for files and chunks
Document storage, processing, and vector-based semantic search
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON, Enum as SQLEnum, Integer
from sqlalchemy.types import DECIMAL
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
import enum
import uuid
from ..base import Base, BaseModel

class OwnerType(enum.Enum):
    """Document ownership types"""
    GEPP = 'GEPP'    # Internal GEPP documents - shared across organizations
    USER = 'USER'    # User/organization-specific documents

class FileType(enum.Enum):
    """File type classifications"""
    PDF = 'pdf'
    DOCX = 'docx'
    DOC = 'doc'
    TXT = 'txt'
    MD = 'markdown'
    HTML = 'html'
    XLSX = 'xlsx'
    XLS = 'xls'
    CSV = 'csv'
    PPT = 'ppt'
    PPTX = 'pptx'
    IMAGE = 'image'
    VIDEO = 'video'
    AUDIO = 'audio'
    OTHER = 'other'

class FileCategory(enum.Enum):
    """File content categories"""
    POLICY = 'policy'                    # Company policies and procedures
    TECHNICAL = 'technical'              # Technical documentation
    TRAINING = 'training'                # Training materials
    COMPLIANCE = 'compliance'            # Compliance and regulatory docs
    OPERATIONAL = 'operational'          # Operational procedures
    KNOWLEDGE_BASE = 'knowledge_base'    # General knowledge articles
    FAQ = 'faq'                         # Frequently asked questions
    MANUAL = 'manual'                   # User manuals and guides
    REPORT = 'report'                   # Reports and analytics
    TEMPLATE = 'template'               # Document templates
    REFERENCE = 'reference'             # Reference materials
    OTHER = 'other'

class ProcessingStatus(enum.Enum):
    """File processing status"""
    UPLOADED = 'uploaded'               # File uploaded to S3
    PROCESSING = 'processing'           # Being processed into chunks
    COMPLETED = 'completed'             # Successfully processed
    FAILED = 'failed'                   # Processing failed
    INDEXED = 'indexed'                 # Vector indexed and searchable
    ARCHIVED = 'archived'               # Archived and not searchable

class KmFile(Base, BaseModel):
    """Knowledge Management files - source documents"""
    __tablename__ = 'km_files'
    
    # File identification
    file_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    original_filename = Column(String(500), nullable=False)
    display_name = Column(String(500))  # User-friendly display name
    
    # Ownership and access
    owner_type = Column(SQLEnum(OwnerType), nullable=False)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))  # Null for GEPP docs
    uploaded_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    
    # File details
    file_type = Column(SQLEnum(FileType), nullable=False)
    file_category = Column(SQLEnum(FileCategory), nullable=False)
    file_size = Column(BigInteger)  # Size in bytes
    mime_type = Column(String(255))
    
    # Storage
    s3_bucket = Column(String(255), nullable=False)
    s3_key = Column(String(1000), nullable=False)  # S3 object key
    s3_url = Column(Text, nullable=False)  # Full S3 URL
    s3_version_id = Column(String(255))  # S3 version ID
    
    # Content metadata
    title = Column(String(500))
    description = Column(Text)
    author = Column(String(255))
    language = Column(String(10), default='en')  # ISO language code
    
    # Processing
    processing_status = Column(SQLEnum(ProcessingStatus), default=ProcessingStatus.UPLOADED)
    processing_started = Column(DateTime)
    processing_completed = Column(DateTime)
    processing_error = Column(Text)
    
    # Content analysis
    total_pages = Column(Integer)
    total_words = Column(Integer)
    total_characters = Column(Integer)
    content_hash = Column(String(64))  # SHA-256 hash of content
    
    # Chunking information
    total_chunks = Column(Integer, default=0)
    chunk_strategy = Column(String(100))  # chunking strategy used
    chunk_size = Column(Integer)  # average chunk size
    chunk_overlap = Column(Integer)  # overlap between chunks
    
    # Usage tracking
    view_count = Column(BigInteger, default=0)
    download_count = Column(BigInteger, default=0)
    search_count = Column(BigInteger, default=0)  # How often chunks are returned in search
    last_accessed = Column(DateTime)
    
    # Versioning
    version = Column(String(20), default='1.0')
    parent_file_id = Column(BigInteger, ForeignKey('km_files.id'))  # For file versions
    is_latest_version = Column(Boolean, default=True)
    
    # Expiration and lifecycle
    expires_on = Column(DateTime)
    is_archived = Column(Boolean, default=False)
    archived_date = Column(DateTime)
    archived_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Access control
    is_public = Column(Boolean, default=False)  # Public within organization
    requires_approval = Column(Boolean, default=False)
    approved_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    approved_date = Column(DateTime)
    
    # Custom metadata
    custom_metadata = Column(JSON)  # Additional metadata fields
    
    # Relationships
    organization = relationship("Organization")
    uploaded_by = relationship("UserLocation", foreign_keys=[uploaded_by_id])
    approved_by = relationship("UserLocation", foreign_keys=[approved_by_id])
    archived_by = relationship("UserLocation", foreign_keys=[archived_by_id])
    parent_file = relationship("KmFile", remote_side="KmFile.id")
    
    # Chunks and tags
    chunks = relationship("KmChunk", back_populates="file", cascade="all, delete-orphan")
    tags = relationship("KmFileTag", back_populates="file", cascade="all, delete-orphan")
    
    def get_accessible_organizations(self):
        """Get list of organizations that can access this file"""
        if self.owner_type == OwnerType.GEPP:
            # GEPP documents are accessible to all organizations
            return 'all'
        else:
            # USER documents are only accessible to their organization
            return [self.organization_id] if self.organization_id else []
    
    def is_accessible_by_user(self, user_location_id):
        """Check if file is accessible by specific user"""
        from sqlalchemy.orm import sessionmaker
        
        user_location = sessionmaker.query(UserLocation).get(user_location_id)
        if not user_location:
            return False
        
        # GEPP documents are accessible to all users
        if self.owner_type == OwnerType.GEPP:
            return True
        
        # USER documents are only accessible within same organization
        return user_location.organization_id == self.organization_id

class KmChunk(Base, BaseModel):
    """Knowledge Management chunks - processed text segments with vector embeddings"""
    __tablename__ = 'km_chunks'
    
    # Chunk identification
    chunk_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    file_id = Column(BigInteger, ForeignKey('km_files.id'), nullable=False)
    chunk_index = Column(Integer, nullable=False)  # Sequential index within file
    
    # Content
    content = Column(Text, nullable=False)  # The actual text content
    content_type = Column(String(50), default='text')  # text, table, image_caption, etc.
    
    # Vector embedding for semantic search
    embedding = Column(Vector(1536))  # OpenAI ada-002 embedding dimension
    embedding_model = Column(String(100), default='text-embedding-ada-002')
    embedding_created = Column(DateTime)
    
    # Position and context
    page_number = Column(Integer)
    paragraph_index = Column(Integer)
    section_title = Column(String(500))
    subsection_title = Column(String(500))
    
    # Content metadata
    word_count = Column(Integer)
    character_count = Column(Integer)
    language = Column(String(10))  # ISO language code
    
    # Chunking details
    start_char = Column(Integer)  # Starting character position in source
    end_char = Column(Integer)    # Ending character position in source
    overlap_previous = Column(Integer)  # Characters overlapping with previous chunk
    overlap_next = Column(Integer)      # Characters overlapping with next chunk
    
    # Content analysis
    sentiment_score = Column(DECIMAL(3, 2))  # -1.0 to 1.0
    readability_score = Column(DECIMAL(5, 2))  # Flesch-Kincaid or similar
    key_phrases = Column(JSON)  # Extracted key phrases
    entities = Column(JSON)     # Named entities (people, places, organizations)
    topics = Column(JSON)       # Topic classifications
    
    # Usage tracking
    search_count = Column(BigInteger, default=0)  # How often returned in search
    relevance_score = Column(DECIMAL(5, 4))  # Average relevance in searches
    last_searched = Column(DateTime)
    
    # Quality metrics
    quality_score = Column(DECIMAL(3, 2))  # 0.0 to 1.0 quality assessment
    information_density = Column(DECIMAL(5, 2))  # Information per word
    uniqueness_score = Column(DECIMAL(3, 2))  # How unique vs other chunks
    
    # Processing metadata
    processing_version = Column(String(20))  # Version of processing pipeline
    extracted_date = Column(DateTime)
    
    # Relationships
    file = relationship("KmFile", back_populates="chunks")
    tags = relationship("KmChunkTag", back_populates="chunk", cascade="all, delete-orphan")
    
    # Indexes will be created in migration for vector similarity search
    __table_args__ = (
        # Regular indexes
        {'extend_existing': True}
    )
    
    def calculate_similarity(self, query_embedding):
        """Calculate cosine similarity with query embedding"""
        # This would typically be done in the database query
        # using pgvector's similarity operators
        pass
    
    def get_context_window(self, window_size=2):
        """Get surrounding chunks for context"""
        # Return chunks before and after this one for context
        return KmChunk.query.filter(
            KmChunk.file_id == self.file_id,
            KmChunk.chunk_index.between(
                max(0, self.chunk_index - window_size),
                self.chunk_index + window_size
            )
        ).order_by(KmChunk.chunk_index).all()

class KmFileTag(Base, BaseModel):
    """Tags for KM files"""
    __tablename__ = 'km_file_tags'
    
    file_id = Column(BigInteger, ForeignKey('km_files.id'), nullable=False)
    
    # Tag details
    tag_name = Column(String(100), nullable=False)
    tag_category = Column(String(50))  # category, purpose, department, etc.
    tag_value = Column(String(255))  # optional value for the tag
    
    # Tag metadata
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    is_system_tag = Column(Boolean, default=False)  # Auto-generated vs user-added
    confidence_score = Column(DECIMAL(3, 2))  # For AI-generated tags
    
    # Relationships
    file = relationship("KmFile", back_populates="tags")
    created_by = relationship("UserLocation")
    
    __table_args__ = (
        # Unique constraint to prevent duplicate tags per file
        {'extend_existing': True}
    )

class KmChunkTag(Base, BaseModel):
    """Tags for KM chunks"""
    __tablename__ = 'km_chunk_tags'
    
    chunk_id = Column(BigInteger, ForeignKey('km_chunks.id'), nullable=False)
    
    # Tag details
    tag_name = Column(String(100), nullable=False)
    tag_category = Column(String(50))  # topic, entity, intent, etc.
    tag_value = Column(String(255))
    
    # Tag metadata
    confidence_score = Column(DECIMAL(3, 2))  # For AI-generated tags
    is_system_tag = Column(Boolean, default=True)  # Most chunk tags are auto-generated
    
    # Source of tag
    extraction_method = Column(String(50))  # nlp, keyword, manual, etc.
    
    # Relationships
    chunk = relationship("KmChunk", back_populates="tags")
    
    __table_args__ = (
        # Unique constraint to prevent duplicate tags per chunk
        {'extend_existing': True}
    )