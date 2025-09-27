"""
Chat conversation models
Manages chat sessions, message history, and user interactions across platforms
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON, Enum as SQLEnum, Integer
from sqlalchemy.types import DECIMAL
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
import uuid
from datetime import datetime
from ..base import Base, BaseModel

class ChatPlatform(enum.Enum):
    """Chat platforms"""
    GEPP_360 = 'GEPP_360'           # Comprehensive waste management platform
    GEPP_BUSINESS = 'GEPP_BUSINESS' # Business management and analytics
    GEPP_EPR = 'GEPP_EPR'          # Extended Producer Responsibility

class ChatStatus(enum.Enum):
    """Chat session status"""
    ACTIVE = 'active'               # Currently active chat
    PAUSED = 'paused'              # Temporarily paused
    COMPLETED = 'completed'        # Successfully completed
    ABANDONED = 'abandoned'        # User left without completion
    ESCALATED = 'escalated'        # Escalated to human agent
    ERROR = 'error'               # Technical error occurred

class MessageType(enum.Enum):
    """Types of messages in chat"""
    TEXT = 'text'                  # Regular text message
    QUICK_REPLY = 'quick_reply'    # Quick reply button response
    CARD = 'card'                  # Rich card with actions
    CAROUSEL = 'carousel'          # Multiple cards carousel
    MEETING_CARD = 'meeting_card'  # Meeting invitation card
    FILE_ATTACHMENT = 'file_attachment' # File upload
    IMAGE = 'image'               # Image message
    AUDIO = 'audio'               # Audio message
    VIDEO = 'video'               # Video message
    LOCATION = 'location'         # Location sharing
    SYSTEM = 'system'             # System message
    ERROR = 'error'               # Error message
    TYPING = 'typing'             # Typing indicator

class MessageRole(enum.Enum):
    """Message sender role"""
    USER = 'user'                 # Human user
    ASSISTANT = 'assistant'       # AI assistant/bot
    EXPERT = 'expert'            # Specific expert agent
    SYSTEM = 'system'            # System message
    MODERATOR = 'moderator'      # Human moderator

class Chat(Base, BaseModel):
    """Main chat conversations between users and AI agents"""
    __tablename__ = 'chats'
    
    # Chat identification
    chat_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    chat_title = Column(String(500))  # User-defined or auto-generated title
    
    # Platform and context
    platform = Column(SQLEnum(ChatPlatform), nullable=False)
    
    # Participants
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)  # Link to organization
    primary_expert_id = Column(BigInteger, ForeignKey('experts.id'))  # Main expert handling chat
    
    # Chat configuration
    expert_ids = Column(JSON)  # Array of expert IDs involved
    language = Column(String(10), default='en')
    timezone = Column(String(50))
    
    # Status and lifecycle
    status = Column(SQLEnum(ChatStatus), default=ChatStatus.ACTIVE)
    started_at = Column(DateTime, nullable=False)
    last_message_at = Column(DateTime)
    ended_at = Column(DateTime)
    
    # Conversation metrics
    total_messages = Column(Integer, default=0)
    user_messages = Column(Integer, default=0)
    assistant_messages = Column(Integer, default=0)
    average_response_time = Column(DECIMAL(8, 3))  # Seconds
    
    # Engagement tracking
    user_satisfaction_rating = Column(Integer)  # 1-5 stars
    user_feedback = Column(Text)
    feedback_date = Column(DateTime)
    
    # Context and state
    conversation_context = Column(JSON)  # Conversation context and memory
    user_intent = Column(String(255))   # Detected user intent
    current_topic = Column(String(255)) # Current conversation topic
    
    # Session information
    session_id = Column(String(255))    # Session ID for tracking
    device_info = Column(JSON)          # Device and browser info
    ip_address = Column(String(45))     # User IP address
    
    # Meeting integration
    meetings_created = Column(Integer, default=0)
    active_meetings = Column(Integer, default=0)
    
    # Cost tracking
    estimated_cost = Column(DECIMAL(10, 4), default=0)  # AI API costs
    total_tokens = Column(BigInteger, default=0)        # Total tokens used
    
    # Escalation and human handover
    escalated_to_human = Column(Boolean, default=False)
    escalation_reason = Column(Text)
    escalation_date = Column(DateTime)
    human_agent_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Analytics and insights
    conversation_summary = Column(Text)  # AI-generated summary
    key_topics = Column(JSON)           # Extracted key topics
    sentiment_analysis = Column(JSON)   # Overall conversation sentiment
    
    # Privacy and compliance
    is_sensitive = Column(Boolean, default=False)  # Contains sensitive information
    anonymized = Column(Boolean, default=False)    # PII has been anonymized
    retention_date = Column(DateTime)              # When to delete this chat
    
    # Custom metadata
    custom_fields = Column(JSON)        # Platform-specific custom fields
    tags = Column(JSON)                # User or system tags
    
    # Relationships
    user_location = relationship("UserLocation", foreign_keys=[user_location_id])
    organization = relationship("Organization")
    primary_expert = relationship("Expert")
    human_agent = relationship("UserLocation", foreign_keys=[human_agent_id])
    
    # Chat history and related data
    chat_history = relationship("ChatHistory", back_populates="chat", cascade="all, delete-orphan")
    chat_context = relationship("ChatContext", back_populates="chat", cascade="all, delete-orphan")
    chat_feedback = relationship("ChatFeedback", back_populates="chat", cascade="all, delete-orphan")
    chat_meetings = relationship("ChatMeeting", back_populates="chat", cascade="all, delete-orphan")
    
    def get_platform_specific_config(self):
        """Get platform-specific configuration"""
        platform_configs = {
            ChatPlatform.GEPP_360: {
                'features': ['waste_tracking', 'analytics', 'compliance'],
                'default_experts': ['technical', 'sustainability'],
                'meeting_types': ['operational_review', 'compliance_check']
            },
            ChatPlatform.GEPP_BUSINESS: {
                'features': ['business_analytics', 'cost_optimization', 'reporting'],
                'default_experts': ['business', 'financial'],
                'meeting_types': ['strategy_session', 'performance_review']
            },
            ChatPlatform.GEPP_EPR: {
                'features': ['epr_compliance', 'regulatory_updates', 'target_tracking'],
                'default_experts': ['epr', 'compliance'],
                'meeting_types': ['compliance_review', 'target_planning']
            }
        }
        return platform_configs.get(self.platform, {})
    
    def update_conversation_metrics(self):
        """Update conversation metrics from chat history"""
        from sqlalchemy import func
        
        # Count messages by role
        message_counts = db.session.query(
            ChatHistory.message_role,
            func.count(ChatHistory.id)
        ).filter_by(chat_id=self.id).group_by(ChatHistory.message_role).all()
        
        for role, count in message_counts:
            if role == MessageRole.USER:
                self.user_messages = count
            elif role in [MessageRole.ASSISTANT, MessageRole.EXPERT]:
                self.assistant_messages = count
        
        self.total_messages = self.user_messages + self.assistant_messages
        
        # Update last message time
        last_message = ChatHistory.query.filter_by(
            chat_id=self.id
        ).order_by(ChatHistory.created_date.desc()).first()
        
        if last_message:
            self.last_message_at = last_message.created_date

class ChatHistory(Base, BaseModel):
    """Individual messages in chat conversations"""
    __tablename__ = 'chat_history'
    
    chat_id = Column(BigInteger, ForeignKey('chats.id'), nullable=False)
    
    # Message identification
    message_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    sequence_number = Column(Integer, nullable=False)  # Message order in conversation
    
    # Message content
    message_type = Column(SQLEnum(MessageType), default=MessageType.TEXT)
    message_role = Column(SQLEnum(MessageRole), nullable=False)
    message_content = Column(JSON, nullable=False)  # Flexible message structure
    
    # Sender information
    expert_id = Column(BigInteger, ForeignKey('experts.id'))  # If sent by expert
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'))  # If sent by human
    
    # Message metadata
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    message_id = Column(String(255))  # External system message ID
    
    # AI processing information
    prompt_used = Column(Text)          # Prompt used to generate response
    model_used = Column(String(100))    # AI model used
    tokens_used = Column(Integer)       # Tokens consumed
    processing_time = Column(DECIMAL(8, 3))  # Response generation time
    confidence_score = Column(DECIMAL(3, 2))  # AI confidence in response
    
    # Content analysis
    intent_detected = Column(String(255))  # Detected user intent
    entities_extracted = Column(JSON)      # Named entities found
    sentiment_score = Column(DECIMAL(3, 2)) # Message sentiment
    language_detected = Column(String(10))  # Detected language
    
    # Knowledge integration
    knowledge_sources = Column(JSON)    # KM chunks used for response
    search_queries = Column(JSON)       # Queries used to find knowledge
    knowledge_confidence = Column(DECIMAL(3, 2))  # Confidence in knowledge used
    
    # Rich message features
    attachments = Column(JSON)          # File attachments
    quick_replies = Column(JSON)        # Quick reply options provided
    cards = Column(JSON)               # Rich cards in message
    actions = Column(JSON)             # Actions available to user
    
    # Message status
    is_edited = Column(Boolean, default=False)
    edit_timestamp = Column(DateTime)
    is_deleted = Column(Boolean, default=False)
    deletion_reason = Column(String(255))
    
    # User interaction
    was_read = Column(Boolean, default=False)
    read_timestamp = Column(DateTime)
    user_reaction = Column(String(50))  # emoji reaction
    
    # Error handling
    has_error = Column(Boolean, default=False)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    
    # Context preservation
    conversation_context = Column(JSON) # Context at time of message
    
    # Relationships
    chat = relationship("Chat", back_populates="chat_history")
    expert = relationship("Expert")
    user_location = relationship("UserLocation")
    
    def get_message_content_text(self):
        """Extract plain text from message content JSON"""
        if isinstance(self.message_content, dict):
            return self.message_content.get('text', '')
        elif isinstance(self.message_content, str):
            return self.message_content
        else:
            return str(self.message_content)
    
    def add_knowledge_source(self, km_chunk, relevance_score):
        """Add knowledge source used in generating response"""
        if not self.knowledge_sources:
            self.knowledge_sources = []
        
        source_info = {
            'chunk_id': km_chunk.id,
            'file_id': km_chunk.file_id,
            'relevance_score': float(relevance_score),
            'content_preview': km_chunk.content[:200] + '...' if len(km_chunk.content) > 200 else km_chunk.content,
            'file_name': km_chunk.file.display_name,
            'section_title': km_chunk.section_title
        }
        
        self.knowledge_sources.append(source_info)

class ChatContext(Base, BaseModel):
    """Conversation context and memory for chats"""
    __tablename__ = 'chat_context'
    
    chat_id = Column(BigInteger, ForeignKey('chats.id'), nullable=False)
    
    # Context identification
    context_key = Column(String(255), nullable=False)  # Key for context item
    context_type = Column(String(100))  # user_info, preferences, history, etc.
    
    # Context data
    context_value = Column(JSON)        # The actual context data
    context_summary = Column(Text)      # Human-readable summary
    
    # Context metadata
    importance = Column(Integer, default=1)  # 1-10 importance score
    last_updated = Column(DateTime)
    expires_at = Column(DateTime)       # When this context expires
    
    # Usage tracking
    times_referenced = Column(Integer, default=0)
    last_referenced = Column(DateTime)
    
    # Context source
    created_from_message_id = Column(BigInteger, ForeignKey('chat_history.id'))
    auto_generated = Column(Boolean, default=True)
    
    # Relationships
    chat = relationship("Chat", back_populates="chat_context")
    created_from_message = relationship("ChatHistory")

class ChatFeedback(Base, BaseModel):
    """User feedback for chat conversations"""
    __tablename__ = 'chat_feedback'
    
    chat_id = Column(BigInteger, ForeignKey('chats.id'), nullable=False)
    message_id = Column(BigInteger, ForeignKey('chat_history.id'))  # Specific message feedback
    
    # Feedback details
    feedback_type = Column(String(100))  # rating, thumbs, detailed, bug_report
    rating = Column(Integer)            # 1-5 star rating
    feedback_text = Column(Text)        # Written feedback
    
    # Feedback categories
    categories = Column(JSON)           # helpful, accurate, fast, polite, etc.
    
    # Specific aspects
    response_quality = Column(Integer)   # 1-5 rating
    response_speed = Column(Integer)     # 1-5 rating
    helpfulness = Column(Integer)        # 1-5 rating
    accuracy = Column(Integer)           # 1-5 rating
    
    # Improvement suggestions
    suggested_improvements = Column(Text)
    missing_features = Column(JSON)
    
    # Feedback metadata
    feedback_date = Column(DateTime, default=datetime.utcnow)
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Follow-up
    requires_follow_up = Column(Boolean, default=False)
    follow_up_completed = Column(Boolean, default=False)
    follow_up_notes = Column(Text)
    
    # Relationships
    chat = relationship("Chat", back_populates="chat_feedback")
    message = relationship("ChatHistory")
    user_location = relationship("UserLocation")

class ChatAnalytics(Base, BaseModel):
    """Analytics data for chat performance"""
    __tablename__ = 'chat_analytics'
    
    # Analytics scope
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))
    platform = Column(SQLEnum(ChatPlatform))
    expert_id = Column(BigInteger, ForeignKey('experts.id'))
    
    # Time period
    analysis_date = Column(DateTime, nullable=False)
    period_type = Column(String(50))    # daily, weekly, monthly
    period_start = Column(DateTime)
    period_end = Column(DateTime)
    
    # Conversation metrics
    total_chats = Column(Integer, default=0)
    completed_chats = Column(Integer, default=0)
    abandoned_chats = Column(Integer, default=0)
    escalated_chats = Column(Integer, default=0)
    
    # Message metrics
    total_messages = Column(Integer, default=0)
    average_messages_per_chat = Column(DECIMAL(8, 2))
    average_response_time = Column(DECIMAL(8, 3))  # Seconds
    
    # User engagement
    unique_users = Column(Integer, default=0)
    returning_users = Column(Integer, default=0)
    user_satisfaction_avg = Column(DECIMAL(3, 2))
    
    # Performance metrics
    success_rate = Column(DECIMAL(5, 2))  # % of chats marked as successful
    resolution_rate = Column(DECIMAL(5, 2))  # % of issues resolved
    first_contact_resolution = Column(DECIMAL(5, 2))  # % resolved in first chat
    
    # Cost metrics
    total_cost = Column(DECIMAL(10, 4))
    cost_per_chat = Column(DECIMAL(8, 4))
    cost_per_message = Column(DECIMAL(8, 4))
    total_tokens = Column(BigInteger, default=0)
    
    # Popular topics and intents
    top_intents = Column(JSON)          # Most common user intents
    top_topics = Column(JSON)           # Most discussed topics
    common_issues = Column(JSON)        # Common problems users face
    
    # Knowledge utilization
    knowledge_usage_rate = Column(DECIMAL(5, 2))  # % of responses using KM
    top_knowledge_sources = Column(JSON)  # Most used KM sources
    knowledge_effectiveness = Column(DECIMAL(5, 2))  # How helpful KM was
    
    # Platform-specific metrics
    platform_specific_metrics = Column(JSON)  # Platform-specific data
    
    # Meeting integration metrics
    meetings_created = Column(Integer, default=0)
    meeting_conversion_rate = Column(DECIMAL(5, 2))  # % of chats leading to meetings
    
    # Relationships
    organization = relationship("Organization")
    expert = relationship("Expert")

class ChatNotification(Base, BaseModel):
    """Notifications related to chat conversations"""
    __tablename__ = 'chat_notifications'
    
    # Notification target
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    chat_id = Column(BigInteger, ForeignKey('chats.id'))
    
    # Notification details
    notification_type = Column(String(100))  # new_message, meeting_invite, feedback_request
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    
    # Delivery channels
    send_email = Column(Boolean, default=False)
    send_sms = Column(Boolean, default=False)
    send_push = Column(Boolean, default=True)
    send_in_app = Column(Boolean, default=True)
    
    # Delivery status
    delivered = Column(Boolean, default=False)
    delivery_attempts = Column(Integer, default=0)
    delivered_at = Column(DateTime)
    
    # User interaction
    read = Column(Boolean, default=False)
    read_at = Column(DateTime)
    clicked = Column(Boolean, default=False)
    clicked_at = Column(DateTime)
    
    # Notification data
    action_url = Column(String(500))    # URL for notification action
    notification_data = Column(JSON)    # Additional notification data
    
    # Scheduling
    scheduled_for = Column(DateTime)    # When to send notification
    expires_at = Column(DateTime)       # When notification expires
    
    # Relationships
    user_location = relationship("UserLocation")
    chat = relationship("Chat")