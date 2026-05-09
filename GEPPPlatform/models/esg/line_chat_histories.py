"""
ESG LINE Chat History — KhunGEPP conversation log.

One row per inbound or outbound message. Conversation key is
`line_user_id`, NOT a user id, so unregistered LINE users (no
`esg_users` row) can still build up a chat history that we keep
as lead capture.

When an unregistered user later accepts an invite, NEW rows
carry `organization_id` while the old "lead" rows retain NULL.
We deliberately don't backfill — admins want to see the
pre-join lead conversation as-is.

See migration 20260508_120000_064_create_esg_line_chat_histories.sql
for the table definition and design notes.
"""

from sqlalchemy import (
    BigInteger,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
)

from ..base import Base, BaseModel


class EsgLineChatHistory(Base, BaseModel):
    __tablename__ = 'esg_line_chat_histories'

    # LINE platform user id (Uxxx...). Always set — this is the
    # conversation key.
    line_user_id = Column(String(64), nullable=False, index=True)

    # Nullable on purpose: unregistered (lead) users have no org
    # binding yet. ON DELETE SET NULL via the FK in the migration.
    organization_id = Column(
        BigInteger,
        ForeignKey('organizations.id', ondelete='SET NULL'),
        nullable=True,
    )

    # 'user' = inbound from the customer; 'assistant' = outbound from
    # KhunGEPP. Don't use an enum — keeping it as a short string keeps
    # the table portable and easy to grep.
    role = Column(String(16), nullable=False)

    # Raw message body. The chat service caps assistant content at
    # ~300 chars before persisting; user content is whatever the
    # customer typed (trimmed at 4000 by the service).
    content = Column(Text, nullable=False)

    # 'th' / 'en' / 'mixed' / NULL — set by a cheap heuristic in the
    # chat service so analytics can group by language.
    language = Column(String(8))

    # Best-effort accounting. Only set on assistant rows.
    model = Column(String(64))
    tokens_in = Column(Integer)
    tokens_out = Column(Integer)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'line_user_id': self.line_user_id,
            'organization_id': self.organization_id,
            'role': self.role,
            'content': self.content,
            'language': self.language,
            'model': self.model,
            'tokens_in': self.tokens_in,
            'tokens_out': self.tokens_out,
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
        }
