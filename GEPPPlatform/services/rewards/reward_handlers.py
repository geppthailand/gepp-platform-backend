"""
Reward API handlers — routes for admin + public/LIFF endpoints
"""

from typing import Dict, Any
import traceback

from .setup_service import RewardSetupService
from .activity_material_service import ActivityMaterialService
from .activity_type_service import ActivityTypeService
from .cost_report_service import CostReportService
from .campaign_service import CampaignService
from .campaign_claim_service import CampaignClaimService
from .campaign_catalog_service import CampaignCatalogService
from .campaign_droppoint_service import CampaignDroppointService
from .campaign_target_service import CampaignTargetService
from .catalog_service import CatalogService
from .catalog_category_service import CatalogCategoryService
from .stock_service import StockService
from .member_service import MemberService
from .staff_service import StaffService
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

        # --- Phase 2: Conversion Rate (org-level point→baht) ---
        if path == "/api/rewards/setup/conversion-rate" and method == "PUT":
            svc = RewardSetupService(db_session)
            return svc.update_conversion_rate(current_org_id, data)

        # --- Overview ---
        if path == "/api/rewards/overview" and method == "GET":
            svc = OverviewService(db_session)
            return svc.get_stats(current_org_id)

        if path == "/api/rewards/overview/alerts" and method == "GET":
            svc = OverviewService(db_session)
            return svc.get_alerts(current_org_id)

        if path == "/api/rewards/overview/campaigns" and method == "GET":
            svc = OverviewService(db_session)
            return svc.get_campaign_details(current_org_id)

        if path == "/api/rewards/overview/staff-today" and method == "GET":
            svc = OverviewService(db_session)
            return svc.get_staff_today(current_org_id)

        if path == "/api/rewards/overview/trends" and method == "GET":
            svc = OverviewService(db_session)
            months = int(query_params.get("months", 6))
            return svc.get_trends(current_org_id, months=months)

        if path == "/api/rewards/overview/stock-matrix" and method == "GET":
            svc = OverviewService(db_session)
            return svc.get_stock_matrix(current_org_id)

        if path == "/api/rewards/overview/top-members" and method == "GET":
            svc = OverviewService(db_session)
            limit = int(query_params.get("limit", 5))
            return svc.get_top_members(current_org_id, limit=limit)

        # --- Phase 2: Drop Point Breakdown (Material kg / Activity count) ---
        if path == "/api/rewards/overview/dropoint-breakdown" and method == "GET":
            svc = OverviewService(db_session)
            metric = query_params.get("metric", "material")
            campaign_id = query_params.get("campaign_id")
            campaign_id_int = int(campaign_id) if campaign_id else None
            return svc.get_dropoint_breakdown(
                current_org_id, metric=metric, campaign_id=campaign_id_int,
            )

        # --- Phase 2: Activity Types CRUD ---
        if path == "/api/rewards/activity-types" and method == "GET":
            svc = ActivityTypeService(db_session)
            return svc.list(current_org_id)

        if path == "/api/rewards/activity-types" and method == "POST":
            svc = ActivityTypeService(db_session)
            return svc.create(current_org_id, data)

        if path == "/api/rewards/activity-types" and method == "PUT":
            svc = ActivityTypeService(db_session)
            return svc.update(int(data.get("id")), current_org_id, data)

        if path == "/api/rewards/activity-types" and method == "DELETE":
            svc = ActivityTypeService(db_session)
            item_id = data.get("id") or query_params.get("id")
            return svc.delete(int(item_id), current_org_id)

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

        # --- Campaign Lifecycle + Detail ---
        if path == "/api/rewards/campaigns/detail" and method == "GET":
            svc = CampaignService(db_session)
            item_id = query_params.get("id")
            return svc.get_detail(int(item_id), current_org_id)

        if path == "/api/rewards/campaigns/publish" and method == "POST":
            svc = CampaignService(db_session)
            return svc.publish(int(data.get("id")))

        if path == "/api/rewards/campaigns/pause" and method == "POST":
            svc = CampaignService(db_session)
            return svc.pause(int(data.get("id")))

        if path == "/api/rewards/campaigns/resume" and method == "POST":
            svc = CampaignService(db_session)
            return svc.resume(int(data.get("id")))

        if path == "/api/rewards/campaigns/archive" and method == "POST":
            svc = CampaignService(db_session)
            return svc.archive(int(data.get("id")))

        if path == "/api/rewards/campaigns/duplicate" and method == "POST":
            svc = CampaignService(db_session)
            return svc.duplicate(int(data.get("id")), current_org_id)

        if path == "/api/rewards/campaigns/transactions" and method == "GET":
            svc = CampaignService(db_session)
            return svc.list_transactions(
                id=int(query_params.get("id")),
                organization_id=current_org_id,
                ref_type=query_params.get("type"),
                date_from=query_params.get("from"),
                date_to=query_params.get("to"),
                search=query_params.get("search"),
                page=int(query_params.get("page", 1)),
                page_size=int(query_params.get("page_size", 20)),
            )

        if path == "/api/rewards/campaigns/members" and method == "GET":
            svc = CampaignService(db_session)
            return svc.list_members(
                id=int(query_params.get("id")),
                organization_id=current_org_id,
                search=query_params.get("search"),
                sort=query_params.get("sort", "points"),
            )

        if path == "/api/rewards/campaigns/weekly-trend" and method == "GET":
            svc = CampaignService(db_session)
            return svc.get_weekly_trend(
                id=int(query_params.get("id")),
                organization_id=current_org_id,
                weeks=int(query_params.get("weeks", 8)),
            )

        # --- Campaign Targets ---
        if path == "/api/rewards/campaign-targets/eligible-activity-materials" and method == "GET":
            svc = CampaignTargetService(db_session)
            campaign_id = query_params.get("campaign_id")
            return svc.list_eligible_activity_materials(int(campaign_id))

        if path == "/api/rewards/campaign-targets/eligible-main-materials" and method == "GET":
            svc = CampaignTargetService(db_session)
            campaign_id = query_params.get("campaign_id")
            return svc.list_eligible_main_materials(int(campaign_id))

        if path == "/api/rewards/campaign-targets" and method == "GET":
            svc = CampaignTargetService(db_session)
            campaign_id = query_params.get("campaign_id")
            return svc.list(int(campaign_id))

        if path == "/api/rewards/campaign-targets" and method == "POST":
            svc = CampaignTargetService(db_session)
            return svc.create(data)

        if path == "/api/rewards/campaign-targets" and method == "PUT":
            svc = CampaignTargetService(db_session)
            return svc.update(int(data.get("id")), data)

        if path == "/api/rewards/campaign-targets" and method == "DELETE":
            svc = CampaignTargetService(db_session)
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
            return svc.create(
                data,
                organization_id=current_org_id,
                admin_user_id=current_user_id,
            )

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
            return svc.deposit_or_withdraw(data, organization_id=current_org_id)

        if path == "/api/rewards/stocks/assign" and method == "POST":
            svc = StockService(db_session)
            return svc.assign_to_campaign(data, organization_id=current_org_id)

        # --- Catalog Categories ---
        if path == "/api/rewards/catalog-categories" and method == "GET":
            svc = CatalogCategoryService(db_session)
            return svc.list(current_org_id)

        if path == "/api/rewards/catalog-categories" and method == "POST":
            svc = CatalogCategoryService(db_session)
            return svc.create(current_org_id, data)

        if path == "/api/rewards/catalog-categories" and method == "PUT":
            svc = CatalogCategoryService(db_session)
            return svc.update(int(data.get("id")), data)

        if path == "/api/rewards/catalog-categories" and method == "DELETE":
            svc = CatalogCategoryService(db_session)
            item_id = data.get("id") or query_params.get("id")
            return svc.delete(int(item_id))

        # --- Catalog Archive (2-step: check → confirm) ---
        if path == "/api/rewards/catalog/archive" and method == "POST":
            svc = CatalogService(db_session)
            return svc.archive_check(int(data.get("id")), current_org_id)

        if path == "/api/rewards/catalog/archive/confirm" and method == "POST":
            svc = CatalogService(db_session)
            return svc.archive_confirm(
                id=int(data.get("id")),
                organization_id=current_org_id,
                return_to_global=bool(data.get("return_to_global", False)),
                admin_user_id=current_user_id,
            )

        # --- Inventory ---
        if path == "/api/rewards/inventory/kpis" and method == "GET":
            svc = StockService(db_session)
            return svc.get_inventory_kpis(current_org_id)

        # --- Phase 2: Cost Report (full-page destination) ---
        if path == "/api/rewards/inventory/cost-report" and method == "GET":
            svc = CostReportService(db_session)
            return svc.get_report(
                organization_id=current_org_id,
                date_from=query_params.get("date_from"),
                date_to=query_params.get("date_to"),
            )

        if path == "/api/rewards/inventory/summary" and method == "GET":
            svc = StockService(db_session)
            include_archived = query_params.get("include_archived", "true").lower() == "true"
            return svc.get_summary(current_org_id, include_archived=include_archived)

        if path == "/api/rewards/inventory/deposit" and method == "POST":
            svc = StockService(db_session)
            return svc.deposit(data, organization_id=current_org_id, admin_user_id=current_user_id)

        if path == "/api/rewards/inventory/transfer" and method == "POST":
            svc = StockService(db_session)
            return svc.transfer(data, organization_id=current_org_id, admin_user_id=current_user_id)

        if path == "/api/rewards/inventory/ledger" and method == "GET":
            svc = StockService(db_session)
            return svc.list_ledger(current_org_id, dict(query_params))

        if path == "/api/rewards/inventory/lots" and method == "GET":
            svc = StockService(db_session)
            catalog_id = query_params.get("catalog_id")
            if not catalog_id:
                raise BadRequestException("catalog_id is required")
            return svc.compute_lots(int(catalog_id))

        # --- Members ---
        if path == "/api/rewards/members" and method == "GET":
            svc = MemberService(db_session)
            # Accept filter params (all optional)
            filters = {
                "role": query_params.get("role"),
                "is_active": (
                    True if query_params.get("is_active") == "true"
                    else False if query_params.get("is_active") == "false"
                    else None
                ),
                "search": query_params.get("search"),
                "date_from": query_params.get("date_from"),
                "date_to": query_params.get("date_to"),
                "sort": query_params.get("sort"),
                "page": int(query_params.get("page", 1)),
                "page_size": int(query_params.get("page_size", 10)),
            }
            return svc.list_members(current_org_id, filters)

        if path == "/api/rewards/members/detail" and method == "GET":
            svc = MemberService(db_session)
            org_reward_user_id = query_params.get("id")
            return svc.get_detail(int(org_reward_user_id), current_org_id)

        if path == "/api/rewards/members/timeline" and method == "GET":
            svc = MemberService(db_session)
            return svc.get_timeline(
                int(query_params.get("id")),
                current_org_id,
                days=int(query_params.get("days", 30)),
            )

        if path == "/api/rewards/members/role" and method == "PUT":
            svc = MemberService(db_session)
            return svc.update_role(data.get("id"), data.get("role"), current_org_id)

        if path == "/api/rewards/members/status" and method == "PUT":
            svc = MemberService(db_session)
            return svc.toggle_active(data.get("id"), current_org_id)

        if path == "/api/rewards/members/bulk-toggle-active" and method == "POST":
            svc = MemberService(db_session)
            return svc.bulk_toggle_active(
                [int(i) for i in (data.get("ids") or [])],
                bool(data.get("is_active")),
                current_org_id,
            )

        if path == "/api/rewards/members/redemption/confirm" and method == "POST":
            svc = MemberService(db_session)
            return svc.admin_confirm_redemption(
                int(data.get("redemption_id")),
                current_org_id,
                admin_user_id=current_user_id,
            )

        if path == "/api/rewards/members/redemption/cancel" and method == "POST":
            svc = MemberService(db_session)
            return svc.admin_cancel_redemption(
                int(data.get("redemption_id")),
                current_org_id,
                admin_user_id=current_user_id,
                note=data.get("note"),
            )

        # --- Staff ---
        if path == "/api/rewards/staff/kpis" and method == "GET":
            svc = StaffService(db_session)
            return svc.get_kpis(current_org_id)

        if path == "/api/rewards/staff/performance" and method == "GET":
            svc = StaffService(db_session)
            return svc.list_performance(current_org_id)

        if path == "/api/rewards/staff/revoke" and method == "POST":
            svc = StaffService(db_session)
            return svc.revoke_staff(int(data.get("id")), current_org_id)

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
            return svc.create_invite(
                current_org_id,
                current_user_id,
                expiry_hours=data.get("expiry_hours"),
            )

        if path == "/api/rewards/staff-invites/revoke" and method == "POST":
            svc = InviteService(db_session)
            return svc.revoke_invite(int(data.get("id")), current_org_id)

        # ============================================================
        # PUBLIC / LIFF ENDPOINTS
        # All user-facing endpoints resolve reward_user_id server-side
        # from X-Line-User-Id header — never trust client-provided ID.
        # ============================================================

        headers = event.get("headers", {})
        line_user_id = headers.get("x-line-user-id") or headers.get("X-Line-User-Id")

        def _resolve_user() -> int:
            pub_svc = PublicRewardService(db_session)
            return pub_svc.resolve_user_by_line_id(line_user_id)

        def _resolve_staff(organization_id: int) -> int:
            """Resolve the caller's staff org_user.id — ignores client-provided staff_org_user_id."""
            pub_svc = PublicRewardService(db_session)
            return pub_svc.resolve_staff_by_line_id(line_user_id, organization_id)

        if path == "/api/rewards/public/invite/verify" and method == "POST":
            svc = InviteService(db_session)
            return svc.verify_invite(data.get("hash"), _resolve_user())

        if path == "/api/rewards/public/register" and method == "POST":
            svc = PublicRewardService(db_session)
            return svc.register_user(data)

        if path == "/api/rewards/public/profile" and method == "GET":
            svc = PublicRewardService(db_session)
            reward_user_id = _resolve_user()
            org_id = query_params.get("organization_id")
            return svc.get_profile(reward_user_id, int(org_id) if org_id else None)

        if path == "/api/rewards/public/memberships" and method == "GET":
            svc = PublicRewardService(db_session)
            return svc.get_memberships(_resolve_user())

        if path == "/api/rewards/public/verify-staff" and method == "POST":
            svc = PublicRewardService(db_session)
            return svc.verify_staff(_resolve_user(), data.get("droppoint_hash"))

        if path == "/api/rewards/public/claim" and method == "POST":
            # Resolve caller's staff identity from header — ignore client-provided staff_org_user_id
            pub_svc = PublicRewardService(db_session)
            verified_staff_id = pub_svc.resolve_staff_for_campaign(line_user_id, data.get("campaign_id"))
            svc = ClaimService(db_session)
            return svc.claim_points(
                staff_org_user_id=verified_staff_id,
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
            return svc.get_user_organizations(_resolve_user())

        if path == "/api/rewards/public/redeem/campaigns" and method == "GET":
            svc = RedeemService(db_session)
            org_id = query_params.get("organization_id")
            return svc.get_user_campaigns_for_redeem(_resolve_user(), int(org_id))

        if path == "/api/rewards/public/redeem/catalog" and method == "GET":
            svc = RedeemService(db_session)
            campaign_id = query_params.get("campaign_id")
            return svc.get_campaign_catalog_for_redeem(int(campaign_id), _resolve_user())

        if path == "/api/rewards/public/redeem" and method == "POST":
            svc = RedeemService(db_session)
            return svc.submit_redemption(
                reward_user_id=_resolve_user(),
                organization_id=data.get("organization_id"),
                campaign_id=data.get("campaign_id"),
                items=data.get("items", []),
            )

        if path == "/api/rewards/public/redemption-lookup" and method == "GET":
            svc = ConfirmService(db_session)
            return svc.lookup_redemption(
                hash=query_params.get("hash", ""),
            )

        if path == "/api/rewards/public/confirm-redeem" and method == "POST":
            svc = ConfirmService(db_session)
            return svc.confirm_redemption(
                hash=data.get("hash"),
                group_hash=data.get("group_hash"),
                staff_org_user_id=data.get("staff_org_user_id"),
            )

        if path == "/api/rewards/public/reject-redemption" and method == "POST":
            svc = RedeemService(db_session)
            return svc.reject_redemption_by_hash(
                hash=data.get("hash", ""),
                note=data.get("note"),
            )

        if path == "/api/rewards/public/cancel-redemption" and method == "POST":
            svc = RedeemService(db_session)
            return svc.cancel_redemption(
                reward_user_id=_resolve_user(),
                redemption_id=data.get("redemption_id"),
            )

        if path == "/api/rewards/public/point-history" and method == "GET":
            svc = HistoryService(db_session)
            return svc.point_history(
                reward_user_id=_resolve_user(),
                organization_id=int(query_params["organization_id"]) if query_params.get("organization_id") else None,
                campaign_id=int(query_params["campaign_id"]) if query_params.get("campaign_id") else None,
                page=int(query_params.get("page", 1)),
                per_page=int(query_params.get("per_page", 20)),
            )

        if path == "/api/rewards/public/redemption-history" and method == "GET":
            svc = HistoryService(db_session)
            return svc.redemption_history(
                reward_user_id=_resolve_user(),
                organization_id=int(query_params["organization_id"]) if query_params.get("organization_id") else None,
                campaign_id=int(query_params["campaign_id"]) if query_params.get("campaign_id") else None,
                page=int(query_params.get("page", 1)),
                per_page=int(query_params.get("per_page", 20)),
            )

        if path == "/api/rewards/public/staff/claim-history" and method == "GET":
            org_id = int(query_params.get("organization_id"))
            svc = HistoryService(db_session)
            return svc.staff_claim_history(
                staff_org_user_id=_resolve_staff(org_id),
                organization_id=org_id,
                campaign_id=int(query_params["campaign_id"]) if query_params.get("campaign_id") else None,
                page=int(query_params.get("page", 1)),
                per_page=int(query_params.get("per_page", 20)),
            )

        if path == "/api/rewards/public/staff/redemption-history" and method == "GET":
            org_id = int(query_params.get("organization_id"))
            svc = HistoryService(db_session)
            return svc.staff_redemption_history(
                staff_org_user_id=_resolve_staff(org_id),
                organization_id=org_id,
                campaign_id=int(query_params["campaign_id"]) if query_params.get("campaign_id") else None,
                page=int(query_params.get("page", 1)),
                per_page=int(query_params.get("per_page", 20)),
            )

        if path == "/api/rewards/public/staff/daily-stats" and method == "GET":
            org_id = int(query_params.get("organization_id"))
            svc = HistoryService(db_session)
            return svc.get_staff_daily_stats(
                staff_org_user_id=_resolve_staff(org_id),
                organization_id=org_id,
            )

        # No matching route
        raise NotFoundException(f"Route not found: {method} {path}")

    except (APIException, NotFoundException, BadRequestException):
        raise
    except Exception as e:
        print(f"[REWARDS] Error: {str(e)}")
        print(traceback.format_exc())
        raise APIException(f"Internal error: {str(e)}")
