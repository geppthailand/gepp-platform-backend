"""
LIFF Auth Service — External platform user authentication.

Uses EsgUser (NOT UserLocation) for LINE/WhatsApp/WeChat users.
Uses EsgExternalInvitationLink for platform-agnostic invitations.
Desktop web users (email/password) remain in UserLocation — untouched.
"""

import json
import urllib.request
import urllib.error
import urllib.parse
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
LINE_VERIFY_URL = 'https://api.line.me/oauth2/v2.1/verify'

# LINE Login channel ID for the ESG LIFF (e.g. 2009993849 from LIFF
# 2009993849-GpYCVVmc). Used to reject access tokens issued by the
# Reward LIFF (or any other channel) that might be sent to the ESG
# /api/auth/liff endpoint by mistake.
#
# IMPORTANT: this is the LINE Login channel ID — the prefix of the LIFF
# ID, NOT the LIFF ID itself. Set via env var so the same code can serve
# multiple ESG channels (dev / prod) without rebuild.
# ESG-prefixed so it doesn't collide with Reward's channel id env.
# Backward compat: also accept the unprefixed LINE_LOGIN_CHANNEL_ID.
ESG_LINE_CHANNEL_ID = (
    os.environ.get('ESG_LINE_LOGIN_CHANNEL_ID')
    or os.environ.get('LINE_LOGIN_CHANNEL_ID', '2009993849')
)


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
        # Reject tokens issued by a different LIFF channel (e.g. Reward
        # LIFF reusing the same browser session against the ESG backend).
        self._assert_esg_channel(line_access_token)

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
        materiality_state = self._get_materiality_state(user.id, user.organization_id)
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
                **materiality_state,
            },
        }

    def _get_materiality_state(self, user_id: int, org_id: int) -> dict:
        """
        Returns the LIFF gate fields the frontend needs on first paint:
          - materialityCompleted: bool
          - enabledScope3Categories: int[]
          - focusMode: 'scope3_only' | 'full_esg'
        Imported locally to avoid a circular dep with esg_handlers.
        Never breaks login: catches all errors.
        """
        try:
            from .materiality_service import MaterialityService
            from . import materiality_config
            mat = MaterialityService(self.session)
            state = mat.get_state(user_id, org_id)
            settings = mat._get_or_create_settings(org_id)
            enabled = list(settings.enabled_scope3_categories or [])
            if not enabled:
                enabled = materiality_config.default_categories_pre_materiality()
            return {
                'materialityCompleted': bool(state.get('completed')),
                'enabledScope3Categories': enabled,
                'focusMode': settings.focus_mode or 'scope3_only',
            }
        except Exception:  # noqa: BLE001 - never break login on this
            logger.exception('Failed to resolve materiality state for LIFF login')
            return {
                'materialityCompleted': False,
                'enabledScope3Categories': [1, 5, 6, 7],
                'focusMode': 'scope3_only',
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

        # Same channel-id check as login — reject tokens from the Reward
        # LIFF (or any other channel) trying to accept an ESG invitation.
        self._assert_esg_channel(line_access_token)

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
        materiality_state = self._get_materiality_state(user.id, user.organization_id)
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
                **materiality_state,
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

    def _verify_access_token_channel(self, access_token: str) -> dict | None:
        """
        Call LINE's verify endpoint to confirm WHICH channel issued the
        access token.

        Returns the LINE response: { "scope", "client_id", "expires_in" }
        where `client_id` is the LINE Login channel ID. Returns None on
        any error so callers can decide whether to fail closed.

        Used by login_with_line + accept_invitation to make sure tokens
        from the Reward LIFF (different channel id) can't authenticate
        into the ESG backend.
        """
        try:
            url = f'{LINE_VERIFY_URL}?access_token={urllib.parse.quote(access_token)}'
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    return json.loads(response.read().decode('utf-8'))
            return None
        except urllib.error.HTTPError as e:
            logger.warning(f"LINE token verify failed: {e.code} {e.reason}")
            return None
        except Exception as e:
            logger.error(f"LINE token verify error: {e}")
            return None

    def _assert_esg_channel(self, access_token: str) -> None:
        """
        Reject login when the access token was issued by a different
        LINE Login channel (e.g. someone reusing a Reward LIFF token
        against the ESG backend). Raises ValueError with a clear,
        user-facing message on mismatch.
        """
        if not ESG_LINE_CHANNEL_ID:
            # Not configured — skip the check rather than fail open
            # silently. Log a loud warning so this is visible in CloudWatch.
            logger.warning(
                'ESG_LINE_LOGIN_CHANNEL_ID is not set — skipping channel '
                'verification. Tokens from any LIFF channel will be accepted.'
            )
            return
        info = self._verify_access_token_channel(access_token)
        if not info:
            # Network / token already invalid — let the downstream profile
            # call surface a more specific error.
            return
        client_id = str(info.get('client_id') or '').strip()
        if client_id and client_id != str(ESG_LINE_CHANNEL_ID):
            logger.warning(
                'Token channel mismatch: got client_id=%s, expected=%s',
                client_id, ESG_LINE_CHANNEL_ID,
            )
            raise ValueError(
                'Access token นี้ออกมาจาก LIFF อื่น (ไม่ใช่ ESG LIFF) '
                'กรุณาเปิดผ่าน ESG LIFF เพื่อเข้าสู่ระบบ'
            )

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
