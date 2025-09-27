"""
Knowledge Management temporary processing models
Handles batch uploads and temporary processing before moving to permanent storage
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON, Enum as SQLEnum, Integer
from sqlalchemy.types import DECIMAL
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
import enum
import uuid
from ..base import Base, BaseModel

class BatchProcessingStatus(enum.Enum):
    """Batch processing status"""
    CREATED = 'created'                 # Batch created, files being uploaded
    UPLOADING = 'uploading'            # Files being uploaded to S3
    UPLOADED = 'uploaded'              # All files uploaded, ready for processing
    PROCESSING = 'processing'          # Files being processed into chunks
    EMBEDDING = 'embedding'            # Creating vector embeddings
    VALIDATING = 'validating'          # Validating processed content
    COMPLETED = 'completed'            # Successfully processed and ready to move
    FAILED = 'failed'                  # Processing failed
    CANCELLED = 'cancelled'            # Batch processing cancelled
    MOVING_TO_PERMANENT = 'moving'     # Moving to permanent storage
    ARCHIVED = 'archived'              # Temporary files archived

class TempFileBatch(Base, BaseModel):
    """Batch upload management for temporary processing"""
    __tablename__ = 'temp_file_batches'
    
    # Batch identification
    batch_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    batch_name = Column(String(255))
    
    # Ownership
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))  # Null for GEPP batches
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    owner_type = Column(String(10), nullable=False)  # GEPP or USER
    
    # Processing configuration
    processing_config = Column(JSON)  # Configuration for processing pipeline
    chunk_strategy = Column(String(100), default='recursive')
    chunk_size = Column(Integer, default=1000)
    chunk_overlap = Column(Integer, default=200)
    embedding_model = Column(String(100), default='text-embedding-ada-002')
    
    # Batch status
    status = Column(SQLEnum(BatchProcessingStatus), default=BatchProcessingStatus.CREATED)
    status_updated = Column(DateTime)
    
    # File counts
    total_files = Column(Integer, default=0)
    processed_files = Column(Integer, default=0)
    failed_files = Column(Integer, default=0)
    
    # Processing metrics
    total_chunks_created = Column(Integer, default=0)
    total_embeddings_created = Column(Integer, default=0)
    processing_started = Column(DateTime)
    processing_completed = Column(DateTime)
    processing_duration = Column(Integer)  # Seconds
    
    # Error tracking
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    
    # Resource usage
    estimated_tokens = Column(BigInteger)  # Estimated tokens for embeddings
    actual_tokens = Column(BigInteger)     # Actual tokens used
    estimated_cost = Column(DECIMAL(10, 4))  # Estimated processing cost
    actual_cost = Column(DECIMAL(10, 4))     # Actual processing cost
    
    # Temporary storage
    temp_s3_bucket = Column(String(255))
    temp_s3_prefix = Column(String(500))  # S3 prefix for this batch
    
    # Cleanup
    cleanup_after = Column(DateTime)  # When to clean up temp files
    is_cleaned_up = Column(Boolean, default=False)
    
    # Priority and scheduling
    priority = Column(Integer, default=5)  # 1-10, higher is more priority
    scheduled_processing = Column(DateTime)  # When to process this batch
    
    # Validation
    validation_rules = Column(JSON)  # Rules for content validation
    validation_passed = Column(Boolean)
    validation_errors = Column(JSON)
    
    # Metadata
    upload_source = Column(String(100))  # web, api, bulk_import, etc.
    custom_metadata = Column(JSON)
    
    # Relationships
    organization = relationship("Organization")
    created_by = relationship("UserLocation")
    temp_files = relationship("TempFile", back_populates="batch", cascade="all, delete-orphan")
    
    def calculate_progress_percentage(self):
        """Calculate processing progress as percentage"""
        if self.total_files == 0:
            return 0
        return (self.processed_files / self.total_files) * 100
    
    def get_estimated_processing_time(self):
        """Estimate remaining processing time based on current progress"""
        if self.processing_started and self.processed_files > 0:
            elapsed = (datetime.utcnow() - self.processing_started).total_seconds()
            rate = self.processed_files / elapsed  # files per second
            remaining_files = self.total_files - self.processed_files
            return remaining_files / rate if rate > 0 else None
        return None

class TempFile(Base, BaseModel):
    """Temporary files during batch processing"""
    __tablename__ = 'temp_files'
    
    # File identification
    file_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    batch_id = Column(BigInteger, ForeignKey('temp_file_batches.id'), nullable=False)
    
    # File details
    original_filename = Column(String(500), nullable=False)
    display_name = Column(String(500))
    file_type = Column(String(20))  # pdf, docx, txt, etc.
    file_size = Column(BigInteger)
    mime_type = Column(String(255))
    
    # Temporary storage
    temp_s3_key = Column(String(1000))  # Temporary S3 location
    temp_s3_url = Column(Text)
    
    # Upload details
    upload_started = Column(DateTime)
    upload_completed = Column(DateTime)
    uploaded_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Processing status
    processing_status = Column(String(50), default='uploaded')
    processing_started = Column(DateTime)
    processing_completed = Column(DateTime)
    processing_error = Column(Text)
    
    # Content analysis (temporary)
    detected_language = Column(String(10))
    detected_encoding = Column(String(50))
    content_preview = Column(Text)  # First 500 characters
    
    # Extraction results
    extracted_text = Column(Text)  # Full extracted text
    total_pages = Column(Integer)
    total_words = Column(Integer)
    total_characters = Column(Integer)
    
    # Chunking results
    total_chunks = Column(Integer, default=0)
    chunk_processing_completed = Column(Boolean, default=False)
    
    # Validation
    validation_passed = Column(Boolean)
    validation_errors = Column(JSON)
    
    # Quality assessment
    content_quality_score = Column(DECIMAL(3, 2))  # 0.0 to 1.0
    extractable_content = Column(Boolean, default=True)
    
    # Metadata
    file_metadata = Column(JSON)  # Additional file-specific metadata
    
    # Move to permanent
    moved_to_permanent = Column(Boolean, default=False)
    permanent_file_id = Column(BigInteger, ForeignKey('km_files.id'))
    moved_date = Column(DateTime)
    
    # Relationships
    batch = relationship("TempFileBatch", back_populates="temp_files")
    uploaded_by = relationship("UserLocation")
    temp_chunks = relationship("TempChunk", back_populates="temp_file", cascade="all, delete-orphan")
    permanent_file = relationship("KmFile")

class TempChunk(Base, BaseModel):
    """Temporary chunks extracted from temporary files"""
    __tablename__ = 'temp_chunks'
    
    # Chunk identification
    chunk_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    temp_file_id = Column(BigInteger, ForeignKey('temp_files.id'), nullable=False)
    batch_id = Column(BigInteger, ForeignKey('temp_file_batches.id'), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    
    # Content
    content = Column(Text, nullable=False)
    content_type = Column(String(50), default='text')
    
    # Position information
    page_number = Column(Integer)
    paragraph_index = Column(Integer)
    start_char = Column(Integer)
    end_char = Column(Integer)
    
    # Content metadata
    word_count = Column(Integer)
    character_count = Column(Integer)
    language = Column(String(10))
    
    # Vector embedding (temporary)
    embedding = Column(Vector(1536))  # Will be moved to permanent chunk
    embedding_model = Column(String(100))
    embedding_created = Column(DateTime)
    embedding_tokens = Column(Integer)  # Tokens used for embedding
    embedding_cost = Column(DECIMAL(8, 6))  # Cost for this embedding
    
    # Processing metadata
    extraction_method = Column(String(50))  # Method used to extract chunk
    chunking_strategy = Column(String(50))  # Strategy used for chunking
    
    # Quality metrics
    quality_score = Column(DECIMAL(3, 2))
    information_density = Column(DECIMAL(5, 2))
    readability_score = Column(DECIMAL(5, 2))
    
    # Preliminary analysis
    detected_topics = Column(JSON)
    key_phrases = Column(JSON)
    entities = Column(JSON)
    sentiment_score = Column(DECIMAL(3, 2))
    
    # Processing status
    processing_completed = Column(Boolean, default=False)
    processing_error = Column(Text)
    
    # Validation
    validation_passed = Column(Boolean, default=True)
    validation_issues = Column(JSON)
    
    # Move to permanent
    moved_to_permanent = Column(Boolean, default=False)
    permanent_chunk_id = Column(BigInteger, ForeignKey('km_chunks.id'))
    moved_date = Column(DateTime)
    
    # Relationships
    temp_file = relationship("TempFile", back_populates="temp_chunks")
    batch = relationship("TempFileBatch")
    permanent_chunk = relationship("KmChunk")
    
    def preview_content(self, max_length=200):
        """Get preview of chunk content"""
        if len(self.content) <= max_length:
            return self.content
        return self.content[:max_length] + "..."
    
    def calculate_embedding_cost(self, cost_per_token=0.0001):
        """Calculate cost for embedding generation"""
        if self.embedding_tokens:
            return float(self.embedding_tokens) * cost_per_token
        return 0.0

class TempProcessingLog(Base, BaseModel):
    """Processing logs for temporary batch operations"""
    __tablename__ = 'temp_processing_logs'
    
    # Log identification
    batch_id = Column(BigInteger, ForeignKey('temp_file_batches.id'))
    temp_file_id = Column(BigInteger, ForeignKey('temp_files.id'))
    
    # Log details
    log_level = Column(String(20))  # DEBUG, INFO, WARNING, ERROR
    message = Column(Text, nullable=False)
    component = Column(String(100))  # uploader, extractor, chunker, embedder
    
    # Context
    processing_step = Column(String(100))
    file_name = Column(String(500))
    
    # Error details
    error_type = Column(String(100))
    error_code = Column(String(50))
    stack_trace = Column(Text)
    
    # Performance metrics
    processing_time_ms = Column(Integer)
    memory_usage_mb = Column(Integer)
    tokens_processed = Column(Integer)
    
    # Additional data
    extra_metadata = Column(JSON)
    
    # Relationships
    batch = relationship("TempFileBatch")
    temp_file = relationship("TempFile")

class TempBatchStatistics(Base, BaseModel):
    """Statistics and metrics for temporary batch processing"""
    __tablename__ = 'temp_batch_statistics'
    
    batch_id = Column(BigInteger, ForeignKey('temp_file_batches.id'), nullable=False)
    
    # Processing metrics
    total_processing_time = Column(Integer)  # Seconds
    average_file_processing_time = Column(DECIMAL(8, 2))
    files_processed_per_minute = Column(DECIMAL(8, 2))
    
    # Content metrics
    total_content_extracted = Column(BigInteger)  # Total characters
    average_file_size = Column(BigInteger)
    total_chunks_created = Column(Integer)
    average_chunks_per_file = Column(DECIMAL(8, 2))
    
    # Embedding metrics
    total_embeddings = Column(Integer)
    total_embedding_tokens = Column(BigInteger)
    total_embedding_cost = Column(DECIMAL(10, 4))
    average_embedding_time = Column(DECIMAL(8, 3))  # Seconds per embedding
    
    # Quality metrics
    average_content_quality = Column(DECIMAL(3, 2))
    files_with_extraction_issues = Column(Integer)
    chunks_with_quality_issues = Column(Integer)
    
    # Error statistics
    total_errors = Column(Integer)
    error_breakdown = Column(JSON)  # Error types and counts
    
    # Resource utilization
    peak_memory_usage = Column(BigInteger)  # Bytes
    peak_cpu_usage = Column(DECIMAL(5, 2))  # Percentage
    network_bandwidth_used = Column(BigInteger)  # Bytes
    
    # Storage statistics
    temp_storage_used = Column(BigInteger)  # Bytes
    final_storage_size = Column(BigInteger)  # Bytes after processing
    compression_ratio = Column(DECIMAL(5, 2))
    
    # Generated timestamp
    statistics_generated = Column(DateTime)
    
    # Relationships
    batch = relationship("TempFileBatch")