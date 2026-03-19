"""
Reward API handlers — routes for admin + public/LIFF endpoints
"""

from typing import Dict, Any
import traceback

from .setup_service import RewardSetupService
from .activity_material_service import ActivityMaterialService
from .campaign_service import CampaignService
from .campaign_claim_service import CampaignClaimService
from .campaign_catalog_service import CampaignCatalogService
from .campaign_droppoint_service import CampaignDroppointService
from .catalog_service import CatalogService
from .stock_service import StockService
from .member_service import MemberService
from .droppoint_service import DroppointService
from .overview_service import OverviewService
from .claim_service import ClaimService
from .redeem_service import RedeemService
from .confirm_service import ConfirmService
from .public_service import PublicRewardService
from .history_service import HistoryService
from .invite_service import InviteService

from ...exceptions import (
    APIException,
    NotFoundException,
    BadRequestException,
)


def handle_reward_routes(event: Dict[str, Any], data: Dict[str, Any], **params) -> Dict[str, Any]:
    """Main handler for reward management routes"""
    path = event.get("rawPath", "")
    method = params.get("method", "GET")
    query_params = params.get("query_params", {})

    db_session = params.get("db_session")
    if not db_session:
        raise APIException("Database session not provided")

    current_user = params.get("current_user", {})
    current_user_id = current_user.get("user_id")
    current_org_id = current_user.get("organization_id")

    try:
        # ============================================================
        # ADMIN ENDPOINTS (require auth)
        # ============================================================

        # --- Setup ---
        if path == "/api/rewards/setup" and method == "GET":
            svc = RewardSetupService(db_session)
            return svc.get_setup(current_org_id)

        if path == "/api/rewards/setup" and method == "POST":
            svc = RewardSetupService(db_session)
            return svc.upsert_setup(current_org_id, data)

        # --- Overview ---
        if path == "/api/rewards/overview" and method == "GET":
            svc = OverviewService(db_session)
            return svc.get_stats(current_org_id)

        # --- Activity Materials ---
        if path == "/api/rewards/activity-materials" and method == "GET":
            svc = ActivityMaterialService(db_session)
            return svc.list(current_org_id)

        if path == "/api/rewards/activity-materials" and method == "POST":
            svc = ActivityMaterialService(db_session)
            return svc.create(current_org_id, data)

        if path == "/api/rewards/activity-materials" and method == "PUT":
            svc = ActivityMaterialService(db_session)
            return svc.update(data.get("id"), data)

        if path == "/api/rewards/activity-materials" and method == "DELETE":
            svc = ActivityMaterialService(db_session)
            item_id = data.get("id") or query_params.get("id")
            return svc.delete(int(item_id))

        # --- Campaigns ---
        if path == "/api/rewards/campaigns" and method == "GET":
            svc = CampaignService(db_session)
            return svc.list(current_org_id)

        if path == "/api/rewards/campaigns" and method == "POST":
            svc = CampaignService(db_session)
            return svc.create(current_org_id, data)

        if path == "/api/rewards/campaigns" and method == "PUT":
            svc = CampaignService(db_session)
            return svc.update(data.get("id"), data)

        if path == "/api/rewards/campaigns" and method == "DELETE":
            svc = CampaignService(db_session)
            item_id = data.get("id") or query_params.get("id")
            return svc.delete(int(item_id))

        # --- Campaign Claims ---
        if path == "/api/rewards/campaign-claims" and method == "GET":
            svc = CampaignClaimService(db_session)
            campaign_id = query_params.get("campaign_id")
            return svc.list(int(campaign_id))

        if path == "/api/rewards/campaign-claims" and method == "POST":
            svc = CampaignClaimService(db_session)
            return svc.create(current_org_id, data)

        if path == "/api/rewards/campaign-claims" and method == "PUT":
            svc = CampaignClaimService(db_session)
            return svc.update(data.get("id"), data)

        if path == "/api/rewards/campaign-claims" and method == "DELETE":
            svc = CampaignClaimService(db_session)
            item_id = data.get("id") or query_params.get("id")
            return svc.delete(int(item_id))

        # --- Campaign Catalog ---
        if path == "/api/rewards/campaign-catalog" and method == "GET":
            svc = CampaignCatalogService(db_session)
            campaign_id = query_params.get("campaign_id")
            return svc.list(int(campaign_id))

        if path == "/api/rewards/campaign-catalog" and method == "POST":
            svc = CampaignCatalogService(db_session)
            return svc.create(data)

        if path == "/api/rewards/campaign-catalog" and method == "PUT":
            svc = CampaignCatalogService(db_session)
            return svc.update(data.get("id"), data)

        if path == "/api/rewards/campaign-catalog" and method == "DELETE":
            svc = CampaignCatalogService(db_session)
            item_id = data.get("id") or query_params.get("id")
            return svc.delete(int(item_id))

        # --- Campaign Droppoints ---
        if path == "/api/rewards/campaign-droppoints" and method == "GET":
            svc = CampaignDroppointService(db_session)
            campaign_id = query_params.get("campaign_id")
            return svc.list(int(campaign_id))

        if path == "/api/rewards/campaign-droppoints" and method == "POST":
            svc = CampaignDroppointService(db_session)
            return svc.create(data)

        if path == "/api/rewards/campaign-droppoints" and method == "DELETE":
            svc = CampaignDroppointService(db_session)
            item_id = data.get("id") or query_params.get("id")
            return svc.delete(int(item_id))

        # --- Catalog ---
        if path == "/api/rewards/catalog" and method == "GET":
            svc = CatalogService(db_session)
            return svc.list(current_org_id)

        if path == "/api/rewards/catalog" and method == "POST":
            svc = CatalogService(db_session)
            return svc.create(current_org_id, data)

        if path == "/api/rewards/catalog" and method == "PUT":
            svc = CatalogService(db_session)
            return svc.update(data.get("id"), data)

        if path == "/api/rewards/catalog" and method == "DELETE":
            svc = CatalogService(db_session)
            item_id = data.get("id") or query_params.get("id")
            return svc.delete(int(item_id))

        # --- Stocks ---
        if path == "/api/rewards/stocks" and method == "GET":
            svc = StockService(db_session)
            catalog_id = query_params.get("catalog_id")
            if catalog_id:
                campaign_id = query_params.get("campaign_id")
                return svc.get_ledger(int(catalog_id), int(campaign_id) if campaign_id else None)
            return svc.get_summary(current_org_id)

        if path == "/api/rewards/stocks" and method == "POST":
            svc = StockService(db_session)
            return svc.deposit_or_withdraw(data)

        # --- Members ---
        if path == "/api/rewards/members" and method == "GET":
            svc = MemberService(db_session)
            return svc.list_members(current_org_id)

        if path == "/api/rewards/members/detail" and method == "GET":
            svc = MemberService(db_session)
            org_reward_user_id = query_params.get("id")
            return svc.get_detail(int(org_reward_user_id), current_org_id)

        if path == "/api/rewards/members/role" and method == "PUT":
            svc = MemberService(db_session)
            return svc.update_role(data.get("id"), data.get("role"))

        if path == "/api/rewards/members/status" and method == "PUT":
            svc = MemberService(db_session)
            return svc.toggle_active(data.get("id"))

        # --- Droppoints ---
        if path == "/api/rewards/droppoints" and method == "GET":
            svc = DroppointService(db_session)
            type_filter = query_params.get("type")
            return svc.list(current_org_id, type_filter)

        if path == "/api/rewards/droppoints" and method == "POST":
            svc = DroppointService(db_session)
            return svc.create(current_org_id, data)

        if path == "/api/rewards/droppoints" and method == "PUT":
            svc = DroppointService(db_session)
            return svc.update(data.get("id"), data)

        if path == "/api/rewards/droppoints" and method == "DELETE":
            svc = DroppointService(db_session)
            item_id = data.get("id") or query_params.get("id")
            return svc.delete(int(item_id))

        # --- Staff Invites ---
        if path == "/api/rewards/staff-invites" and method == "GET":
            svc = InviteService(db_session)
            return svc.list_invites(current_org_id)

        if path == "/api/rewards/staff-invites" and method == "POST":
            svc = InviteService(db_session)
            return svc.create_invite(current_org_id, current_user_id)

        # ============================================================
        # PUBLIC / LIFF ENDPOINTS
        # ============================================================

        if path == "/api/rewards/public/invite/verify" and method == "POST":
            svc = InviteService(db_session)
            return svc.verify_invite(data.get("hash"), data.get("reward_user_id"))

        if path == "/api/rewards/public/register" and method == "POST":
            svc = PublicRewardService(db_session)
            return svc.register_user(data)

        if path == "/api/rewards/public/profile" and method == "GET":
            svc = PublicRewardService(db_session)
            reward_user_id = query_params.get("reward_user_id")
            org_id = query_params.get("organization_id")
            return svc.get_profile(int(reward_user_id), int(org_id) if org_id else None)

        if path == "/api/rewards/public/verify-staff" and method == "POST":
            svc = PublicRewardService(db_session)
            return svc.verify_staff(data.get("reward_user_id"), data.get("droppoint_hash"))

        if path == "/api/rewards/public/claim" and method == "POST":
            svc = ClaimService(db_session)
            return svc.claim_points(
                staff_org_user_id=data.get("staff_org_user_id"),
                reward_user_id=data.get("reward_user_id"),
                campaign_id=data.get("campaign_id"),
                items=data.get("items", []),
                droppoint_id=data.get("droppoint_id"),
                image_ids=data.get("image_ids"),
            )

        if path == "/api/rewards/public/campaigns" and method == "GET":
            svc = CampaignService(db_session)
            org_id = query_params.get("organization_id")
            return svc.list(int(org_id))

        if path == "/api/rewards/public/campaign-claims" and method == "GET":
            svc = CampaignClaimService(db_session)
            campaign_id = query_params.get("campaign_id")
            return svc.list(int(campaign_id))

        if path == "/api/rewards/public/redeem/orgs" and method == "GET":
            svc = RedeemService(db_session)
            reward_user_id = query_params.get("reward_user_id")
            return svc.get_user_organizations(int(reward_user_id))

        if path == "/api/rewards/public/redeem/campaigns" and method == "GET":
            svc = RedeemService(db_session)
            reward_user_id = query_params.get("reward_user_id")
            org_id = query_params.get("organization_id")
            return svc.get_user_campaigns_for_redeem(int(reward_user_id), int(org_id))

        if path == "/api/rewards/public/redeem/catalog" and method == "GET":
            svc = RedeemService(db_session)
            campaign_id = query_params.get("campaign_id")
            reward_user_id = query_params.get("reward_user_id")
            return svc.get_campaign_catalog_for_redeem(int(campaign_id), int(reward_user_id))

        if path == "/api/rewards/public/redeem" and method == "POST":
            svc = RedeemService(db_session)
            return svc.submit_redemption(
                reward_user_id=data.get("reward_user_id"),
                organization_id=data.get("organization_id"),
                campaign_id=data.get("campaign_id"),
                items=data.get("items", []),
            )

        if path == "/api/rewards/public/confirm-redeem" and method == "POST":
            svc = ConfirmService(db_session)
            return svc.confirm_redemption(
                hash=data.get("hash"),
                group_hash=data.get("group_hash"),
                staff_org_user_id=data.get("staff_org_user_id"),
            )

        if path == "/api/rewards/public/point-history" and method == "GET":
            svc = HistoryService(db_session)
            return svc.point_history(
                reward_user_id=int(query_params.get("reward_user_id")),
                organization_id=int(query_params["organization_id"]) if query_params.get("organization_id") else None,
                campaign_id=int(query_params["campaign_id"]) if query_params.get("campaign_id") else None,
                page=int(query_params.get("page", 1)),
                per_page=int(query_params.get("per_page", 20)),
            )

        if path == "/api/rewards/public/redemption-history" and method == "GET":
            svc = HistoryService(db_session)
            return svc.redemption_history(
                reward_user_id=int(query_params.get("reward_user_id")),
                organization_id=int(query_params["organization_id"]) if query_params.get("organization_id") else None,
                campaign_id=int(query_params["campaign_id"]) if query_params.get("campaign_id") else None,
                page=int(query_params.get("page", 1)),
                per_page=int(query_params.get("per_page", 20)),
            )

        if path == "/api/rewards/public/staff/claim-history" and method == "GET":
            svc = HistoryService(db_session)
            return svc.staff_claim_history(
                staff_org_user_id=int(query_params.get("staff_org_user_id")),
                organization_id=int(query_params.get("organization_id")),
                campaign_id=int(query_params["campaign_id"]) if query_params.get("campaign_id") else None,
                page=int(query_params.get("page", 1)),
                per_page=int(query_params.get("per_page", 20)),
            )

        if path == "/api/rewards/public/staff/redemption-history" and method == "GET":
            svc = HistoryService(db_session)
            return svc.staff_redemption_history(
                staff_org_user_id=int(query_params.get("staff_org_user_id")),
                organization_id=int(query_params.get("organization_id")),
                campaign_id=int(query_params["campaign_id"]) if query_params.get("campaign_id") else None,
                page=int(query_params.get("page", 1)),
                per_page=int(query_params.get("per_page", 20)),
            )

        if path == "/api/rewards/public/staff/daily-stats" and method == "GET":
            svc = HistoryService(db_session)
            return svc.get_staff_daily_stats(
                staff_org_user_id=int(query_params.get("staff_org_user_id")),
                organization_id=int(query_params.get("organization_id")),
            )

        # No matching route
        raise NotFoundException(f"Route not found: {method} {path}")

    except (APIException, NotFoundException, BadRequestException):
        raise
    except Exception as e:
        print(f"[REWARDS] Error: {str(e)}")
        print(traceback.format_exc())
        raise APIException(f"Internal error: {str(e)}")
