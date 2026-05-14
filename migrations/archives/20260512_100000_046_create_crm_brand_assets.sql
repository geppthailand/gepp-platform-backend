-- CRM brand assets — single source of truth for colors, fonts, company info, social
-- Seeded from gepp-edm-main/js/brand.js (Phase 2 Sprint 7).
-- organization_id = NULL means platform default; per-org rows override.

CREATE TABLE IF NOT EXISTS crm_brand_assets (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT REFERENCES organizations(id) ON DELETE CASCADE,
    asset_key VARCHAR(64) NOT NULL,
    asset_value TEXT NOT NULL,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (organization_id, asset_key)
);

CREATE INDEX IF NOT EXISTS idx_crm_brand_assets_org_key
    ON crm_brand_assets (organization_id, asset_key);

COMMENT ON TABLE crm_brand_assets IS
    'Brand constants (colors, fonts, company info, social) for email templates and AI generation. organization_id NULL = platform default, per-org rows override.';

-- ────────────────────────────────────────────────────────────────────
-- Seed platform defaults (organization_id = NULL)
-- Mirrors gepp-edm-main/js/brand.js — keep in sync via update statements only.
-- ────────────────────────────────────────────────────────────────────

INSERT INTO crm_brand_assets (organization_id, asset_key, asset_value) VALUES
    -- COLORS
    (NULL, 'color_primary',         '#13754A'),
    (NULL, 'color_primary_light',   '#1a9960'),
    (NULL, 'color_primary_dark',    '#0d5535'),
    (NULL, 'color_lime',            '#CEDD42'),
    (NULL, 'color_lime_dark',       '#b5c42a'),
    (NULL, 'color_forest',          '#0A1F14'),
    (NULL, 'color_dark',            '#0D1117'),
    (NULL, 'color_surface_light',   '#F7F8F6'),
    (NULL, 'color_surface_white',   '#FFFFFF'),
    (NULL, 'color_surface_border',  '#E2E8F0'),
    (NULL, 'color_text_primary',    '#0D1117'),
    (NULL, 'color_text_secondary',  '#475569'),
    (NULL, 'color_text_muted',      '#94A3B8'),
    (NULL, 'color_text_inverse',    '#F7F8F6'),
    -- FONT
    (NULL, 'font_stack',            'Inter, -apple-system, BlinkMacSystemFont, ''Segoe UI'', Roboto, Helvetica, Arial, sans-serif'),
    (NULL, 'font_mono',             '''Courier New'', Courier, monospace'),
    -- EMAIL DIMS
    (NULL, 'email_width',           '600'),
    (NULL, 'email_padding',         '40'),
    -- COMPANY
    (NULL, 'company_name',          'GEPP Intelligence'),
    (NULL, 'company_legal_name',    'GEPP Sa-Ard Co., Ltd.'),
    (NULL, 'company_tagline',       'Waste Data That Works For You'),
    (NULL, 'company_description',   'The intelligence platform for waste management. Hardware-verified data, active insights, and ESG compliance for Southeast Asia.'),
    (NULL, 'company_email',         'hello@gepp.me'),
    (NULL, 'company_phone',         '06-4043-7166'),
    (NULL, 'company_address_full',  '559/186 Nonsi Road, Chong Nonsi, Yan Nawa District, Bangkok 10120, Thailand'),
    (NULL, 'company_url',           'https://gepp.me'),
    (NULL, 'company_platform_login','https://geppdatasolutions.com/login'),
    (NULL, 'logo_url',              'https://gepp.me/images/brand/gepp-logo.png'),
    -- SOCIAL
    (NULL, 'social_facebook_url',   'https://facebook.com/geppthailand'),
    (NULL, 'social_linkedin_url',   'https://th.linkedin.com/company/geppsaard'),
    (NULL, 'social_youtube_url',    'https://youtube.com/channel/UCrweanNIwXkG85H-M2VFd-Q'),
    (NULL, 'social_instagram_url',  'https://instagram.com/gepp_thailand'),
    -- IMPACT STATS
    (NULL, 'impact_landfill_reduction_value', '58%'),
    (NULL, 'impact_landfill_reduction_label', 'Landfill Reduction'),
    (NULL, 'impact_cost_savings_value',       '50%'),
    (NULL, 'impact_cost_savings_label',       'Cost Savings'),
    (NULL, 'impact_ghg_trees_value',          '77M+'),
    (NULL, 'impact_ghg_trees_label',          'Trees Equivalent GHG Prevention'),
    (NULL, 'impact_time_to_results_value',    '10 months'),
    (NULL, 'impact_time_to_results_label',    'Average Time to Results')
ON CONFLICT (organization_id, asset_key) DO UPDATE
    SET asset_value = EXCLUDED.asset_value,
        updated_date = NOW();
