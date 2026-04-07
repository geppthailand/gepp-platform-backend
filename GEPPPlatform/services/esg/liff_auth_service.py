"""
LIFF Auth Service — External platform user authentication.

Uses EsgUser (NOT UserLocation) for LINE/WhatsApp/WeChat users.
Uses EsgExternalInvitationLink for platform-agnostic invitations.
Desktop web users (email/password) remain in UserLocation — untouched.
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

from ...models.esg.esg_users import EsgUser
from ...models.esg.esg_external_invitation_links import EsgExternalInvitationLink

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
        Looks up EsgUser by (platform='line', platform_user_id=LINE_USER_ID).
        Must have organization_id to proceed.
        """
        profile = self._get_line_profile(line_access_token)
        if not profile:
            raise ValueError('Failed to fetch LINE profile. Please check LIFF permissions.')

        line_user_id = profile.get('userId')
        if not line_user_id:
            raise ValueError('LINE profile missing userId')

        display_name = profile.get('displayName', '')

        user = self._find_esg_user('line', line_user_id)

        if not user or not user.organization_id:
            return {
                'success': False,
                'needs_invitation': True,
                'line_user_id': line_user_id,
                'display_name': display_name,
                'message': 'กรุณากด invitation link จากผู้ดูแลองค์กรก่อนเข้าใช้งาน',
            }

        tokens = self._generate_tokens(user.id, user.organization_id, '')
        return {
            'success': True,
            'auth_token': tokens['auth_token'],
            'refresh_token': tokens['refresh_token'],
            'token_type': 'Bearer',
            'expires_in': 86400,
            'user': {
                'id': user.id,
                'email': '',
                'displayName': user.display_name or display_name,
                'organizationId': user.organization_id,
                'pictureUrl': user.profile_image_url,
            },
        }

    # ==========================================
    # INVITATION
    # ==========================================

    def generate_invitation(self, organization_id: int, invited_by_id: int) -> dict:
        """Generate a platform-agnostic invitation link."""
        token = self._generate_token(32)

        invitation = EsgExternalInvitationLink(
            organization_id=organization_id,
            invited_by_id=invited_by_id,
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        self.session.add(invitation)
        self.session.commit()
        self.session.refresh(invitation)

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
        Accept invitation via LINE.
        Creates EsgUser(platform='line') linked to the invitation's org.
        """
        invitation = (
            self.session.query(EsgExternalInvitationLink)
            .filter(
                EsgExternalInvitationLink.token == invitation_token,
                EsgExternalInvitationLink.is_active == True,
            )
            .first()
        )
        if not invitation:
            raise ValueError('Invitation link ไม่ถูกต้องหรือหมดอายุ')
        if invitation.expires_at and invitation.expires_at < datetime.now(timezone.utc):
            raise ValueError('Invitation link หมดอายุแล้ว กรุณาขอลิงก์ใหม่จากผู้ดูแล')
        if invitation.used_at:
            raise ValueError('Invitation link นี้ถูกใช้งานแล้ว')

        profile = self._get_line_profile(line_access_token)
        if not profile:
            raise ValueError('Failed to fetch LINE profile')

        line_user_id = profile.get('userId')
        display_name = profile.get('displayName', '')
        picture_url = profile.get('pictureUrl')

        # Check if this LINE user already exists
        user = self._find_esg_user('line', line_user_id)

        if user and user.organization_id:
            raise ValueError('LINE ID นี้เชื่อมต่อกับองค์กรอื่นอยู่แล้ว กรุณาให้ผู้ดูแลลบออกก่อน')

        if user:
            # Existing user without org — link
            user.organization_id = invitation.organization_id
            if not user.display_name:
                user.display_name = display_name
            if not user.profile_image_url and picture_url:
                user.profile_image_url = picture_url
        else:
            # New user
            user = EsgUser(
                platform='line',
                platform_user_id=line_user_id,
                display_name=display_name,
                profile_image_url=picture_url,
                organization_id=invitation.organization_id,
            )
            self.session.add(user)

        # Mark invitation as used + track who used it
        invitation.used_at = datetime.now(timezone.utc)
        self.session.flush()
        invitation.used_by_esg_user_id = user.id
        invitation.used_by_platform = 'line'
        invitation.used_by_platform_user_id = line_user_id
        invitation.used_by_display_name = display_name
        self.session.commit()
        self.session.refresh(user)

        logger.info(f"EsgUser {user.id} (line:{line_user_id}) joined org {invitation.organization_id}")

        tokens = self._generate_tokens(user.id, user.organization_id, '')
        return {
            'success': True,
            'auth_token': tokens['auth_token'],
            'refresh_token': tokens['refresh_token'],
            'token_type': 'Bearer',
            'expires_in': 86400,
            'user': {
                'id': user.id,
                'email': '',
                'displayName': user.display_name or display_name,
                'organizationId': user.organization_id,
                'pictureUrl': user.profile_image_url,
            },
        }

    # ==========================================
    # MEMBER MANAGEMENT (desktop Settings)
    # ==========================================

    def list_members(self, organization_id: int, platform: str = None) -> dict:
        """List all external platform users in an organization."""
        query = (
            self.session.query(EsgUser)
            .filter(
                EsgUser.organization_id == organization_id,
                EsgUser.is_active == True,
            )
        )
        if platform:
            query = query.filter(EsgUser.platform == platform)

        members = query.order_by(EsgUser.created_date.desc()).all()
        return {
            'success': True,
            'members': [m.to_dict() for m in members],
        }

    def remove_member(self, organization_id: int, member_id: int) -> dict:
        """Remove an external user from the organization (unlink, not delete)."""
        user = (
            self.session.query(EsgUser)
            .filter(
                EsgUser.id == member_id,
                EsgUser.organization_id == organization_id,
                EsgUser.is_active == True,
            )
            .first()
        )
        if not user:
            raise ValueError('Member not found')

        user.organization_id = None
        self.session.commit()
        return {'success': True, 'message': f'Removed {user.display_name or user.platform_user_id}'}

    def list_invitations(self, organization_id: int) -> dict:
        """List all invitation links for an organization."""
        invitations = (
            self.session.query(EsgExternalInvitationLink)
            .filter(
                EsgExternalInvitationLink.organization_id == organization_id,
                EsgExternalInvitationLink.is_active == True,
            )
            .order_by(EsgExternalInvitationLink.created_date.desc())
            .limit(20)
            .all()
        )
        liff_base = os.environ.get('LIFF_BASE_URL', 'https://esg.gepp.me')
        return {
            'success': True,
            'invitations': [
                {
                    **inv.to_dict(),
                    'url': f'{liff_base}/liff?invite={inv.token}',
                }
                for inv in invitations
            ],
        }

    # ==========================================
    # INTERNAL
    # ==========================================

    def _find_esg_user(self, platform: str, platform_user_id: str) -> EsgUser | None:
        return (
            self.session.query(EsgUser)
            .filter(
                EsgUser.platform == platform,
                EsgUser.platform_user_id == platform_user_id,
                EsgUser.is_active == True,
            )
            .first()
        )

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

    def _generate_token(self, length: int = 32) -> str:
        chars = string.ascii_letters + string.digits
        return ''.join(secrets.choice(chars) for _ in range(length))
