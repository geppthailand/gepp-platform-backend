"""
Expert agents and AI configuration for chat system
Manages AI agents, their knowledge access, and platform-specific capabilities
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON, Enum as SQLEnum, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import DECIMAL
import enum
import uuid
from datetime import datetime
from ..base import Base, BaseModel

class Platform(enum.Enum):
    """GEPP Platform types"""
    GEPP_360 = 'GEPP_360'           # Comprehensive waste management platform
    GEPP_BUSINESS = 'GEPP_BUSINESS' # Business management and analytics
    GEPP_EPR = 'GEPP_EPR'          # Extended Producer Responsibility

class ExpertType(enum.Enum):
    """Types of expert agents"""
    GENERAL = 'general'             # General purpose assistant
    TECHNICAL = 'technical'         # Technical waste management expert
    COMPLIANCE = 'compliance'       # Regulatory and compliance expert
    BUSINESS = 'business'          # Business strategy and operations
    EPR = 'epr'                    # EPR compliance specialist
    SUSTAINABILITY = 'sustainability' # Sustainability and GRI expert
    FINANCIAL = 'financial'        # Financial and cost analysis
    LOGISTICS = 'logistics'        # Logistics and transportation
    QUALITY = 'quality'           # Quality assurance and control
    CUSTOMER_SERVICE = 'customer_service' # Customer support
    DATA_ANALYST = 'data_analyst'  # Data analysis and insights
    PROCUREMENT = 'procurement'    # Procurement and vendor management

class ExpertStatus(enum.Enum):
    """Expert agent status"""
    ACTIVE = 'active'              # Currently active and available
    INACTIVE = 'inactive'          # Temporarily disabled
    TRAINING = 'training'          # Being trained or updated
    MAINTENANCE = 'maintenance'    # Under maintenance
    DEPRECATED = 'deprecated'      # Deprecated, being phased out

class AgentCapability(enum.Enum):
    """Agent capabilities and features"""
    TEXT_GENERATION = 'text_generation'
    DOCUMENT_ANALYSIS = 'document_analysis'
    DATA_VISUALIZATION = 'data_visualization'
    CALCULATION = 'calculation'
    MEETING_SCHEDULING = 'meeting_scheduling'
    WORKFLOW_AUTOMATION = 'workflow_automation'
    MULTI_LANGUAGE = 'multi_language'
    VOICE_INTERACTION = 'voice_interaction'
    IMAGE_ANALYSIS = 'image_analysis'
    REAL_TIME_DATA = 'real_time_data'

class Expert(Base, BaseModel):
    """AI Expert agents with specialized knowledge and capabilities"""
    __tablename__ = 'experts'
    
    # Expert identification
    expert_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255))  # User-friendly display name
    description = Column(Text)
    
    # Expert classification
    expert_type = Column(SQLEnum(ExpertType), nullable=False)
    platforms = Column(JSON)  # Array of platforms this expert serves
    specializations = Column(JSON)  # Specific areas of expertise
    
    # AI Configuration
    ai_model = Column(String(100), default='gpt-4')  # AI model to use
    model_version = Column(String(50))
    temperature = Column(DECIMAL(3, 2), default=0.7)  # Response creativity
    max_tokens = Column(Integer, default=2000)
    top_p = Column(DECIMAL(3, 2), default=1.0)
    frequency_penalty = Column(DECIMAL(3, 2), default=0.0)
    presence_penalty = Column(DECIMAL(3, 2), default=0.0)
    
    # Capabilities
    capabilities = Column(JSON)  # Array of AgentCapability values
    supported_languages = Column(JSON, default=['en'])  # Language codes
    
    # Personality and behavior
    personality_traits = Column(JSON)  # Personality characteristics
    communication_style = Column(String(100))  # formal, casual, technical, friendly
    response_tone = Column(String(100))  # professional, helpful, concise, detailed
    
    # System prompts and instructions
    system_prompt = Column(Text, nullable=False)  # Core system instructions
    context_instructions = Column(Text)  # Additional context handling instructions
    safety_guidelines = Column(Text)  # Safety and compliance guidelines
    
    # Knowledge access configuration
    knowledge_scope = Column(String(50))  # global, organization, restricted
    default_knowledge_filter = Column(JSON)  # Default KM filters
    
    # Performance settings
    response_time_limit = Column(Integer, default=30)  # Seconds
    context_window_size = Column(Integer, default=4000)  # Token context window
    memory_enabled = Column(Boolean, default=True)  # Remember conversation context
    learning_enabled = Column(Boolean, default=False)  # Learn from interactions
    
    # Availability and limitations
    status = Column(SQLEnum(ExpertStatus), default=ExpertStatus.ACTIVE)
    max_concurrent_chats = Column(Integer, default=100)
    daily_usage_limit = Column(Integer)  # Max daily interactions
    
    # Cost management
    cost_per_request = Column(DECIMAL(8, 4))  # Estimated cost per request
    monthly_budget_limit = Column(DECIMAL(10, 2))
    current_monthly_cost = Column(DECIMAL(10, 2), default=0)
    
    # Usage tracking
    total_conversations = Column(BigInteger, default=0)
    total_messages = Column(BigInteger, default=0)
    average_response_time = Column(DECIMAL(8, 3))  # Seconds
    user_satisfaction_score = Column(DECIMAL(3, 2))  # 0-5 rating
    
    # Versioning and updates
    version = Column(String(20), default='1.0')
    last_updated = Column(DateTime)
    update_notes = Column(Text)
    
    # Administrative
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    is_default = Column(Boolean, default=False)  # Default expert for platform
    is_public = Column(Boolean, default=True)  # Available to all users
    
    # Custom configuration
    custom_config = Column(JSON)  # Additional custom settings
    
    # Relationships
    created_by = relationship("UserLocation")
    knowledge_access = relationship("ExpertKnowledgeAccess", back_populates="expert", cascade="all, delete-orphan")
    prompt_templates = relationship("ExpertPromptTemplate", back_populates="expert", cascade="all, delete-orphan")
    configurations = relationship("ExpertConfiguration", back_populates="expert", cascade="all, delete-orphan")
    
    def is_available_for_platform(self, platform):
        """Check if expert is available for specific platform"""
        if not self.platforms:
            return False
        return platform.value in self.platforms
    
    def can_access_knowledge(self, km_chunk):
        """Check if expert can access specific knowledge chunk"""
        # Check knowledge access rules
        access_rules = self.knowledge_access
        
        for rule in access_rules:
            if rule.matches_chunk(km_chunk):
                return rule.access_granted
        
        # Default based on knowledge scope
        if self.knowledge_scope == 'global':
            return True
        elif self.knowledge_scope == 'organization':
            # Check if chunk is from same organization or GEPP
            return (km_chunk.file.owner_type == 'GEPP' or 
                   km_chunk.file.organization_id in self.get_accessible_organizations())
        else:
            return False
    
    def get_effective_prompt(self, context=None):
        """Get effective system prompt with context"""
        base_prompt = self.system_prompt
        
        if context:
            base_prompt += f"\n\nContext: {context}"
        
        if self.context_instructions:
            base_prompt += f"\n\nInstructions: {self.context_instructions}"
        
        return base_prompt

class ExpertKnowledgeAccess(Base, BaseModel):
    """Knowledge access permissions for experts"""
    __tablename__ = 'expert_knowledge_access'
    
    expert_id = Column(BigInteger, ForeignKey('experts.id'), nullable=False)
    
    # Access rule identification
    rule_name = Column(String(255), nullable=False)
    priority = Column(Integer, default=0)  # Higher priority rules checked first
    
    # Access control
    access_granted = Column(Boolean, default=True)
    
    # File-level filters
    owner_types = Column(JSON)  # ['GEPP', 'USER'] - which owner types
    organization_ids = Column(JSON)  # Specific organization IDs
    file_categories = Column(JSON)  # File categories to include/exclude
    file_types = Column(JSON)  # File types to include/exclude
    
    # Chunk-level filters
    chunk_categories = Column(JSON)  # Categories from tags
    chunk_tags = Column(JSON)  # Specific tags to match
    content_types = Column(JSON)  # Content types (text, table, etc.)
    
    # Quality filters
    min_quality_score = Column(DECIMAL(3, 2))  # Minimum content quality
    min_information_density = Column(DECIMAL(5, 2))  # Minimum info density
    
    # Content filters
    excluded_keywords = Column(JSON)  # Keywords that exclude content
    required_keywords = Column(JSON)  # Keywords that must be present
    language_codes = Column(JSON)  # Allowed languages
    
    # Time-based filters
    valid_from = Column(DateTime)
    valid_to = Column(DateTime)
    
    # Usage tracking
    times_used = Column(BigInteger, default=0)
    last_used = Column(DateTime)
    
    # Rule metadata
    description = Column(Text)
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Relationships
    expert = relationship("Expert", back_populates="knowledge_access")
    created_by = relationship("UserLocation")
    
    def matches_chunk(self, km_chunk):
        """Check if this access rule matches the given chunk"""
        # Check owner type
        if self.owner_types and km_chunk.file.owner_type not in self.owner_types:
            return False
        
        # Check organization
        if (self.organization_ids and 
            km_chunk.file.organization_id and 
            km_chunk.file.organization_id not in self.organization_ids):
            return False
        
        # Check file category
        if (self.file_categories and 
            km_chunk.file.file_category not in self.file_categories):
            return False
        
        # Check chunk tags
        if self.chunk_tags:
            chunk_tag_names = [tag.tag_name for tag in km_chunk.tags]
            if not any(tag in chunk_tag_names for tag in self.chunk_tags):
                return False
        
        # Check quality score
        if (self.min_quality_score and 
            km_chunk.quality_score and 
            km_chunk.quality_score < self.min_quality_score):
            return False
        
        # Check time validity
        now = datetime.utcnow()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_to and now > self.valid_to:
            return False
        
        return True

class ExpertPromptTemplate(Base, BaseModel):
    """Prompt templates for different expert scenarios"""
    __tablename__ = 'expert_prompt_templates'
    
    expert_id = Column(BigInteger, ForeignKey('experts.id'), nullable=False)
    
    # Template identification
    template_name = Column(String(255), nullable=False)
    template_type = Column(String(100))  # greeting, analysis, recommendation, summary
    
    # Template content
    prompt_template = Column(Text, nullable=False)
    variables = Column(JSON)  # Template variables and their descriptions
    
    # Usage conditions
    trigger_conditions = Column(JSON)  # When to use this template
    platforms = Column(JSON)  # Platforms this template applies to
    
    # Template metadata
    description = Column(Text)
    examples = Column(JSON)  # Example uses of this template
    
    # Performance tracking
    usage_count = Column(BigInteger, default=0)
    success_rate = Column(DECIMAL(5, 2))  # Success rate when used
    average_rating = Column(DECIMAL(3, 2))  # User rating when used
    
    # Version control
    version = Column(String(20), default='1.0')
    is_active = Column(Boolean, default=True)
    
    # Relationships
    expert = relationship("Expert", back_populates="prompt_templates")

class ExpertConfiguration(Base, BaseModel):
    """Platform-specific expert configurations"""
    __tablename__ = 'expert_configurations'
    
    expert_id = Column(BigInteger, ForeignKey('experts.id'), nullable=False)
    
    # Configuration scope
    platform = Column(SQLEnum(Platform), nullable=False)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))  # Org-specific config
    
    # Platform-specific settings
    config_name = Column(String(255), nullable=False)
    config_values = Column(JSON, nullable=False)  # Key-value configuration
    
    # Overrides for base expert settings
    model_overrides = Column(JSON)  # Override AI model settings
    prompt_overrides = Column(JSON)  # Override prompt settings
    capability_overrides = Column(JSON)  # Override capabilities
    
    # Platform-specific features
    enabled_features = Column(JSON)  # Features enabled for this platform
    disabled_features = Column(JSON)  # Features disabled for this platform
    
    # UI/UX customization
    display_config = Column(JSON)  # How expert appears in UI
    interaction_config = Column(JSON)  # How user interacts with expert
    
    # Integration settings
    api_endpoints = Column(JSON)  # Platform-specific API endpoints
    webhook_urls = Column(JSON)  # Webhook configurations
    
    # Performance settings
    response_cache_ttl = Column(Integer)  # Cache TTL in seconds
    rate_limiting = Column(JSON)  # Rate limiting configuration
    
    # Priority and scheduling
    priority = Column(Integer, default=0)  # Config priority
    valid_from = Column(DateTime)
    valid_to = Column(DateTime)
    
    # Metadata
    description = Column(Text)
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Relationships
    expert = relationship("Expert", back_populates="configurations")
    organization = relationship("Organization")
    created_by = relationship("UserLocation")

class ExpertAnalytics(Base, BaseModel):
    """Analytics and performance metrics for experts"""
    __tablename__ = 'expert_analytics'
    
    expert_id = Column(BigInteger, ForeignKey('experts.id'), nullable=False)
    
    # Analytics period
    analysis_date = Column(DateTime, nullable=False)
    period_type = Column(String(50))  # daily, weekly, monthly
    period_start = Column(DateTime)
    period_end = Column(DateTime)
    
    # Usage metrics
    total_conversations = Column(Integer, default=0)
    total_messages = Column(Integer, default=0)
    unique_users = Column(Integer, default=0)
    
    # Performance metrics
    average_response_time = Column(DECIMAL(8, 3))  # Seconds
    success_rate = Column(DECIMAL(5, 2))  # % of successful interactions
    user_satisfaction = Column(DECIMAL(3, 2))  # Average user rating
    
    # Platform breakdown
    usage_by_platform = Column(JSON)  # Usage stats by platform
    conversations_by_platform = Column(JSON)
    
    # Cost analysis
    total_cost = Column(DECIMAL(10, 4))
    cost_per_message = Column(DECIMAL(8, 4))
    cost_per_conversation = Column(DECIMAL(8, 4))
    
    # Knowledge usage
    knowledge_queries = Column(Integer, default=0)
    knowledge_hit_rate = Column(DECIMAL(5, 2))  # % of queries that found relevant knowledge
    top_knowledge_topics = Column(JSON)
    
    # User interaction patterns
    peak_usage_hours = Column(JSON)
    common_query_types = Column(JSON)
    conversation_lengths = Column(JSON)  # Distribution of conversation lengths
    
    # Issues and feedback
    error_count = Column(Integer, default=0)
    timeout_count = Column(Integer, default=0)
    negative_feedback_count = Column(Integer, default=0)
    
    # Improvement opportunities
    optimization_suggestions = Column(JSON)
    performance_alerts = Column(JSON)
    
    # Relationships
    expert = relationship("Expert")

class ExpertTraining(Base, BaseModel):
    """Expert training sessions and updates"""
    __tablename__ = 'expert_training'
    
    expert_id = Column(BigInteger, ForeignKey('experts.id'), nullable=False)
    
    # Training session details
    training_type = Column(String(100))  # fine_tuning, prompt_optimization, knowledge_update
    training_description = Column(Text)
    
    # Training data
    training_dataset = Column(JSON)  # Training data configuration
    training_parameters = Column(JSON)  # Training hyperparameters
    
    # Training process
    status = Column(String(50), default='pending')  # pending, running, completed, failed
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    # Results
    performance_before = Column(JSON)  # Performance metrics before training
    performance_after = Column(JSON)  # Performance metrics after training
    improvement_metrics = Column(JSON)  # Improvement measurements
    
    # Deployment
    deployed_to_production = Column(Boolean, default=False)
    deployment_date = Column(DateTime)
    rollback_available = Column(Boolean, default=True)
    
    # Cost tracking
    training_cost = Column(DECIMAL(10, 4))
    compute_hours = Column(DECIMAL(8, 2))
    
    # Metadata
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    notes = Column(Text)
    
    # Relationships
    expert = relationship("Expert")
    created_by = relationship("UserLocation")