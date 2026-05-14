-- ============================================================
-- esg_line_chat_histories — KhunGEPP chat conversation log
-- ============================================================
-- Stores the running conversation between LINE users and the
-- KhunGEPP (คุณเก็บ) LLM assistant. Append-only.
--
-- Conversation key is `line_user_id` so unregistered users (no
-- esg_users row, no organization_id) can still chat — that's
-- intentional, we use this table for lead capture too.
--
-- `organization_id` is populated only AFTER a user accepts an
-- invite. Pre-existing rows from when they were a lead retain
-- NULL, which is what admins want to see ("the conversation
-- started before they joined org X").
--
-- Read pattern: when composing the next reply, the chat service
-- pulls the most recent rows for `line_user_id`, walks newest →
-- oldest accumulating `len(content)`, and stops once the total
-- exceeds 10,000 chars. The 10k cap is purely a read-side budget
-- — we never delete or prune rows here.
-- ============================================================

CREATE TABLE IF NOT EXISTS esg_line_chat_histories (
    id BIGSERIAL PRIMARY KEY,

    line_user_id VARCHAR(64) NOT NULL,                         -- LINE platform user id (Uxxx...)
    organization_id BIGINT REFERENCES organizations(id) ON DELETE SET NULL,

    role VARCHAR(16) NOT NULL,                                 -- 'user' | 'assistant'
    content TEXT NOT NULL,                                     -- raw message body
    language VARCHAR(8),                                       -- 'th' | 'en' | 'mixed' | NULL

    -- Best-effort accounting (assistant rows only).
    model VARCHAR(64),
    tokens_in INTEGER,
    tokens_out INTEGER,

    -- BaseModel parity
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);

-- Fast history fetch: "most recent rows for this LINE user".
CREATE INDEX IF NOT EXISTS idx_esg_chat_line_user_created
    ON esg_line_chat_histories (line_user_id, created_date DESC)
    WHERE is_active = TRUE;

-- Lead analytics: "how many unregistered users chatted this month".
CREATE INDEX IF NOT EXISTS idx_esg_chat_org_created
    ON esg_line_chat_histories (organization_id, created_date DESC);

COMMENT ON TABLE esg_line_chat_histories IS 'KhunGEPP chat history per LINE user. Retained indefinitely. organization_id is NULL for unregistered (lead) users — populated only on rows created AFTER they accept an org invite. role IN (user, assistant); content is the raw message body, capped on the assistant side at ~300 chars by the chat service.';
COMMENT ON COLUMN esg_line_chat_histories.line_user_id IS 'LINE platform user id (LINE Login userId). Conversation key — same id across registered and unregistered states.';
COMMENT ON COLUMN esg_line_chat_histories.organization_id IS 'Set after the user joins an org. Pre-join rows keep NULL on purpose so the lead history is preserved.';
COMMENT ON COLUMN esg_line_chat_histories.role IS 'user = inbound from the customer; assistant = outbound from KhunGEPP.';
COMMENT ON COLUMN esg_line_chat_histories.tokens_in IS 'Best-effort prompt token count from OpenRouter response. Only set on assistant rows.';
