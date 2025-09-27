"""
Meeting and collaboration models
Manages AI-powered meetings, multi-expert discussions, and collaborative problem-solving
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Boolean, JSON, Enum as SQLEnum, Integer
from sqlalchemy.types import DECIMAL
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
import uuid
from datetime import datetime
from ..base import Base, BaseModel

class MeetingType(enum.Enum):
    """Types of AI-powered meetings"""
    CONSULTATION = 'consultation'      # One-on-one expert consultation
    MULTI_EXPERT = 'multi_expert'     # Multiple experts discussion
    PROBLEM_SOLVING = 'problem_solving' # Collaborative problem solving
    STRATEGY_SESSION = 'strategy_session' # Strategic planning
    COMPLIANCE_REVIEW = 'compliance_review' # Compliance and regulatory review
    OPERATIONAL_REVIEW = 'operational_review' # Operations review
    PERFORMANCE_ANALYSIS = 'performance_analysis' # Performance analysis
    TRAINING_SESSION = 'training_session' # Educational/training meeting
    BRAINSTORMING = 'brainstorming'   # Creative brainstorming session
    DECISION_SUPPORT = 'decision_support' # Decision-making support

class MeetingStatus(enum.Enum):
    """Meeting lifecycle status"""
    SCHEDULED = 'scheduled'           # Meeting scheduled but not started
    ACTIVE = 'active'                # Meeting currently in progress
    PAUSED = 'paused'               # Temporarily paused
    COMPLETED = 'completed'         # Successfully completed
    CANCELLED = 'cancelled'         # Cancelled before completion
    FAILED = 'failed'              # Technical failure
    ARCHIVED = 'archived'          # Archived for historical reference

class ParticipantRole(enum.Enum):
    """Participant roles in meetings"""
    HOST = 'host'                   # Meeting host (user)
    MODERATOR = 'moderator'         # AI moderator
    EXPERT = 'expert'              # Expert participant
    OBSERVER = 'observer'          # Observer (read-only)
    CONTRIBUTOR = 'contributor'    # Can contribute to discussion
    FACILITATOR = 'facilitator'    # AI facilitator

class SummaryType(enum.Enum):
    """Types of meeting summaries"""
    REAL_TIME = 'real_time'        # Live summary during meeting
    INTERIM = 'interim'            # Interim summary at checkpoints
    FINAL = 'final'               # Final meeting summary
    ACTION_ITEMS = 'action_items'  # Action items summary
    DECISIONS = 'decisions'        # Decisions made summary
    INSIGHTS = 'insights'         # Key insights summary

class ChatMeeting(Base, BaseModel):
    """AI-powered meetings spawned from chat conversations"""
    __tablename__ = 'chat_meetings'
    
    # Meeting identification
    meeting_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    meeting_title = Column(String(500), nullable=False)
    meeting_description = Column(Text)
    
    # Source chat and context
    chat_id = Column(BigInteger, ForeignKey('chats.id'), nullable=False)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)  # Link to organization
    
    # Meeting configuration
    meeting_type = Column(SQLEnum(MeetingType), nullable=False)
    platform = Column(String(50))  # Inherited from parent chat
    
    # Participants
    host_user_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    moderator_expert_id = Column(BigInteger, ForeignKey('experts.id'))  # AI moderator
    participant_expert_ids = Column(JSON)  # Array of expert IDs
    
    # Meeting agenda and objectives
    agenda = Column(JSON)               # Meeting agenda items
    objectives = Column(JSON)           # Meeting objectives
    success_criteria = Column(JSON)     # Success criteria
    
    # Meeting schedule
    scheduled_start = Column(DateTime)
    scheduled_end = Column(DateTime)
    actual_start = Column(DateTime)
    actual_end = Column(DateTime)
    estimated_duration = Column(Integer) # Minutes
    
    # Meeting status and progress
    status = Column(SQLEnum(MeetingStatus), default=MeetingStatus.SCHEDULED)
    current_agenda_item = Column(Integer, default=0)  # Current agenda item index
    progress_percentage = Column(DECIMAL(5, 2), default=0)  # Overall progress
    
    # Meeting context and background
    background_context = Column(JSON)   # Background information
    relevant_documents = Column(JSON)   # Related KM documents
    previous_meetings = Column(JSON)    # Links to previous related meetings
    
    # AI configuration
    meeting_prompt_template = Column(Text)  # Template for meeting moderation
    expert_interaction_rules = Column(JSON)  # Rules for expert interactions
    facilitation_style = Column(String(100))  # collaborative, structured, free-form
    
    # Meeting insights and outcomes
    key_decisions = Column(JSON)        # Decisions made during meeting
    action_items = Column(JSON)         # Action items assigned
    insights_generated = Column(JSON)   # Key insights from discussion
    recommendations = Column(JSON)      # AI-generated recommendations
    
    # Collaboration metrics
    total_participants = Column(Integer, default=0)
    total_messages = Column(Integer, default=0)
    expert_contributions = Column(JSON) # Contributions by each expert
    engagement_score = Column(DECIMAL(5, 2))  # Overall engagement score
    
    # Meeting quality and satisfaction
    meeting_effectiveness = Column(DECIMAL(5, 2))  # 0-5 effectiveness rating
    participant_satisfaction = Column(JSON)  # Satisfaction ratings by participant
    objectives_achieved = Column(JSON)  # Which objectives were achieved
    
    # Cost tracking
    estimated_cost = Column(DECIMAL(10, 4), default=0)  # AI processing costs
    actual_cost = Column(DECIMAL(10, 4), default=0)
    total_tokens = Column(BigInteger, default=0)
    
    # Follow-up and continuation
    follow_up_required = Column(Boolean, default=False)
    follow_up_date = Column(DateTime)
    parent_meeting_id = Column(BigInteger, ForeignKey('chat_meetings.id'))  # For follow-up meetings
    
    # Privacy and access control
    is_confidential = Column(Boolean, default=False)
    access_level = Column(String(50), default='organization')  # organization, team, private
    recording_enabled = Column(Boolean, default=True)
    
    # Custom metadata
    custom_fields = Column(JSON)        # Platform-specific fields
    tags = Column(JSON)                # Meeting tags
    
    # Relationships
    chat = relationship("Chat", back_populates="chat_meetings")
    organization = relationship("Organization")
    host_user = relationship("UserLocation")
    moderator_expert = relationship("Expert")
    parent_meeting = relationship("ChatMeeting", remote_side="ChatMeeting.id")
    
    # Related data
    meeting_history = relationship("ChatMeetingHistory", back_populates="meeting", cascade="all, delete-orphan")
    meeting_participants = relationship("ChatMeetingParticipant", back_populates="meeting", cascade="all, delete-orphan")
    meeting_summaries = relationship("ChatMeetingSummary", back_populates="meeting", cascade="all, delete-orphan")
    meeting_actions = relationship("MeetingAction", back_populates="meeting", cascade="all, delete-orphan")
    meeting_documents = relationship("MeetingDocument", back_populates="meeting", cascade="all, delete-orphan")
    
    def calculate_meeting_effectiveness(self):
        """Calculate meeting effectiveness based on various factors"""
        factors = {
            'objectives_achieved': self.calculate_objectives_achievement(),
            'participant_engagement': self.calculate_engagement_score(),
            'action_items_clarity': self.assess_action_items_quality(),
            'time_efficiency': self.calculate_time_efficiency(),
            'participant_satisfaction': self.get_average_satisfaction()
        }
        
        # Weighted average
        effectiveness = (
            factors['objectives_achieved'] * 0.3 +
            factors['participant_engagement'] * 0.2 +
            factors['action_items_clarity'] * 0.2 +
            factors['time_efficiency'] * 0.15 +
            factors['participant_satisfaction'] * 0.15
        )
        
        self.meeting_effectiveness = effectiveness
        return effectiveness
    
    def get_active_experts(self):
        """Get list of currently active expert participants"""
        return [p for p in self.meeting_participants 
                if p.participant_type == 'expert' and p.is_active]

class ChatMeetingHistory(Base, BaseModel):
    """Conversation history within meetings between experts and users"""
    __tablename__ = 'chat_meeting_history'
    
    meeting_id = Column(BigInteger, ForeignKey('chat_meetings.id'), nullable=False)
    
    # Message identification
    message_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    sequence_number = Column(Integer, nullable=False)  # Message order in meeting
    
    # Message content and structure (JSON format for flexibility)
    message_content = Column(JSON, nullable=False)  # Flexible message structure
    message_type = Column(String(100))  # discussion, decision, action_item, insight
    
    # Sender information
    sender_type = Column(String(50))    # user, expert, moderator, system
    sender_expert_id = Column(BigInteger, ForeignKey('experts.id'))
    sender_user_id = Column(BigInteger, ForeignKey('user_locations.id'))
    sender_name = Column(String(255))   # Display name
    
    # Message context
    agenda_item_id = Column(Integer)    # Which agenda item this relates to
    thread_id = Column(String(255))     # For threaded conversations
    reply_to_message_id = Column(BigInteger, ForeignKey('chat_meeting_history.id'))  # Reply chain
    
    # Content analysis
    sentiment_score = Column(DECIMAL(3, 2))  # Message sentiment
    confidence_level = Column(DECIMAL(3, 2)) # Expert confidence in response
    expertise_relevance = Column(DECIMAL(3, 2)) # How relevant to expert's domain
    
    # AI processing information
    model_used = Column(String(100))    # AI model used for generation
    tokens_used = Column(Integer)       # Tokens consumed
    processing_time = Column(DECIMAL(8, 3))  # Generation time
    prompt_template_used = Column(Text) # Prompt template used
    
    # Knowledge integration
    knowledge_sources = Column(JSON)    # KM sources referenced
    external_references = Column(JSON)  # External sources referenced
    knowledge_confidence = Column(DECIMAL(3, 2))  # Confidence in knowledge used
    
    # Contribution analysis
    contribution_type = Column(String(100))  # insight, solution, question, clarification
    innovation_score = Column(DECIMAL(3, 2)) # How innovative/creative the contribution
    practical_value = Column(DECIMAL(3, 2))  # Practical applicability
    
    # Interaction tracking
    reactions = Column(JSON)            # User reactions (like, helpful, etc.)
    follow_up_questions = Column(JSON)  # Follow-up questions generated
    clarification_needed = Column(Boolean, default=False)
    
    # Meeting flow control
    advances_agenda = Column(Boolean, default=False)  # Moves agenda forward
    creates_action_item = Column(Boolean, default=False)  # Results in action item
    makes_decision = Column(Boolean, default=False)   # Makes or influences decision
    
    # Timestamp and metadata
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    edited = Column(Boolean, default=False)
    edit_timestamp = Column(DateTime)
    
    # Relationships
    meeting = relationship("ChatMeeting", back_populates="meeting_history")
    sender_expert = relationship("Expert")
    sender_user = relationship("UserLocation")
    reply_to_message = relationship("ChatMeetingHistory", remote_side="ChatMeetingHistory.id")

class ChatMeetingParticipant(Base, BaseModel):
    """Participants in chat meetings (experts and users)"""
    __tablename__ = 'chat_meeting_participants'
    
    meeting_id = Column(BigInteger, ForeignKey('chat_meetings.id'), nullable=False)
    
    # Participant identification
    participant_type = Column(String(50))  # expert, user, moderator
    expert_id = Column(BigInteger, ForeignKey('experts.id'))
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'))
    
    # Participation details
    role = Column(SQLEnum(ParticipantRole), nullable=False)
    display_name = Column(String(255))
    avatar_url = Column(String(500))
    
    # Participation status
    invited_at = Column(DateTime)
    joined_at = Column(DateTime)
    left_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    
    # Participation metrics
    total_messages = Column(Integer, default=0)
    total_contribution_time = Column(Integer, default=0)  # Seconds actively contributing
    engagement_score = Column(DECIMAL(5, 2))  # Participation engagement level
    
    # Expert-specific information
    expertise_areas = Column(JSON)      # Areas of expertise for this meeting
    confidence_in_domain = Column(DECIMAL(3, 2))  # Confidence in meeting domain
    previous_experience = Column(JSON)  # Previous experience with similar topics
    
    # Contribution analysis
    insights_contributed = Column(Integer, default=0)
    decisions_influenced = Column(Integer, default=0)
    action_items_created = Column(Integer, default=0)
    questions_answered = Column(Integer, default=0)
    
    # Performance metrics
    response_time_avg = Column(DECIMAL(8, 3))  # Average response time
    message_quality_avg = Column(DECIMAL(3, 2))  # Average message quality score
    helpfulness_rating = Column(DECIMAL(3, 2))  # How helpful participants found them
    
    # Satisfaction and feedback
    meeting_satisfaction = Column(Integer)  # 1-5 satisfaction rating
    would_recommend = Column(Boolean)       # Would recommend this meeting format
    feedback_comment = Column(Text)         # Open feedback
    
    # Permissions and capabilities
    can_moderate = Column(Boolean, default=False)
    can_invite_others = Column(Boolean, default=False)
    can_end_meeting = Column(Boolean, default=False)
    can_access_documents = Column(Boolean, default=True)
    
    # Custom metadata
    custom_attributes = Column(JSON)    # Custom participant attributes
    
    # Relationships
    meeting = relationship("ChatMeeting", back_populates="meeting_participants")
    expert = relationship("Expert")
    user_location = relationship("UserLocation")

class ChatMeetingSummary(Base, BaseModel):
    """Meeting summaries generated at different points in time"""
    __tablename__ = 'chat_meeting_summaries'
    
    meeting_id = Column(BigInteger, ForeignKey('chat_meetings.id'), nullable=False)
    
    # Summary identification
    summary_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True)
    summary_type = Column(SQLEnum(SummaryType), nullable=False)
    
    # Summary content (JSON format for structured data)
    summary_content = Column(JSON, nullable=False)  # Structured summary data
    
    # Summary metadata
    generated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    generated_by_expert_id = Column(BigInteger, ForeignKey('experts.id'))
    
    # Summary scope
    agenda_items_covered = Column(JSON)  # Which agenda items this covers
    time_range_start = Column(DateTime)  # Start of summarized period
    time_range_end = Column(DateTime)    # End of summarized period
    messages_summarized = Column(Integer) # Number of messages included
    
    # Summary quality metrics
    completeness_score = Column(DECIMAL(3, 2))  # How complete the summary is
    accuracy_score = Column(DECIMAL(3, 2))      # How accurate the summary is
    conciseness_score = Column(DECIMAL(3, 2))   # How concise the summary is
    
    # Key elements extracted
    key_decisions = Column(JSON)        # Key decisions identified
    action_items = Column(JSON)         # Action items extracted
    insights = Column(JSON)             # Key insights captured
    concerns_raised = Column(JSON)      # Concerns or issues raised
    next_steps = Column(JSON)           # Next steps identified
    
    # Participant involvement
    participant_contributions = Column(JSON)  # Summary of each participant's contributions
    consensus_areas = Column(JSON)      # Areas where consensus was reached
    disagreement_areas = Column(JSON)   # Areas of disagreement
    
    # AI processing information
    model_used = Column(String(100))    # AI model used for summarization
    tokens_used = Column(Integer)       # Tokens used for generation
    processing_time = Column(DECIMAL(8, 3))  # Time to generate summary
    
    # User feedback on summary
    usefulness_rating = Column(DECIMAL(3, 2))  # How useful users found it
    accuracy_feedback = Column(Text)    # Feedback on accuracy
    missing_elements = Column(JSON)     # What users felt was missing
    
    # Version control
    version = Column(String(20), default='1.0')
    is_final = Column(Boolean, default=False)
    supersedes_summary_id = Column(BigInteger, ForeignKey('chat_meeting_summaries.id'))
    
    # Relationships
    meeting = relationship("ChatMeeting", back_populates="meeting_summaries")
    generated_by_expert = relationship("Expert")
    supersedes_summary = relationship("ChatMeetingSummary", remote_side="ChatMeetingSummary.id")

class MeetingAction(Base, BaseModel):
    """Action items and tasks generated from meetings"""
    __tablename__ = 'meeting_actions'
    
    meeting_id = Column(BigInteger, ForeignKey('chat_meetings.id'), nullable=False)
    
    # Action identification
    action_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True)
    action_title = Column(String(500), nullable=False)
    action_description = Column(Text)
    
    # Action classification
    action_type = Column(String(100))   # task, decision, follow_up, research
    priority = Column(String(50))       # high, medium, low
    complexity = Column(String(50))     # simple, moderate, complex
    
    # Assignment and responsibility
    assigned_to_user_id = Column(BigInteger, ForeignKey('user_locations.id'))
    assigned_to_team = Column(String(255))  # Team or department
    assigned_by_expert_id = Column(BigInteger, ForeignKey('experts.id'))  # Which expert suggested
    
    # Timeline and deadlines
    created_date = Column(DateTime, default=datetime.utcnow)
    due_date = Column(DateTime)
    estimated_effort = Column(Integer)  # Hours
    
    # Action context
    agenda_item_source = Column(Integer)  # Which agenda item generated this
    discussion_context = Column(Text)     # Context from the discussion
    dependencies = Column(JSON)           # Other actions this depends on
    
    # Progress tracking
    status = Column(String(50), default='open')  # open, in_progress, completed, blocked
    progress_percentage = Column(DECIMAL(5, 2), default=0)
    completion_date = Column(DateTime)
    
    # Success criteria
    success_criteria = Column(JSON)     # Criteria for completion
    deliverables = Column(JSON)         # Expected deliverables
    quality_standards = Column(JSON)    # Quality requirements
    
    # Resources and support
    required_resources = Column(JSON)   # Resources needed
    support_needed = Column(JSON)       # Support or assistance needed
    budget_required = Column(DECIMAL(15, 2))  # Budget if needed
    
    # Follow-up and tracking
    check_in_frequency = Column(String(50))  # daily, weekly, monthly
    last_update = Column(DateTime)
    update_notes = Column(Text)
    
    # Impact and value
    business_impact = Column(Text)      # Expected business impact
    success_metrics = Column(JSON)      # How to measure success
    risk_factors = Column(JSON)         # Potential risks
    
    # Relationships
    meeting = relationship("ChatMeeting", back_populates="meeting_actions")
    assigned_to_user = relationship("UserLocation")
    assigned_by_expert = relationship("Expert")

class MeetingDocument(Base, BaseModel):
    """Documents referenced or generated during meetings"""
    __tablename__ = 'meeting_documents'
    
    meeting_id = Column(BigInteger, ForeignKey('chat_meetings.id'), nullable=False)
    
    # Document identification
    document_type = Column(String(100))  # reference, output, template, recording
    
    # KM integration
    km_file_id = Column(BigInteger, ForeignKey('km_files.id'))  # Link to KM system
    km_chunk_ids = Column(JSON)         # Specific chunks referenced
    
    # External documents
    external_url = Column(String(1000)) # External document URL
    document_title = Column(String(500))
    document_description = Column(Text)
    
    # Usage in meeting
    referenced_at = Column(DateTime)    # When it was referenced
    referenced_by_expert_id = Column(BigInteger, ForeignKey('experts.id'))
    usage_context = Column(Text)        # How it was used in the meeting
    
    # Document relevance
    relevance_score = Column(DECIMAL(3, 2))  # How relevant to the meeting
    usefulness_rating = Column(DECIMAL(3, 2)) # How useful participants found it
    
    # Access and permissions
    shared_with_participants = Column(Boolean, default=True)
    access_level = Column(String(50), default='meeting')  # meeting, organization, public
    
    # Relationships
    meeting = relationship("ChatMeeting", back_populates="meeting_documents")
    km_file = relationship("KmFile")
    referenced_by_expert = relationship("Expert")

class MeetingTemplate(Base, BaseModel):
    """Templates for different types of meetings"""
    __tablename__ = 'meeting_templates'
    
    # Template identification
    template_name = Column(String(255), nullable=False)
    template_type = Column(SQLEnum(MeetingType), nullable=False)
    description = Column(Text)
    
    # Platform and organization scope
    platform = Column(String(50))      # Which platform this applies to
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))  # Org-specific or global
    
    # Template structure
    agenda_template = Column(JSON)      # Default agenda items
    objectives_template = Column(JSON)  # Default objectives
    success_criteria_template = Column(JSON)  # Default success criteria
    
    # Participant configuration
    default_experts = Column(JSON)      # Default expert types to include
    moderator_instructions = Column(Text) # Instructions for AI moderator
    facilitation_style = Column(String(100)) # Default facilitation style
    
    # AI configuration
    prompt_templates = Column(JSON)     # AI prompt templates
    interaction_rules = Column(JSON)    # Rules for expert interactions
    
    # Meeting flow
    estimated_duration = Column(Integer) # Default duration in minutes
    agenda_time_allocation = Column(JSON) # Time allocation for agenda items
    break_points = Column(JSON)         # Suggested break points
    
    # Quality and effectiveness
    usage_count = Column(Integer, default=0)
    average_effectiveness = Column(DECIMAL(3, 2))
    user_rating = Column(DECIMAL(3, 2))
    
    # Template metadata
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'))
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    organization = relationship("Organization")
    created_by = relationship("UserLocation")