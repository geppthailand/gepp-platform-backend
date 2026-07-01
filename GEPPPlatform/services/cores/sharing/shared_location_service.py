"""
Shared Location Service — cross-organization location data sharing.

Company A ("source") shares a specific location (source_user_location_id) to Company B
("target", resolved from target_email's owned org). Company B surfaces that location's data
as READ-ONLY via a virtual node in its organization_setup.root_nodes, bounded by a date window.

Security model:
- All mutations are OWNER-gated (Organization.owner_id == actor user_id).
- Email resolution is SILENT (anti-enumeration): if target_email is unknown or not an org owner,
  the share is still created but is_valid=false and no email is sent — no error is raised.
- Reciprocal shares are BLOCKED at create time (org-level): if B already has an effective share
  to A, A cannot share anything to B (raises ConflictException with RECIPROCAL_SHARE_EXISTS so the
  frontend can offer the "go cancel B's share" CTA).
"""

import os
import json
import secrets
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
from sqlalchemy import func, and_, or_

from ....models.shared_user_location import SharedUserLocation
from ....models.subscriptions.organizations import Organization, OrganizationSetup
from ....models.users.user_location import UserLocation
from ....libs.exceptions import (
    NotFoundException,
    BadRequestException,
    ForbiddenException,
    ConflictException,
)

logger = logging.getLogger(__name__)


def _send_share_notification_email(to_email: str, subject: str, html_content: str) -> bool:
    """Send a share-notification email via the PROD-GEPPEmailNotification Lambda.

    Mirrors AuthHandlers._send_email_via_lambda so we don't need to instantiate the auth
    handler (which pulls in JWT/bcrypt setup). Best-effort: never raises.
    """
    try:
        lambda_function_name = os.environ.get('EMAIL_LAMBDA_FUNCTION', 'PROD-GEPPEmailNotification')
        message = {
            "from_email": os.environ.get('EMAIL_FROM', 'noreply@gepp.me'),
            "from_name": os.environ.get('EMAIL_FROM_NAME', 'GEPP Platform'),
            "to": [{"email": to_email, "type": "to"}],
            "subject": subject,
            "html": html_content,
        }
        lambda_client = boto3.client('lambda')
        response = lambda_client.invoke(
            FunctionName=lambda_function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps({"data": {"message": message}}).encode('utf-8'),
        )
        if response.get('FunctionError'):
            logger.warning("Share email Lambda error: %s", response.get('FunctionError'))
            return False
        return True
    except Exception as e:  # noqa: BLE001 — email is best-effort
        logger.warning("Error sending share notification email: %s", str(e))
        return False


def _parse_dt(value: Any) -> Optional[datetime]:
    """Parse an ISO datetime string (accepts trailing 'Z'); pass through datetimes; else None."""
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value
    try:
        s = str(value).strip()
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


class SharedLocationService:
    def __init__(self, db):
        self.db = db

    # ── ownership ────────────────────────────────────────────────────────────
    def _get_org(self, organization_id: int) -> Optional[Organization]:
        return self.db.query(Organization).filter(
            Organization.id == organization_id,
            Organization.deleted_date.is_(None),
        ).first()

    def _require_owner(self, organization_id: int, actor_user_id: int) -> Organization:
        org = self._get_org(organization_id)
        if not org:
            raise NotFoundException('Organization not found')
        if org.owner_id != actor_user_id:
            raise ForbiddenException('Only the organization owner may manage shared locations')
        return org

    # ── serialization ────────────────────────────────────────────────────────
    @staticmethod
    def _iso(dt: Optional[datetime]) -> Optional[str]:
        return dt.isoformat() if dt else None

    def _serialize(self, share: SharedUserLocation, include_email: bool = True) -> Dict[str, Any]:
        data = {
            'id': share.id,
            'source_organization_id': share.source_organization_id,
            'source_user_location_id': share.source_user_location_id,
            'target_organization_id': share.target_organization_id,
            'name': share.name,
            'description': share.description,
            'share_code': share.share_code,
            'is_active': share.is_active,
            'is_valid': share.is_valid,
            'is_rejected': share.is_rejected,
            'placed_parent_node_id': share.placed_parent_node_id,
            'expired_date': self._iso(share.expired_date),
            'start_date': self._iso(share.start_date),
            'end_date': self._iso(share.end_date),
            'created_date': self._iso(share.created_date),
            'updated_date': self._iso(share.updated_date),
        }
        if include_email:
            data['target_email'] = share.target_email
        return data

    # ── source-side listing (shares A created for one location) ───────────────
    def list_shares(self, source_organization_id: int, source_user_location_id: int,
                    actor_user_id: int) -> List[Dict[str, Any]]:
        self._require_owner(source_organization_id, actor_user_id)
        shares = self.db.query(SharedUserLocation).filter(
            SharedUserLocation.source_organization_id == source_organization_id,
            SharedUserLocation.source_user_location_id == source_user_location_id,
            SharedUserLocation.deleted_date.is_(None),
        ).order_by(SharedUserLocation.created_date.desc()).all()
        return [self._serialize(s) for s in shares]

    def get_share(self, share_id: int, source_organization_id: int,
                  actor_user_id: int) -> Dict[str, Any]:
        self._require_owner(source_organization_id, actor_user_id)
        share = self.db.query(SharedUserLocation).filter(
            SharedUserLocation.id == share_id,
            SharedUserLocation.source_organization_id == source_organization_id,
            SharedUserLocation.deleted_date.is_(None),
        ).first()
        if not share:
            raise NotFoundException('Share not found')
        return self._serialize(share)

    # ── email → owner resolution (silent) ─────────────────────────────────────
    def _resolve_target_org(self, target_email: str) -> Optional[Organization]:
        """Return the org owned by the user with this email, or None. Never raises."""
        if not target_email:
            return None
        user = self.db.query(UserLocation).filter(
            func.lower(UserLocation.email) == target_email.strip().lower(),
            UserLocation.is_user.is_(True),
            UserLocation.deleted_date.is_(None),
        ).first()
        if not user:
            return None
        # The user must be the OWNER of some organization to receive a share.
        return self.db.query(Organization).filter(
            Organization.owner_id == user.id,
            Organization.deleted_date.is_(None),
        ).order_by(Organization.id.asc()).first()

    def _has_effective_share(self, source_org_id: int, target_org_id: int) -> bool:
        """True if an effective (usable) share source→target currently exists."""
        now = datetime.now(timezone.utc)
        q = self.db.query(SharedUserLocation.id).filter(
            SharedUserLocation.source_organization_id == source_org_id,
            SharedUserLocation.target_organization_id == target_org_id,
            SharedUserLocation.deleted_date.is_(None),
            SharedUserLocation.is_active.is_(True),
            SharedUserLocation.is_valid.is_(True),
            SharedUserLocation.is_rejected.is_(False),
            or_(SharedUserLocation.expired_date.is_(None),
                SharedUserLocation.expired_date > now),
        )
        return self.db.query(q.exists()).scalar()

    # ── create ────────────────────────────────────────────────────────────────
    def create_share(self, source_organization_id: int, source_user_location_id: int,
                     actor_user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        self._require_owner(source_organization_id, actor_user_id)

        # The shared location must be a REAL location row owned by the source org.
        loc = self.db.query(UserLocation).filter(
            UserLocation.id == source_user_location_id,
            UserLocation.organization_id == source_organization_id,
            UserLocation.is_location.is_(True),
            UserLocation.deleted_date.is_(None),
        ).first()
        if not loc:
            raise BadRequestException('source_user_location_id must be a real location in your organization')

        target_email = (data.get('target_email') or '').strip()
        if not target_email:
            raise BadRequestException('target_email is required')

        share = SharedUserLocation(
            source_organization_id=source_organization_id,
            source_user_location_id=source_user_location_id,
            target_organization_id=None,
            name=data.get('name'),
            description=data.get('description'),
            target_email=target_email,
            share_code=secrets.token_urlsafe(16),
            is_active=data.get('is_active', True),
            expired_date=_parse_dt(data.get('expired_date')),
            start_date=_parse_dt(data.get('start_date')),
            end_date=_parse_dt(data.get('end_date')),
            is_valid=False,
            is_rejected=False,
        )

        # Silent email resolution + reciprocal-cycle block.
        target_org = self._resolve_target_org(target_email)
        send_email = False
        if target_org is not None:
            # Org-level reciprocal (งูกินหาง) block — hard error, surfaced to the sharer.
            if self._has_effective_share(target_org.id, source_organization_id):
                exc = ConflictException(
                    message=(f"Cannot share to organization "
                             f"'{target_org.name}' — a reciprocal share from it to you already exists."),
                    error_code='RECIPROCAL_SHARE_EXISTS',
                )
                exc.errors = [{'target_org_name': target_org.name,
                               'target_organization_id': target_org.id}]
                raise exc
            share.target_organization_id = target_org.id
            share.is_valid = True
            send_email = True
        # else: unresolved / not an owner → is_valid stays False, no email, no error (silent).

        self.db.add(share)
        self.db.commit()
        self.db.refresh(share)

        if send_email:
            self._notify_recipient(share, loc, target_org)

        return self._serialize(share)

    def _notify_recipient(self, share: SharedUserLocation, loc: UserLocation,
                          target_org: Organization) -> None:
        source_org = self._get_org(share.source_organization_id)
        source_name = source_org.name if source_org else 'องค์กร'
        loc_name = loc.display_name or loc.name_th or loc.name_en or 'สถานที่'
        subject = f"[GEPP] {source_name} ได้แชร์ข้อมูลสถานที่ให้คุณ / shared a location with you"
        html = (
            f"<p>เรียนเจ้าของ {target_org.name},</p>"
            f"<p><b>{source_name}</b> ได้แชร์ข้อมูลสถานที่ <b>{loc_name}</b> "
            f"(“{share.name or '-'}”) ให้กับองค์กรของคุณ</p>"
            f"<p>เปิด GEPP Business → สถานที่ &amp; แท๊ก → แผนผังองค์กร แล้วเปิดถาด "
            f"“สถานที่ได้รับแชร์” เพื่อดึงสถานที่นี้เข้าสู่ผังองค์กรของคุณ (ข้อมูลจะเป็นแบบอ่านอย่างเดียว)</p>"
            f"<hr><p><b>{source_name}</b> shared the location <b>{loc_name}</b> with your "
            f"organization. Open GEPP Business → Locations &amp; Tags → Org chart → the "
            f"“Shared locations” tray to place it (read-only).</p>"
        )
        _send_share_notification_email(share.target_email, subject, html)

    # ── update (source owner; email immutable) ────────────────────────────────
    def update_share(self, share_id: int, source_organization_id: int,
                     actor_user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        self._require_owner(source_organization_id, actor_user_id)
        share = self.db.query(SharedUserLocation).filter(
            SharedUserLocation.id == share_id,
            SharedUserLocation.source_organization_id == source_organization_id,
            SharedUserLocation.deleted_date.is_(None),
        ).first()
        if not share:
            raise NotFoundException('Share not found')

        # target_email is intentionally NOT editable.
        if 'name' in data:
            share.name = data.get('name')
        if 'description' in data:
            share.description = data.get('description')
        if 'is_active' in data:
            share.is_active = bool(data.get('is_active'))
        if 'expired_date' in data:
            share.expired_date = _parse_dt(data.get('expired_date'))
        if 'start_date' in data:
            share.start_date = _parse_dt(data.get('start_date'))
        if 'end_date' in data:
            share.end_date = _parse_dt(data.get('end_date'))

        self.db.commit()
        self.db.refresh(share)
        return self._serialize(share)

    # ── delete (source owner, soft) ───────────────────────────────────────────
    def delete_share(self, share_id: int, source_organization_id: int,
                     actor_user_id: int) -> Dict[str, Any]:
        self._require_owner(source_organization_id, actor_user_id)
        share = self.db.query(SharedUserLocation).filter(
            SharedUserLocation.id == share_id,
            SharedUserLocation.source_organization_id == source_organization_id,
            SharedUserLocation.deleted_date.is_(None),
        ).first()
        if not share:
            raise NotFoundException('Share not found')
        share.deleted_date = datetime.now(timezone.utc)
        share.is_valid = False
        self.db.commit()
        return {'id': share_id, 'deleted': True}

    # ── incoming (target owner) ───────────────────────────────────────────────
    def list_incoming(self, target_organization_id: int, actor_user_id: int) -> List[Dict[str, Any]]:
        """Effective shares granted TO this org — feeds B's canvas Share tray."""
        self._require_owner(target_organization_id, actor_user_id)
        now = datetime.now(timezone.utc)
        shares = self.db.query(SharedUserLocation).filter(
            SharedUserLocation.target_organization_id == target_organization_id,
            SharedUserLocation.deleted_date.is_(None),
            SharedUserLocation.is_active.is_(True),
            SharedUserLocation.is_valid.is_(True),
            SharedUserLocation.is_rejected.is_(False),
            or_(SharedUserLocation.expired_date.is_(None),
                SharedUserLocation.expired_date > now),
        ).order_by(SharedUserLocation.created_date.desc()).all()

        result: List[Dict[str, Any]] = []
        for s in shares:
            src_org = self._get_org(s.source_organization_id)
            loc = self.db.query(UserLocation).filter(
                UserLocation.id == s.source_user_location_id
            ).first()
            loc_name = None
            if loc:
                loc_name = loc.display_name or loc.name_th or loc.name_en
            # Do NOT leak descendant detail — only the wrapper node's identity.
            result.append({
                'share_id': s.id,
                'name': s.name,
                'description': s.description,
                'source_organization_id': s.source_organization_id,
                'source_organization_name': src_org.name if src_org else None,
                'source_location_name': loc_name,
                'placed_parent_node_id': s.placed_parent_node_id,
                'start_date': self._iso(s.start_date),
                'end_date': self._iso(s.end_date),
            })
        return result

    # ── place (target owner drags the shared node into their chart) ───────────
    def place_share(self, share_id: int, target_organization_id: int,
                    actor_user_id: int, parent_node_id: int) -> Dict[str, Any]:
        """Attach a shared node under a real location in the target org's chart.

        Placement is stored on the share record (never in organization_setup.root_nodes),
        so the tree-save pipeline never sees or materializes a virtual node.
        """
        self._require_owner(target_organization_id, actor_user_id)
        share = self.db.query(SharedUserLocation).filter(
            SharedUserLocation.id == share_id,
            SharedUserLocation.target_organization_id == target_organization_id,
            SharedUserLocation.deleted_date.is_(None),
        ).first()
        if not share:
            raise NotFoundException('Share not found')
        if not share.effective():
            raise BadRequestException('This share is no longer available')
        # Parent must be a real location in the TARGET org.
        parent = self.db.query(UserLocation).filter(
            UserLocation.id == parent_node_id,
            UserLocation.organization_id == target_organization_id,
            UserLocation.is_location.is_(True),
            UserLocation.deleted_date.is_(None),
        ).first()
        if not parent:
            raise BadRequestException('parent_node_id must be a real location in your organization')
        share.placed_parent_node_id = parent_node_id
        self.db.commit()
        self.db.refresh(share)
        return self._serialize(share)

    def unplace_share(self, share_id: int, target_organization_id: int,
                      actor_user_id: int) -> Dict[str, Any]:
        """Remove a shared node from the target org's chart WITHOUT rejecting the share.

        Non-destructive: clears placement only (is_valid/is_rejected untouched), so the share
        returns to the tray as an unplaced item that can be dragged back in later.
        """
        self._require_owner(target_organization_id, actor_user_id)
        share = self.db.query(SharedUserLocation).filter(
            SharedUserLocation.id == share_id,
            SharedUserLocation.target_organization_id == target_organization_id,
            SharedUserLocation.deleted_date.is_(None),
        ).first()
        if not share:
            raise NotFoundException('Share not found')
        share.placed_parent_node_id = None
        self.db.commit()
        self.db.refresh(share)
        return self._serialize(share)

    # ── reject (target owner) ─────────────────────────────────────────────────
    def reject_share(self, share_id: int, target_organization_id: int,
                    actor_user_id: int) -> Dict[str, Any]:
        """Recipient rejects/removes a shared node → is_rejected=true, is_valid=false.

        This is also how a reciprocal-share block gets resolved.
        """
        self._require_owner(target_organization_id, actor_user_id)
        share = self.db.query(SharedUserLocation).filter(
            SharedUserLocation.id == share_id,
            SharedUserLocation.target_organization_id == target_organization_id,
            SharedUserLocation.deleted_date.is_(None),
        ).first()
        if not share:
            raise NotFoundException('Share not found')
        share.is_rejected = True
        share.is_valid = False
        share.placed_parent_node_id = None  # unplace: remove from the chart overlay
        self.db.commit()
        self.db.refresh(share)
        return self._serialize(share)
