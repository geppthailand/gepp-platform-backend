-- Allow manually-created CRM leads that are not attached to a platform organization.
-- The free-text organization/company name remains stored on crm_leads.company.

ALTER TABLE crm_leads
    ALTER COLUMN organization_id DROP NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS crm_leads_unassigned_email_unique
    ON crm_leads (email)
    WHERE organization_id IS NULL;
