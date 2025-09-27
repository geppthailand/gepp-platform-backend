-- Migration: Add missing platform enum values
-- Date: 2025-09-16 14:00:00
-- Description: Add BUSINESS, REWARDS, GEPP_BUSINESS_WEB, GEPP_REWARD_APP, ADMIN_WEB, GEPP_EPR_WEB values to platform_enum

-- Add new platform enum values (each must be in separate transaction)
ALTER TYPE platform_enum ADD VALUE IF NOT EXISTS 'BUSINESS';
ALTER TYPE platform_enum ADD VALUE IF NOT EXISTS 'REWARDS';
ALTER TYPE platform_enum ADD VALUE IF NOT EXISTS 'GEPP_BUSINESS_WEB';
ALTER TYPE platform_enum ADD VALUE IF NOT EXISTS 'GEPP_REWARD_APP';
ALTER TYPE platform_enum ADD VALUE IF NOT EXISTS 'ADMIN_WEB';
ALTER TYPE platform_enum ADD VALUE IF NOT EXISTS 'GEPP_EPR_WEB';