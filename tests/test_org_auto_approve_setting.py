"""Org-wide "auto-approve scale transactions" setting on the customer settings screen.

The toggle sits next to two PER-USER toggles but is org-wide and owner-only, so the
two things worth pinning down are: (1) a body carrying only this key still takes the
scalar-update branch instead of the "create a new setup version" branch, and (2) a
non-owner cannot flip it even though they can reach the same screen.
"""

import pytest

from GEPPPlatform.exceptions import (
    BadRequestException,
    UnauthorizedException,
    ValidationException,  # noqa: F401  raised inside the handler, asserted via BadRequest
)
from GEPPPlatform.services.cores.organizations import organization_handlers as handlers
from GEPPPlatform.services.cores.organizations.dto.organization_requests import (
    UpdateOrganizationSetupRequest,
)

OWNER_ID = 5
MEMBER_ID = 9


class _FakeOrg:
    id = 10
    owner_id = OWNER_ID
    auto_approve_scale_transactions = False


class _FakeOrgService:
    def __init__(self):
        self.org = _FakeOrg()
        self.calls = []

    def get_user_organization(self, user_id):
        return self.org

    def get_organization_setup(self, organization_id):
        # Shape the response DTO requires (id / organization_id / version / is_active).
        return {
            'id': 1,
            'organization_id': organization_id,
            'version': '1.0',
            'is_active': True,
        }

    def get_organization_by_id(self, organization_id):
        return self.org

    def get_user_location_settings(self, user_location_id):
        return {'input_destination': False, 'show_all_location_options': True}

    def upsert_user_location_settings(self, **kwargs):
        self.calls.append(('user_settings', kwargs))
        return {'input_destination': False, 'show_all_location_options': True}

    def set_auto_approve_scale_transactions(self, organization_id, enabled, acting_user_id=None):
        self.calls.append(('set_flag', organization_id, enabled, acting_user_id))
        self.org.auto_approve_scale_transactions = enabled
        return enabled


def _update(user_id, body):
    return handlers.handle_update_organization_setup(_FakeOrgService(), user_id, body, headers={})


def test_flag_alone_routes_to_scalar_update_not_a_new_version():
    """Without this the body falls through to the tree branch and validation rejects it."""
    request = UpdateOrganizationSetupRequest.from_dict({'auto_approve_scale_transactions': True})
    body = {'auto_approve_scale_transactions': True}

    assert request.has_level_names_only(body) is True
    assert request.validate(allow_level_names_only=True) == []


def test_owner_can_enable_and_response_reflects_it():
    service = _FakeOrgService()
    result = handlers.handle_update_organization_setup(
        service, OWNER_ID, {'auto_approve_scale_transactions': True}, headers={}
    )

    assert ('set_flag', 10, True, OWNER_ID) in service.calls
    assert result['success'] is True
    # Must survive the response DTO, which is a fixed allowlist — a field it doesn't
    # know about is dropped silently and the screen would render a stale toggle.
    payload = result['data']
    assert payload['auto_approve_scale_transactions'] is True
    assert payload['auto_approve_scale_transactions_editable'] is True


def test_non_owner_is_refused():
    """A data-entry user must not be able to switch off the review of their own numbers."""
    service = _FakeOrgService()
    with pytest.raises(UnauthorizedException):
        handlers.handle_update_organization_setup(
            service, MEMBER_ID, {'auto_approve_scale_transactions': True}, headers={}
        )

    assert service.calls == []
    assert service.org.auto_approve_scale_transactions is False


def test_non_boolean_is_rejected():
    """ValidationException is converted to BadRequest at the handler boundary."""
    with pytest.raises(BadRequestException):
        _update(OWNER_ID, {'auto_approve_scale_transactions': 'yes'})


def test_per_user_toggles_still_route_to_user_settings():
    """Regression: the neighbouring toggles must stay per-user, not become org-wide."""
    service = _FakeOrgService()
    handlers.handle_update_organization_setup(
        service, MEMBER_ID, {'input_destination': True}, headers={}
    )

    kinds = [c[0] for c in service.calls]
    assert 'user_settings' in kinds
    assert 'set_flag' not in kinds
