"""
LIFF Auth Service - Exchange LINE LIFF access token for platform JWT.

Uses existing UserLocation model (shared with GEPP Business).
User must be invited to an organization first — no auto-create org.
"""

import json
import urllib.request
import urllib.error
import jwt
import os
import logging
import secrets
import string
from datetime import datetime, timedelta, timezone

from GEPPPlatform.models.users.user_location import UserLocation
from GEPPPlatform.models.users.user_related import UserInvitation
from GEPPPlatform.models.subscriptions.organizations import Organization
from GEPPPlatform.models.base import PlatformEnum

logger = logging.getLogger(__name__)

JWT_SECRET = os.environ.get('JWT_SECRET_KEY', os.environ.get('JWT_SECRET', 'your-secret-key'))
JWT_ALGORITHM = 'HS256'
JWT_AUTH_EXPIRY_DAYS = 1
JWT_REFRESH_EXPIRY_DAYS = 7

LINE_PROFILE_URL = 'https://api.line.me/v2/profile'


class LiffAuthService:

    def __init__(self, session):
        self.session = session

    # ==========================================
    # LIFF LOGIN
    # ==========================================

    def login_with_line(self, line_access_token: str) -> dict:
        """
        Authenticate via LINE LIFF access token.
        - Fetches LINE profile
        - Finds existing UserLocation by line_user_id
        - If user exists + has org → return JWT
        - If user exists but no org → return needs_invitation=True
        - If user not found → return needs_invitation=True (user must accept invitation first)
        """
        profile = self._get_line_profile(line_access_token)
        if not profile:
            raise ValueError('Failed to fetch LINE profile. Please check LIFF permissions.')

        line_user_id = profile.get('userId')
        if not line_user_id:
            raise ValueError('LINE profile missing userId')

        display_name = profile.get('displayName', '')
        picture_url = profile.get('pictureUrl')

        # Find existing user by line_user_id
        user = (
            self.session.query(UserLocation)
            .filter(
                UserLocation.line_user_id == line_user_id,
                UserLocation.is_active == True,
            )
            .first()
        )

        if not user or not user.organization_id:
            # User not found or not linked to any org — needs invitation
            return {
                'success': False,
                'needs_invitation': True,
                'line_user_id': line_user_id,
                'display_name': display_name,
                'message': 'กรุณากด invitation link จากผู้ดูแลองค์กรก่อนเข้าใช้งาน',
            }

        # User exists + has org → generate JWT
        tokens = self._generate_tokens(user.id, user.organization_id, user.display_name or '')

        return {
            'success': True,
            'auth_token': tokens['auth_token'],
            'refresh_token': tokens['refresh_token'],
            'token_type': 'Bearer',
            'expires_in': 86400,
            'user': {
                'id': user.id,
                'email': user.email or '',
                'displayName': user.display_name or display_name,
                'organizationId': user.organization_id,
                'pictureUrl': user.profile_image_url,
            },
        }

    # ==========================================
    # INVITATION
    # ==========================================

    def generate_invitation(self, organization_id: int, invited_by_id: int) -> dict:
        """Generate an invitation link for an organization. Called from desktop Settings."""
        token = self._generate_invite_token()

        invitation = UserInvitation(
            organization_id=organization_id,
            invited_by_id=invited_by_id,
            invitation_token=token,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        self.session.add(invitation)
        self.session.commit()
        self.session.refresh(invitation)

        # Build LIFF invitation URL
        liff_base = os.environ.get('LIFF_BASE_URL', 'https://esg.gepp.me')
        invite_url = f'{liff_base}/liff?invite={token}'

        return {
            'success': True,
            'invitation_token': token,
            'invitation_url': invite_url,
            'expires_at': str(invitation.expires_at),
        }

    def accept_invitation(self, invitation_token: str, line_access_token: str) -> dict:
        """
        Accept an invitation: validate token, get LINE profile, create/link user to org.
        Called from LIFF when user opens invitation link.
        """
        # Validate invitation
        invitation = (
            self.session.query(UserInvitation)
            .filter(
                UserInvitation.invitation_token == invitation_token,
                UserInvitation.is_active == True,
            )
            .first()
        )
        if not invitation:
            raise ValueError('Invitation link ไม่ถูกต้องหรือหมดอายุ')

        if invitation.expires_at and invitation.expires_at < datetime.utcnow():
            raise ValueError('Invitation link หมดอายุแล้ว กรุณาขอลิงก์ใหม่จากผู้ดูแล')

        if invitation.used_at:
            raise ValueError('Invitation link นี้ถูกใช้งานแล้ว')

        # Get LINE profile
        profile = self._get_line_profile(line_access_token)
        if not profile:
            raise ValueError('Failed to fetch LINE profile')

        line_user_id = profile.get('userId')
        display_name = profile.get('displayName', '')
        picture_url = profile.get('pictureUrl')

        # Check if user with this line_user_id already exists
        user = (
            self.session.query(UserLocation)
            .filter(
                UserLocation.line_user_id == line_user_id,
                UserLocation.is_active == True,
            )
            .first()
        )

        if user and user.organization_id:
            # User already belongs to an org — block
            raise ValueError('LINE ID นี้เชื่อมต่อกับองค์กรอื่นอยู่แล้ว กรุณาให้ผู้ดูแลลบออกก่อน')

        if user:
            # Existing user without org — link to the new org
            user.organization_id = invitation.organization_id
            if not user.display_name:
                user.display_name = display_name
            if not user.profile_image_url and picture_url:
                user.profile_image_url = picture_url
        else:
            # New user — create UserLocation linked to org
            user = UserLocation(
                is_user=True,
                is_location=False,
                line_user_id=line_user_id,
                display_name=display_name,
                profile_image_url=picture_url,
                organization_id=invitation.organization_id,
                platform=PlatformEnum.MOBILE,
            )
            self.session.add(user)

        # Mark invitation as used
        invitation.used_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(user)

        logger.info(f"User {user.id} ({line_user_id}) joined org {invitation.organization_id} via invitation")

        # Generate JWT
        tokens = self._generate_tokens(user.id, user.organization_id, user.display_name or '')

        return {
            'success': True,
            'auth_token': tokens['auth_token'],
            'refresh_token': tokens['refresh_token'],
            'token_type': 'Bearer',
            'expires_in': 86400,
            'user': {
                'id': user.id,
                'email': user.email or '',
                'displayName': user.display_name or display_name,
                'organizationId': user.organization_id,
                'pictureUrl': user.profile_image_url,
            },
        }

    # ==========================================
    # LINE MEMBER MANAGEMENT (desktop Settings)
    # ==========================================

    def list_line_members(self, organization_id: int) -> dict:
        """List all LINE-linked users in an organization."""
        members = (
            self.session.query(UserLocation)
            .filter(
                UserLocation.organization_id == organization_id,
                UserLocation.line_user_id.isnot(None),
                UserLocation.is_active == True,
            )
            .order_by(UserLocation.created_date.desc())
            .all()
        )
        return {
            'success': True,
            'members': [
                {
                    'id': m.id,
                    'line_user_id': m.line_user_id,
                    'display_name': m.display_name,
                    'email': m.email,
                    'profile_image_url': m.profile_image_url,
                    'created_date': str(m.created_date) if m.created_date else None,
                }
                for m in members
            ],
        }

    def remove_line_member(self, organization_id: int, member_id: int) -> dict:
        """Remove a LINE user from the organization (unlink, not delete)."""
        user = (
            self.session.query(UserLocation)
            .filter(
                UserLocation.id == member_id,
                UserLocation.organization_id == organization_id,
                UserLocation.line_user_id.isnot(None),
                UserLocation.is_active == True,
            )
            .first()
        )
        if not user:
            raise ValueError('Member not found')

        # Unlink from org (keep user record)
        user.organization_id = None
        self.session.commit()

        return {'success': True, 'message': f'Removed {user.display_name or user.line_user_id} from organization'}

    def list_invitations(self, organization_id: int) -> dict:
        """List all invitations for an organization."""
        invitations = (
            self.session.query(UserInvitation)
            .filter(
                UserInvitation.organization_id == organization_id,
                UserInvitation.is_active == True,
            )
            .order_by(UserInvitation.created_date.desc())
            .limit(20)
            .all()
        )
        liff_base = os.environ.get('LIFF_BASE_URL', 'https://esg.gepp.me')
        return {
            'success': True,
            'invitations': [
                {
                    'id': inv.id,
                    'token': inv.invitation_token,
                    'url': f'{liff_base}/liff?invite={inv.invitation_token}',
                    'expires_at': str(inv.expires_at) if inv.expires_at else None,
                    'used_at': str(inv.used_at) if inv.used_at else None,
                    'created_date': str(inv.created_date) if inv.created_date else None,
                }
                for inv in invitations
            ],
        }

    # ==========================================
    # INTERNAL
    # ==========================================

    def _get_line_profile(self, access_token: str) -> dict | None:
        try:
            req = urllib.request.Request(
                LINE_PROFILE_URL,
                headers={'Authorization': f'Bearer {access_token}'},
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    return json.loads(response.read().decode('utf-8'))
            return None
        except urllib.error.HTTPError as e:
            logger.warning(f"LINE profile fetch failed: {e.code} {e.reason}")
            return None
        except Exception as e:
            logger.error(f"LINE profile fetch error: {e}")
            return None

    def _generate_tokens(self, user_id: int, organization_id: int | None, email: str) -> dict:
        now = datetime.now(timezone.utc)
        auth_payload = {
            'user_id': user_id, 'organization_id': organization_id,
            'email': email, 'type': 'auth',
            'exp': now + timedelta(days=JWT_AUTH_EXPIRY_DAYS), 'iat': now,
        }
        refresh_payload = {
            'user_id': user_id, 'organization_id': organization_id,
            'email': email, 'type': 'refresh',
            'exp': now + timedelta(days=JWT_REFRESH_EXPIRY_DAYS), 'iat': now,
        }
        return {
            'auth_token': jwt.encode(auth_payload, JWT_SECRET, algorithm=JWT_ALGORITHM),
            'refresh_token': jwt.encode(refresh_payload, JWT_SECRET, algorithm=JWT_ALGORITHM),
        }

    def _generate_invite_token(self, length: int = 32) -> str:
        chars = string.ascii_letters + string.digits
        return ''.join(secrets.choice(chars) for _ in range(length))
