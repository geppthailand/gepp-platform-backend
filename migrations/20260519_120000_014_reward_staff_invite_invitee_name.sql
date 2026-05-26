-- Add invitee_name column to reward_staff_invites
-- Admins can label each invite with the person they're inviting (e.g. "John doe — front desk")
-- so they can track which invite is for whom in the InvitesDrawer.

ALTER TABLE reward_staff_invites
ADD COLUMN IF NOT EXISTS invitee_name VARCHAR(255) NULL;

COMMENT ON COLUMN reward_staff_invites.invitee_name IS
  'Optional label for who this invite is meant for — set by admin at creation, shown in the invites list.';
