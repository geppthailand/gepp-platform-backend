"""
Brand assets service — read/write the crm_brand_assets table.

Resolution order: per-org override → platform default (organization_id IS NULL).
Used by:
  - email_renderer.py — expand brand variables at template render time
  - prompts/crm_email_gen/default/scripts/generate_email.py — feed brand context into AI prompt
  - block builder (Sprint 8) — pull colors/fonts when rendering blocks
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ....exceptions import BadRequestException, NotFoundException

logger = logging.getLogger(__name__)


# ───────────────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────────────

def get_brand_context(db_session: Session, organization_id: Optional[int]) -> Dict[str, str]:
    """
    Return the resolved brand context for an organization as a flat dict.

    Per-org rows override platform defaults. Missing keys silently absent.

    Usage:
        ctx = get_brand_context(db, org_id)
        ctx["color_primary"]      # e.g. "#13754A"
        ctx["company_name"]       # e.g. "GEPP Intelligence"
    """
    if organization_id is not None:
        try:
            organization_id = int(organization_id)
        except (TypeError, ValueError):
            organization_id = None

    rows = db_session.execute(
        text(
            """
            SELECT asset_key, asset_value
            FROM crm_brand_assets
            WHERE organization_id IS NULL
               OR organization_id = :org_id
            ORDER BY organization_id NULLS FIRST  -- platform first, then org overrides
            """
        ),
        {"org_id": organization_id},
    ).fetchall()

    out: Dict[str, str] = {}
    for key, value in rows:
        out[key] = value  # org row overwrites the earlier platform default
    return out


def list_brand_assets(db_session: Session, organization_id: Optional[int]) -> List[Dict[str, Any]]:
    """
    Admin-facing listing. Returns BOTH platform + org rows so the UI can show
    which keys are overridden and which fall back to the default.
    """
    rows = db_session.execute(
        text(
            """
            SELECT
                key AS asset_key,
                MAX(CASE WHEN organization_id IS NULL THEN asset_value END)  AS platform_default,
                MAX(CASE WHEN organization_id = :org_id THEN asset_value END) AS org_override
            FROM (
                SELECT asset_key AS key, asset_value, organization_id FROM crm_brand_assets
                WHERE organization_id IS NULL OR organization_id = :org_id
            ) s
            GROUP BY key
            ORDER BY key
            """
        ),
        {"org_id": organization_id},
    ).fetchall()

    return [
        {
            "key": r[0],
            "platformDefault": r[1],
            "orgOverride": r[2],
            "resolvedValue": r[2] if r[2] is not None else r[1],
            "isOverridden": r[2] is not None,
        }
        for r in rows
    ]


def set_brand_asset(
    db_session: Session,
    organization_id: int,
    asset_key: str,
    asset_value: str,
) -> Dict[str, Any]:
    """Set/replace a per-org brand asset override. Requires organization_id."""
    if not organization_id:
        raise BadRequestException("organization_id is required for set_brand_asset")
    if not asset_key or not asset_key.strip():
        raise BadRequestException("asset_key is required")
    if asset_value is None:
        raise BadRequestException("asset_value is required (use delete to remove an override)")

    asset_key = asset_key.strip()

    db_session.execute(
        text(
            """
            INSERT INTO crm_brand_assets (organization_id, asset_key, asset_value)
            VALUES (:org_id, :key, :val)
            ON CONFLICT (organization_id, asset_key) DO UPDATE
                SET asset_value = EXCLUDED.asset_value,
                    updated_date = NOW()
            """
        ),
        {"org_id": int(organization_id), "key": asset_key, "val": asset_value},
    )
    db_session.commit()

    return {
        "organizationId": int(organization_id),
        "assetKey": asset_key,
        "assetValue": asset_value,
    }


def delete_brand_asset(
    db_session: Session,
    organization_id: int,
    asset_key: str,
) -> Dict[str, Any]:
    """Remove a per-org override. The platform default (NULL row) is never touched."""
    if not organization_id:
        raise BadRequestException("organization_id is required")

    result = db_session.execute(
        text(
            """
            DELETE FROM crm_brand_assets
            WHERE organization_id = :org_id AND asset_key = :key
            """
        ),
        {"org_id": int(organization_id), "key": asset_key},
    )
    db_session.commit()
    return {"deleted": int(result.rowcount or 0)}
