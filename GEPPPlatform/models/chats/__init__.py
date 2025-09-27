"""
Chats Module
Comprehensive chat bot interactions, expert agents, and collaborative meeting system
across multiple GEPP platforms
"""

# Expert agents and configuration
from .experts import (
    Platform, ExpertType, ExpertStatus, AgentCapability,
    Expert, ExpertKnowledgeAccess, ExpertPromptTemplate, ExpertConfiguration
)

# Chat conversations
from .conversations import (
    ChatStatus, MessageType, MessageRole, ChatPlatform,
    Chat, ChatHistory, ChatContext, ChatFeedback
)

# Meeting and collaboration
from .meetings import (
    MeetingStatus, MeetingType, ParticipantRole, SummaryType,
    ChatMeeting, ChatMeetingHistory, ChatMeetingParticipant,
    ChatMeetingSummary, MeetingAction, MeetingDocument
)

__all__ = [
    # Expert models
    'Platform', 'ExpertType', 'ExpertStatus', 'AgentCapability',
    'Expert', 'ExpertKnowledgeAccess', 'ExpertPromptTemplate', 'ExpertConfiguration',
    
    # Chat models
    'ChatStatus', 'MessageType', 'MessageRole', 'ChatPlatform',
    'Chat', 'ChatHistory', 'ChatContext', 'ChatFeedback',
    
    # Meeting models
    'MeetingStatus', 'MeetingType', 'ParticipantRole', 'SummaryType',
    'ChatMeeting', 'ChatMeetingHistory', 'ChatMeetingParticipant',
    'ChatMeetingSummary', 'MeetingAction', 'MeetingDocument'
]