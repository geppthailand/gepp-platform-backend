# Knowledge Management (KM) Module

## Overview
The Knowledge Management module provides comprehensive document management and RAG (Retrieval-Augmented Generation) capabilities using advanced vector search with pgvector. It enables organizations to store, process, and semantically search through documents while maintaining strict access controls and ownership boundaries.

## Core Concepts

### Document Ownership Model
The KM system implements a two-tier ownership structure:

#### GEPP Documents
- **Internal Knowledge Base**: Documents owned by GEPP system
- **Shared Resource**: Accessible across all organizations
- **Standard Answers**: Used to set consistent response standards
- **Best Practices**: Internal procedures and guidelines
- **Universal Access**: All authenticated users can access

#### USER Documents  
- **Organization-Specific**: Documents owned by individual organizations
- **Private Assets**: Only accessible within the owning organization
- **Custom Knowledge**: Organization-specific procedures and documents
- **Restricted Access**: Limited to organization members

### Document Processing Pipeline
```
File Upload → S3 Storage → Text Extraction → Chunking → Vector Embedding → Searchable Index
     ↓              ↓            ↓            ↓             ↓              ↓
 temp_files → km_files → content → km_chunks → vectors → semantic_search
```

### Vector Search Architecture
- **pgvector Integration**: PostgreSQL extension for vector similarity search
- **Embedding Model**: OpenAI text-embedding-ada-002 (1536 dimensions)
- **Search Types**: Semantic, keyword, hybrid, and structured search
- **Similarity Metrics**: Cosine similarity, L2 distance, inner product

## Module Architecture

### 1. Core Models (`files.py`)

#### KmFile - Document Storage
```python
class KmFile(Base, BaseModel):
    # Ownership and access control
    owner_type = Column(SQLEnum(OwnerType))  # GEPP or USER
    organization_id = Column(BigInteger)     # Null for GEPP docs
    
    # S3 storage integration
    s3_bucket = Column(String(255))
    s3_key = Column(String(1000))
    s3_url = Column(Text)
    
    # Content analysis
    total_chunks = Column(Integer)
    processing_status = Column(SQLEnum(ProcessingStatus))
    
    # Usage tracking
    search_count = Column(BigInteger)
    view_count = Column(BigInteger)
```

#### KmChunk - Searchable Content Segments
```python
class KmChunk(Base, BaseModel):
    # Vector embedding for semantic search
    embedding = Column(Vector(1536))  # pgvector type
    
    # Content and context
    content = Column(Text)
    section_title = Column(String(500))
    page_number = Column(Integer)
    
    # Quality metrics
    quality_score = Column(DECIMAL(3, 2))
    information_density = Column(DECIMAL(5, 2))
    uniqueness_score = Column(DECIMAL(3, 2))
```

### 2. Temporary Processing (`temp_processing.py`)

#### Batch Upload Management
```python
class TempFileBatch(Base, BaseModel):
    # Batch processing configuration
    batch_uuid = Column(UUID)
    processing_config = Column(JSON)
    chunk_strategy = Column(String(100))
    
    # Processing metrics
    total_files = Column(Integer)
    total_chunks_created = Column(Integer)
    processing_duration = Column(Integer)
    
    # Cost tracking
    estimated_tokens = Column(BigInteger)
    actual_cost = Column(DECIMAL(10, 4))
```

#### Temporary Processing Workflow
1. **Upload Phase**: Files uploaded to temporary S3 bucket
2. **Processing Phase**: Text extraction and initial analysis
3. **Chunking Phase**: Content segmented into meaningful chunks
4. **Embedding Phase**: Vector embeddings generated
5. **Validation Phase**: Quality checks and validation
6. **Migration Phase**: Move to permanent storage
7. **Cleanup Phase**: Remove temporary files

### 3. Management & Analytics (`management.py`)

#### Search System
```python
class KmSearch(Base, BaseModel):
    # Query and embedding
    query_text = Column(Text)
    query_embedding = Column(Vector(1536))
    search_type = Column(SQLEnum(SearchType))
    
    # Performance metrics
    execution_time = Column(DECIMAL(8, 3))
    total_results = Column(Integer)
    
    # User interaction tracking
    clicked_results = Column(JSON)
    user_satisfaction = Column(Integer)
```

#### Analytics and Insights
- **Usage Analytics**: Search patterns, popular content, user engagement
- **Performance Metrics**: Response times, success rates, system health
- **Cost Tracking**: Embedding costs, storage costs, compute usage
- **Quality Metrics**: Content quality scores, duplicate detection

## Key Features

### 1. Advanced Search Capabilities

#### Semantic Search
```python
# Vector similarity search using pgvector
SELECT 
    c.content,
    c.embedding <-> %s AS distance,
    f.display_name
FROM km_chunks c
JOIN km_files f ON c.file_id = f.id
WHERE c.embedding <-> %s < 0.3  -- Similarity threshold
ORDER BY c.embedding <-> %s
LIMIT 10;
```

#### Hybrid Search
Combines semantic and keyword search for optimal results:
- **Vector Similarity**: Semantic understanding
- **Full-Text Search**: Exact keyword matches
- **Metadata Filters**: Category, type, date filters
- **Relevance Ranking**: Combined scoring algorithm

#### Search Types
- **SEMANTIC**: Pure vector similarity search
- **KEYWORD**: Traditional full-text search
- **HYBRID**: Combines semantic and keyword
- **STRUCTURED**: Filtered by metadata

### 2. Document Processing Pipeline

#### Text Extraction
- **PDF Processing**: Layout-aware text extraction
- **Office Documents**: DOCX, XLSX, PPTX support
- **Plain Text**: TXT, MD, HTML formats
- **Image OCR**: Text extraction from images
- **Table Extraction**: Structured table data

#### Intelligent Chunking
```python
# Recursive chunking strategy
def chunk_document(text, chunk_size=1000, overlap=200):
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end]
        chunks.append({
            'content': chunk,
            'start_char': start,
            'end_char': end,
            'overlap_previous': overlap if start > 0 else 0
        })
        start = end - overlap
    return chunks
```

#### Chunking Strategies
- **Recursive**: Split by sentences, then paragraphs
- **Semantic**: Use NLP to identify semantic boundaries
- **Fixed-Size**: Fixed character/token count
- **Sliding Window**: Overlapping windows for context

### 3. Access Control and Security

#### Multi-Tenant Architecture
```python
def get_accessible_files(user_location_id):
    user = UserLocation.query.get(user_location_id)
    
    # GEPP documents accessible to all
    gepp_files = KmFile.query.filter_by(owner_type=OwnerType.GEPP)
    
    # USER documents only within organization
    user_files = KmFile.query.filter(
        KmFile.owner_type == OwnerType.USER,
        KmFile.organization_id == user.organization_id
    )
    
    return gepp_files.union(user_files)
```

#### Permission Levels
- **Search**: Can search and view results
- **Upload**: Can upload new documents
- **Manage**: Can edit and delete files
- **Admin**: Full system administration

### 4. Quality Assurance

#### Content Quality Metrics
```python
def calculate_content_quality(chunk):
    metrics = {
        'information_density': calculate_info_density(chunk.content),
        'readability_score': calculate_readability(chunk.content),
        'uniqueness_score': calculate_uniqueness(chunk, all_chunks),
        'sentiment_score': analyze_sentiment(chunk.content)
    }
    
    # Weighted average for final quality score
    quality_score = (
        metrics['information_density'] * 0.3 +
        metrics['readability_score'] * 0.2 +
        metrics['uniqueness_score'] * 0.3 +
        abs(metrics['sentiment_score']) * 0.2
    )
    
    return quality_score
```

#### Duplicate Detection
- **Content Hashing**: SHA-256 hashes for exact duplicates
- **Semantic Similarity**: Vector similarity for near-duplicates
- **Fuzzy Matching**: Edit distance algorithms
- **Deduplication**: Automatic removal of duplicates

## Usage Patterns

### 1. Document Upload and Processing
```python
# Create batch for processing
batch = TempFileBatch(
    organization_id=org_id,
    created_by_id=user_id,
    owner_type='USER',
    chunk_strategy='recursive',
    chunk_size=1000,
    chunk_overlap=200
)

# Upload files to batch
for file in uploaded_files:
    temp_file = TempFile(
        batch_id=batch.id,
        original_filename=file.filename,
        temp_s3_key=upload_to_s3(file),
        file_type=detect_file_type(file)
    )

# Process batch asynchronously
process_batch_async(batch.id)
```

### 2. Semantic Search Implementation
```python
def semantic_search(query, organization_id=None, limit=20):
    # Generate query embedding
    query_embedding = generate_embedding(query)
    
    # Build search query
    search_query = db.session.query(KmChunk).join(KmFile)
    
    # Apply access control
    if organization_id:
        search_query = search_query.filter(
            or_(
                KmFile.owner_type == OwnerType.GEPP,
                and_(
                    KmFile.owner_type == OwnerType.USER,
                    KmFile.organization_id == organization_id
                )
            )
        )
    
    # Vector similarity search
    results = search_query.order_by(
        KmChunk.embedding.cosine_distance(query_embedding)
    ).limit(limit).all()
    
    return results
```

### 3. Analytics and Reporting
```python
def generate_usage_analytics(organization_id, period):
    analytics = {
        'total_searches': count_searches(organization_id, period),
        'popular_content': get_popular_content(organization_id, period),
        'user_engagement': calculate_engagement_metrics(organization_id, period),
        'cost_breakdown': calculate_costs(organization_id, period),
        'quality_metrics': assess_content_quality(organization_id)
    }
    
    return analytics
```

## Integration Points

### With Other Modules

#### Transaction Module Integration
```python
# Generate embeddings for transaction-related queries
def enhance_transaction_search(transaction_query):
    # Search KM for related procedures
    related_docs = semantic_search(
        f"waste management {transaction_query} procedures",
        limit=5
    )
    
    # Provide context for transaction processing
    return {
        'transaction_data': transaction_query,
        'related_procedures': related_docs,
        'best_practices': filter_by_category(related_docs, 'best_practice')
    }
```

#### User Module Integration
- **User Permissions**: Integration with user role system
- **Organization Boundaries**: Respect organizational access controls
- **Activity Tracking**: Log user interactions for analytics

#### Rewards Module Integration
```python
# Reward users for knowledge contributions
def process_document_upload_reward(user_id, file_id):
    if file_meets_quality_threshold(file_id):
        award_points(
            user_id=user_id,
            points=calculate_contribution_points(file_id),
            reason="Knowledge base contribution"
        )
```

### External System Integration

#### AI/ML Services
- **OpenAI API**: For embeddings and content analysis
- **AWS Comprehend**: For entity extraction and sentiment
- **Google Cloud AI**: For document processing and OCR

#### Storage Integration
- **AWS S3**: Primary document storage
- **CloudFront**: CDN for fast document delivery
- **Elasticsearch**: Optional full-text search enhancement

## Performance Optimization

### 1. Vector Index Optimization
```sql
-- Create optimal pgvector index
CREATE INDEX idx_km_chunks_embedding_cosine 
ON km_chunks USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);

-- Update index statistics
ANALYZE km_chunks;
```

### 2. Search Performance
- **Index Strategy**: Proper pgvector index configuration
- **Caching**: Redis for frequent search results
- **Connection Pooling**: Optimized database connections
- **Query Optimization**: Efficient SQL queries

### 3. Storage Optimization
- **S3 Intelligent Tiering**: Automatic cost optimization
- **Compression**: Document compression for storage
- **CDN Distribution**: Fast global content delivery
- **Lifecycle Policies**: Automated archival of old documents

## Security and Compliance

### 1. Data Protection
- **Encryption at Rest**: S3 server-side encryption
- **Encryption in Transit**: TLS for all communications
- **Access Logging**: Comprehensive audit trails
- **PII Detection**: Automatic sensitive data detection

### 2. Access Control
- **Role-Based Access**: Integration with user permission system
- **Organization Boundaries**: Strict multi-tenant isolation
- **Document-Level Permissions**: Fine-grained access control
- **Audit Trails**: Complete activity logging

### 3. Compliance Features
- **GDPR Compliance**: Right to be forgotten implementation
- **Data Retention**: Configurable retention policies
- **Export Capabilities**: Data portability features
- **Consent Management**: User consent tracking

## Best Practices

### 1. Document Organization
- **Consistent Categorization**: Use standardized categories and tags
- **Clear Naming**: Descriptive file names and display names
- **Version Control**: Proper versioning for document updates
- **Quality Standards**: Maintain high content quality thresholds

### 2. Search Optimization
- **Query Expansion**: Enhance queries with synonyms and context
- **Result Ranking**: Implement relevance scoring algorithms
- **User Feedback**: Collect and use search satisfaction metrics
- **Continuous Learning**: Improve search based on usage patterns

### 3. Cost Management
- **Embedding Optimization**: Avoid unnecessary re-embeddings
- **Storage Tiering**: Use appropriate S3 storage classes
- **Processing Efficiency**: Optimize batch processing workflows
- **Monitoring**: Track costs and usage patterns

### 4. Maintenance
- **Regular Indexing**: Keep vector indexes optimized
- **Content Cleanup**: Remove outdated or low-quality content
- **Performance Monitoring**: Track system performance metrics
- **Capacity Planning**: Plan for storage and compute growth

## Future Enhancements

### 1. Advanced AI Features
- **Multi-Modal Search**: Support for images, videos, audio
- **Auto-Summarization**: AI-generated document summaries
- **Question Answering**: Direct answer extraction from documents
- **Content Generation**: AI-assisted content creation

### 2. Enhanced User Experience
- **Visual Search**: Search by document screenshots or diagrams
- **Voice Search**: Speech-to-text query interface
- **Recommendation Engine**: Personalized content recommendations
- **Collaborative Features**: Document annotation and commenting

### 3. Integration Expansion
- **Microsoft 365**: Direct integration with Office documents
- **Google Workspace**: Google Docs and Drive integration
- **Slack/Teams**: Chatbot integration for knowledge access
- **API Ecosystem**: Rich APIs for third-party integrations

### 4. Enterprise Features
- **Advanced Analytics**: Machine learning insights
- **Workflow Integration**: Document approval workflows
- **Compliance Automation**: Automated compliance checking
- **Enterprise Search**: Federated search across systems