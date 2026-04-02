"""
LIFF Auth Service - LINE LIFF token validation and user registration (UC 1.1)
"""

import requests
import jwt
import os
from datetime import datetime, timedelta

from GEPPPlatform.models.users.user_related import User


JWT_SECRET = os.environ.get('JWT_SECRET', 'your-secret-key')
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')
JWT_EXPIRY_HOURS = int(os.environ.get('JWT_EXPIRY_HOURS', '24'))

LINE_PROFILE_URL = 'https://api.line.me/v2/profile'


class LiffAuthService:

    def __init__(self, session):
        self.session = session

    def login_with_line(self, line_access_token: str) -> dict:
        """
        Authenticate a user via LINE LIFF access token.
        Creates user if they don't exist yet.

        Returns JWT token and user info.
        """
        profile = self._get_line_profile(line_access_token)
        if not profile:
            raise ValueError('Failed to fetch LINE profile. Please check permissions.')

        line_user_id = profile['userId']
        display_name = profile.get('displayName', '')
        picture_url = profile.get('pictureUrl')

        # Check if user exists
        user = (
            self.session.query(User)
            .filter(User.line_user_id == line_user_id)
            .first()
        )

        if not user:
            # Auto-register new user
            user = User(
                line_user_id=line_user_id,
                display_name=display_name,
                picture_url=picture_url,
            )
            self.session.add(user)
            self.session.commit()
            self.session.refresh(user)

        # Generate JWT
        token = self._generate_jwt(user)

        return {
            'success': True,
            'auth_token': token,
            'user': {
                'id': user.id,
                'display_name': user.display_name,
                'organization_id': getattr(user, 'organization_id', None),
                'picture_url': getattr(user, 'picture_url', None),
            },
        }

    def link_company(self, user_id: int, joining_code: str) -> dict:
        """Link a user to a company via joining code (UC 1.2)."""
        from GEPPPlatform.models.subscriptions.organizations import Organization

        org = (
            self.session.query(Organization)
            .filter(Organization.joining_code == joining_code, Organization.is_active == True)
            .first()
        )
        if not org:
            raise ValueError('Invalid joining code. Please check and try again.')

        user = self.session.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError('User not found.')

        user.organization_id = org.id
        self.session.commit()

        return {
            'success': True,
            'organization_id': org.id,
            'organization_name': getattr(org, 'name', None),
        }

    def _get_line_profile(self, access_token: str) -> dict | None:
        """Fetch LINE user profile using the LIFF access token."""
        try:
            response = requests.get(
                LINE_PROFILE_URL,
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=10,
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception:
            return None

    def _generate_jwt(self, user) -> str:
        """Generate a JWT token for the authenticated user."""
        payload = {
            'user_id': user.id,
            'organization_id': getattr(user, 'organization_id', None),
            'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
            'iat': datetime.utcnow(),
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
