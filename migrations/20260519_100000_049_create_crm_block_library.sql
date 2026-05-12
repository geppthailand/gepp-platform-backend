-- Sprint 8: block library table + seed 12 standard system blocks
-- Stores reusable block definitions that can be cloned into templates.
-- organization_id NULL = platform-level (system) block; non-NULL = org-private block.

CREATE TABLE IF NOT EXISTS crm_block_library (
    id               BIGSERIAL     PRIMARY KEY,
    organization_id  BIGINT        REFERENCES organizations(id) ON DELETE CASCADE,
    block_type       VARCHAR(32)   NOT NULL,
    name             VARCHAR(255)  NOT NULL,
    description      TEXT,
    default_props    JSONB         NOT NULL DEFAULT '{}',
    thumbnail_url    VARCHAR(500),
    sort_order       INTEGER       NOT NULL DEFAULT 0,
    is_system        BOOLEAN       NOT NULL DEFAULT FALSE,
    is_active        BOOLEAN       NOT NULL DEFAULT TRUE,
    created_date     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_date     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    deleted_date     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_crm_block_library_org
    ON crm_block_library (organization_id)
    WHERE is_active = TRUE AND deleted_date IS NULL;

CREATE INDEX IF NOT EXISTS idx_crm_block_library_type
    ON crm_block_library (block_type)
    WHERE is_active = TRUE AND deleted_date IS NULL;

CREATE INDEX IF NOT EXISTS idx_crm_block_library_system
    ON crm_block_library (is_system)
    WHERE is_active = TRUE AND deleted_date IS NULL;

COMMENT ON TABLE crm_block_library IS
    'Reusable email block definitions (Sprint 8). organization_id NULL = system block. Blocks are dragged into the BlockEmailBuilder composer.';
COMMENT ON COLUMN crm_block_library.block_type IS
    'Must match a key in email_blocks.py _RENDERERS: header|hero|hero_image|accent_bar|body|greeting|signoff|cta|secondary_cta|stats_grid|bullet_list|numbered_steps|agenda_list|feature_list|speaker_list|callout_box|ps_block|divider|subheading|quote|footer';
COMMENT ON COLUMN crm_block_library.default_props IS
    'JSON props matching the schema declared in BlockRegistry.ts for this block_type. Cloned as a starting point when the user drags the block to the canvas.';
COMMENT ON COLUMN crm_block_library.is_system IS
    'TRUE for platform-seeded blocks (organization_id IS NULL). Only Opus/super-admin can modify these.';


-- ─── Seed 12 standard system blocks ────────────────────────────────────────
-- These correspond 1-to-1 with the most commonly used renderer.js blocks.
-- default_props mirrors the JS function signature defaults.

INSERT INTO crm_block_library
    (organization_id, block_type, name, description, default_props, sort_order, is_system)
VALUES
    (NULL, 'header', 'Logo Header',
     'Brand logo centered at the top of the email.',
     '{"logoUrl": ""}',
     10, TRUE),

    (NULL, 'accent_bar', 'Accent Bar',
     'Thin lime-green horizontal divider — trademark GEPP brand touch.',
     '{}',
     20, TRUE),

    (NULL, 'hero', 'Hero Banner',
     'Full-width dark hero section with headline and optional subheadline.',
     '{"headline": "Your Headline Here", "subheadline": "Supporting text that explains the value proposition.", "bgColor": "", "accentColor": ""}',
     30, TRUE),

    (NULL, 'greeting', 'Personalized Greeting',
     'Hi {{user.first_name}}, — personalized opening line.',
     '{"greeting": "Hi", "name": "{{user.first_name}}"}',
     40, TRUE),

    (NULL, 'body', 'Body Text',
     'One or more plain-text paragraphs. Supports \\n for line breaks.',
     '{"paragraphs": ["Enter your message here."], "paddingTop": 32, "paddingBottom": 32}',
     50, TRUE),

    (NULL, 'cta', 'Call-to-Action Button',
     'Primary CTA button with MSO VML fallback for Outlook.',
     '{"text": "Get Started", "url": "https://geppdatasolutions.com/login", "align": "center", "bgColor": "", "textColor": ""}',
     60, TRUE),

    (NULL, 'stats_grid', 'Stats Grid',
     'Up to 4 highlighted statistics side by side.',
     '{"stats": [{"value": "58%", "label": "Landfill Reduction"}, {"value": "50%", "label": "Cost Savings"}, {"value": "77M+", "label": "Trees Equiv. GHG"}]}',
     70, TRUE),

    (NULL, 'bullet_list', 'Bullet List',
     'Checkmark-icon list — ideal for features or benefits.',
     '{"items": ["Feature one", "Feature two", "Feature three"], "icon": "&#10003;", "iconColor": ""}',
     80, TRUE),

    (NULL, 'numbered_steps', 'Numbered Steps',
     'Step-by-step guide with numbered circle badges and connectors.',
     '{"steps": [{"title": "Step 1", "description": "What to do first."}, {"title": "Step 2", "description": "What to do next."}]}',
     90, TRUE),

    (NULL, 'feature_list', 'Feature Cards',
     'Card-style feature list with left accent border.',
     '{"features": [{"title": "Smart Insights", "description": "AI-driven recommendations based on your ESG data."}, {"title": "Waste Tracking", "description": "Hardware-verified waste data in real time."}]}',
     100, TRUE),

    (NULL, 'signoff', 'Signoff',
     'Best regards — sender name and title.',
     '{"senderName": "The GEPP Team", "senderTitle": ""}',
     110, TRUE),

    (NULL, 'footer', 'Standard Footer',
     'Social icons, address, unsubscribe link, and copyright.',
     '{}',
     120, TRUE)

ON CONFLICT DO NOTHING;
