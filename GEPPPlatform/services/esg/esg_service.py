"""
ESG Service — CRUD for settings, documents, org setup, platform bindings, data hierarchy, extractions, completeness
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_, distinct, case, String
from datetime import datetime, date
from decimal import Decimal
import logging

from ...models.esg.settings import EsgOrganizationSettings
from ...models.esg.documents import EsgDocument
from ...models.esg.organization_setup import EsgOrganizationSetup
from ...models.esg.platform_binding import EsgExternalPlatformBinding
from ...models.esg.data_hierarchy import EsgDataCategory, EsgDataSubcategory, EsgDatapoint
from ...models.esg.data_extraction import EsgOrganizationDataExtraction
from ...models.esg.records import EsgRecord

logger = logging.getLogger(__name__)


class EsgService:
    """ESG business logic service"""

    def __init__(self, db: Session):
        self.db = db

    # ========== SETTINGS ==========

    def get_settings(self, organization_id: int) -> Dict[str, Any]:
        """Get or create ESG settings for organization"""
        settings = self.db.query(EsgOrganizationSettings).filter(
            EsgOrganizationSettings.organization_id == organization_id,
            EsgOrganizationSettings.is_active == True
        ).first()

        if not settings:
            # Create default settings
            settings = EsgOrganizationSettings(organization_id=organization_id)
            self.db.add(settings)
            self.db.flush()

        return {'success': True, 'settings': settings.to_dict()}

    def update_settings(self, organization_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update ESG settings for organization"""
        settings = self.db.query(EsgOrganizationSettings).filter(
            EsgOrganizationSettings.organization_id == organization_id,
            EsgOrganizationSettings.is_active == True
        ).first()

        if not settings:
            settings = EsgOrganizationSettings(organization_id=organization_id)
            self.db.add(settings)

        # Update fields
        updatable_fields = [
            'reporting_year', 'methodology', 'organizational_boundary',
            'base_year', 'reduction_target_percent', 'reduction_target_year',
            'line_channel_id', 'line_channel_secret', 'line_channel_token',
            'line_webhook_url', 'line_rich_menu_id'
        ]
        for field in updatable_fields:
            if field in data and data[field] is not None:
                setattr(settings, field, data[field])

        self.db.flush()
        return {'success': True, 'message': 'Settings updated', 'settings': settings.to_dict()}

    # ========== DOCUMENTS ==========

    def create_document(self, organization_id: int, data: Dict[str, Any], uploaded_by_id: int = None) -> Dict[str, Any]:
        """Create a document record"""
        doc = EsgDocument(
            organization_id=organization_id,
            file_name=data['file_name'],
            file_url=data['file_url'],
            file_type=data.get('file_type'),
            file_size_bytes=data.get('file_size_bytes'),
            esg_category=data.get('esg_category'),
            esg_subcategory=data.get('esg_subcategory'),
            document_type=data.get('document_type'),
            reporting_year=data.get('reporting_year'),
            source=data.get('source', 'upload'),
            uploaded_by_id=uploaded_by_id,
            notes=data.get('notes'),
            ai_classification_status='pending',
        )
        self.db.add(doc)
        self.db.flush()
        return {'success': True, 'message': 'Document created', 'document': doc.to_dict()}

    def list_documents(
        self, organization_id: int,
        page: int = 1, page_size: int = 20,
        esg_category: str = None, document_type: str = None,
        ai_status: str = None, source: str = None
    ) -> Dict[str, Any]:
        """List documents with filtering"""
        query = self.db.query(EsgDocument).filter(
            EsgDocument.organization_id == organization_id,
            EsgDocument.is_active == True,
            EsgDocument.deleted_date.is_(None)
        )

        if esg_category:
            query = query.filter(EsgDocument.esg_category == esg_category)
        if document_type:
            query = query.filter(EsgDocument.document_type == document_type)
        if ai_status:
            query = query.filter(EsgDocument.ai_classification_status == ai_status)
        if source:
            query = query.filter(EsgDocument.source == source)

        total = query.count()
        docs = query.order_by(EsgDocument.created_date.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()

        return {
            'success': True,
            'documents': [d.to_dict() for d in docs],
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total,
                'total_pages': (total + page_size - 1) // page_size
            }
        }

    def get_document(self, document_id: int, organization_id: int) -> Dict[str, Any]:
        """Get a single document"""
        doc = self.db.query(EsgDocument).filter(
            EsgDocument.id == document_id,
            EsgDocument.organization_id == organization_id,
            EsgDocument.is_active == True
        ).first()

        if not doc:
            return {'success': False, 'message': 'Document not found'}
        return {'success': True, 'document': doc.to_dict()}

    # ========== ORG SETUP ==========

    def get_org_setup(self, organization_id: int) -> Dict[str, Any]:
        """Get or create ESG organization setup"""
        setup = self.db.query(EsgOrganizationSetup).filter(
            EsgOrganizationSetup.organization_id == organization_id,
            EsgOrganizationSetup.is_active == True
        ).first()

        if not setup:
            setup = EsgOrganizationSetup(organization_id=organization_id)
            self.db.add(setup)
            self.db.flush()

        return {'success': True, 'org_setup': setup.to_dict()}

    def update_org_setup(self, organization_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update ESG organization setup"""
        setup = self.db.query(EsgOrganizationSetup).filter(
            EsgOrganizationSetup.organization_id == organization_id,
            EsgOrganizationSetup.is_active == True
        ).first()

        if not setup:
            setup = EsgOrganizationSetup(organization_id=organization_id)
            self.db.add(setup)

        updatable = [
            'industry_sector', 'employee_count', 'revenue_currency',
            'annual_revenue', 'reporting_framework', 'fiscal_year_start',
            'auto_extract_enabled', 'notification_enabled'
        ]
        for field in updatable:
            if field in data and data[field] is not None:
                setattr(setup, field, data[field])

        self.db.flush()
        return {'success': True, 'message': 'Organization setup updated', 'org_setup': setup.to_dict()}

    # ========== PLATFORM BINDINGS ==========

    def list_platform_bindings(self, organization_id: int) -> Dict[str, Any]:
        """List platform bindings for an organization"""
        bindings = self.db.query(EsgExternalPlatformBinding).filter(
            EsgExternalPlatformBinding.organization_id == organization_id,
            EsgExternalPlatformBinding.is_active == True
        ).all()
        return {'success': True, 'platform_bindings': [b.to_dict() for b in bindings]}

    def create_platform_binding(self, organization_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a platform binding"""
        channel = data.get('channel')
        if not channel:
            return {'success': False, 'message': 'channel is required'}

        # Check for existing binding
        existing = self.db.query(EsgExternalPlatformBinding).filter(
            EsgExternalPlatformBinding.organization_id == organization_id,
            EsgExternalPlatformBinding.channel == channel,
            EsgExternalPlatformBinding.is_active == True
        ).first()

        if existing:
            return {'success': False, 'message': f'A {channel} binding already exists for this organization'}

        binding = EsgExternalPlatformBinding(
            organization_id=organization_id,
            channel=channel,
            auth_json=data.get('auth_json', {}),
            authorized_groups=data.get('authorized_groups', []),
        )
        self.db.add(binding)
        self.db.flush()
        return {'success': True, 'message': 'Platform binding created', 'platform_binding': binding.to_dict()}

    def update_platform_binding(self, binding_id: int, organization_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a platform binding"""
        binding = self.db.query(EsgExternalPlatformBinding).filter(
            EsgExternalPlatformBinding.id == binding_id,
            EsgExternalPlatformBinding.organization_id == organization_id,
            EsgExternalPlatformBinding.is_active == True
        ).first()

        if not binding:
            return {'success': False, 'message': 'Platform binding not found'}

        if 'auth_json' in data:
            binding.auth_json = data['auth_json']
        if 'authorized_groups' in data:
            binding.authorized_groups = data['authorized_groups']

        self.db.flush()
        return {'success': True, 'message': 'Platform binding updated', 'platform_binding': binding.to_dict()}

    def add_authorized_group(self, binding_id: int, organization_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a group to authorized_groups (pending state)"""
        binding = self.db.query(EsgExternalPlatformBinding).filter(
            EsgExternalPlatformBinding.id == binding_id,
            EsgExternalPlatformBinding.organization_id == organization_id,
            EsgExternalPlatformBinding.is_active == True
        ).first()

        if not binding:
            return {'success': False, 'message': 'Platform binding not found'}

        groups = list(binding.authorized_groups or [])
        group_name = data.get('group_name', '')

        groups.append({
            'group_id': None,
            'group_name': group_name,
            'status': 'pending',
            'added_at': datetime.utcnow().isoformat(),
        })

        binding.authorized_groups = groups
        self.db.flush()
        return {'success': True, 'message': 'Group added (pending pairing)', 'platform_binding': binding.to_dict()}

    def remove_authorized_group(self, binding_id: int, organization_id: int, group_id: str) -> Dict[str, Any]:
        """Remove a group from authorized_groups"""
        binding = self.db.query(EsgExternalPlatformBinding).filter(
            EsgExternalPlatformBinding.id == binding_id,
            EsgExternalPlatformBinding.organization_id == organization_id,
            EsgExternalPlatformBinding.is_active == True
        ).first()

        if not binding:
            return {'success': False, 'message': 'Platform binding not found'}

        groups = [g for g in (binding.authorized_groups or []) if g.get('group_id') != group_id]
        binding.authorized_groups = groups
        self.db.flush()
        return {'success': True, 'message': 'Group removed', 'platform_binding': binding.to_dict()}

    # ========== DATA HIERARCHY ==========

    def list_categories(self, pillar: str = None) -> Dict[str, Any]:
        """List ESG data categories"""
        query = self.db.query(EsgDataCategory).filter(
            EsgDataCategory.is_active == True,
            EsgDataCategory.deleted_date.is_(None)
        )
        if pillar:
            query = query.filter(EsgDataCategory.pillar == pillar)
        cats = query.order_by(EsgDataCategory.pillar, EsgDataCategory.sort_order).all()
        return {'success': True, 'categories': [c.to_dict() for c in cats]}

    def list_subcategories(self, category_id: int = None, pillar: str = None) -> Dict[str, Any]:
        """List ESG data subcategories"""
        query = self.db.query(EsgDataSubcategory).filter(
            EsgDataSubcategory.is_active == True,
            EsgDataSubcategory.deleted_date.is_(None)
        )
        if category_id:
            query = query.filter(EsgDataSubcategory.esg_data_category_id == category_id)
        if pillar:
            query = query.filter(EsgDataSubcategory.pillar == pillar)
        subs = query.order_by(EsgDataSubcategory.sort_order).all()
        return {'success': True, 'subcategories': [s.to_dict() for s in subs]}

    def list_datapoints(self, subcategory_id: int = None, pillar: str = None) -> Dict[str, Any]:
        """List ESG datapoints"""
        query = self.db.query(EsgDatapoint).filter(
            EsgDatapoint.is_active == True,
            EsgDatapoint.deleted_date.is_(None)
        )
        if subcategory_id:
            query = query.filter(EsgDatapoint.esg_data_subcategory_id == subcategory_id)
        if pillar:
            query = query.filter(EsgDatapoint.pillar == pillar)
        dps = query.order_by(EsgDatapoint.sort_order).all()
        return {'success': True, 'datapoints': [d.to_dict() for d in dps]}

    # ========== EXTRACTIONS ==========

    def list_extractions(self, organization_id: int, page: int = 1, page_size: int = 20,
                         channel: str = None, status: str = None) -> Dict[str, Any]:
        """List data extractions for an organization"""
        query = self.db.query(EsgOrganizationDataExtraction).filter(
            EsgOrganizationDataExtraction.organization_id == organization_id,
            EsgOrganizationDataExtraction.is_active == True
        )
        if channel:
            query = query.filter(EsgOrganizationDataExtraction.channel == channel)
        if status:
            query = query.filter(EsgOrganizationDataExtraction.processing_status == status)

        total = query.count()
        extractions = query.order_by(EsgOrganizationDataExtraction.created_date.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()

        return {
            'success': True,
            'extractions': [e.to_dict() for e in extractions],
            'pagination': {'page': page, 'page_size': page_size, 'total': total, 'total_pages': (total + page_size - 1) // page_size}
        }

    def get_extraction(self, extraction_id: int, organization_id: int) -> Dict[str, Any]:
        """Get a single extraction record"""
        extraction = self.db.query(EsgOrganizationDataExtraction).filter(
            EsgOrganizationDataExtraction.id == extraction_id,
            EsgOrganizationDataExtraction.organization_id == organization_id,
            EsgOrganizationDataExtraction.is_active == True
        ).first()

        if not extraction:
            return {'success': False, 'message': 'Extraction not found'}
        return {'success': True, 'extraction': extraction.to_dict()}

    # ========== DATA COMPLETENESS ==========

    def get_data_completeness(self, organization_id: int) -> Dict[str, Any]:
        """Calculate data completeness across ESG hierarchy"""
        # Load full hierarchy
        categories = self.db.query(EsgDataCategory).filter(
            EsgDataCategory.is_active == True,
            EsgDataCategory.deleted_date.is_(None)
        ).order_by(EsgDataCategory.pillar, EsgDataCategory.sort_order).all()

        subcategories = self.db.query(EsgDataSubcategory).filter(
            EsgDataSubcategory.is_active == True,
            EsgDataSubcategory.deleted_date.is_(None)
        ).order_by(EsgDataSubcategory.sort_order).all()

        datapoints = self.db.query(EsgDatapoint).filter(
            EsgDatapoint.is_active == True,
            EsgDatapoint.deleted_date.is_(None)
        ).order_by(EsgDatapoint.sort_order).all()

        # Get all filled datapoint IDs for this org
        extractions = self.db.query(EsgOrganizationDataExtraction).filter(
            EsgOrganizationDataExtraction.organization_id == organization_id,
            EsgOrganizationDataExtraction.processing_status == 'completed',
            EsgOrganizationDataExtraction.is_active == True
        ).all()

        filled_dp_ids = set()
        for ext in extractions:
            for match in (ext.datapoint_matches or []):
                dp_id = match.get('datapoint_id')
                if dp_id:
                    filled_dp_ids.add(dp_id)

        # Build hierarchy with completeness
        subcat_map = {}
        for sc in subcategories:
            subcat_map.setdefault(sc.esg_data_category_id, []).append(sc)

        dp_map = {}
        for dp in datapoints:
            dp_map.setdefault(dp.esg_data_subcategory_id, []).append(dp)

        pillar_data = {}
        for cat in categories:
            pillar = cat.pillar
            if pillar not in pillar_data:
                pillar_data[pillar] = {'pillar': pillar, 'name': {'E': 'Environment', 'S': 'Social', 'G': 'Governance'}.get(pillar, pillar), 'categories': [], 'total_dp': 0, 'filled_dp': 0}

            cat_subcats = subcat_map.get(cat.id, [])
            cat_total = 0
            cat_filled = 0
            subcat_list = []

            for sc in cat_subcats:
                sc_dps = dp_map.get(sc.id, [])
                sc_total = len(sc_dps)
                sc_filled = sum(1 for d in sc_dps if d.id in filled_dp_ids)

                dp_statuses = [{
                    'id': d.id, 'name': d.name, 'unit': d.unit,
                    'has_data': d.id in filled_dp_ids,
                } for d in sc_dps]

                subcat_list.append({
                    'id': sc.id, 'name': sc.name,
                    'score': round(sc_filled / sc_total * 100, 1) if sc_total > 0 else 0,
                    'total_datapoints': sc_total, 'filled_datapoints': sc_filled,
                    'datapoints': dp_statuses,
                })

                cat_total += sc_total
                cat_filled += sc_filled

            pillar_data[pillar]['categories'].append({
                'id': cat.id, 'name': cat.name,
                'score': round(cat_filled / cat_total * 100, 1) if cat_total > 0 else 0,
                'total_datapoints': cat_total, 'filled_datapoints': cat_filled,
                'subcategories': subcat_list,
            })
            pillar_data[pillar]['total_dp'] += cat_total
            pillar_data[pillar]['filled_dp'] += cat_filled

        pillars = []
        total_all = 0
        filled_all = 0
        for p in ['E', 'S', 'G']:
            if p in pillar_data:
                pd = pillar_data[p]
                pd['score'] = round(pd['filled_dp'] / pd['total_dp'] * 100, 1) if pd['total_dp'] > 0 else 0
                pillars.append(pd)
                total_all += pd['total_dp']
                filled_all += pd['filled_dp']

        overall = round(filled_all / total_all * 100, 1) if total_all > 0 else 0

        return {
            'success': True,
            'completeness': {
                'overall_score': overall,
                'total_datapoints': total_all,
                'filled_datapoints': filled_all,
                'pillars': pillars,
            }
        }

    def get_esg_positioning(self, organization_id: int) -> Dict[str, Any]:
        """Get ESG positioning data for radar chart"""
        completeness = self.get_data_completeness(organization_id)
        pillars = completeness.get('completeness', {}).get('pillars', [])

        positioning = {
            'scores': {p['pillar']: p.get('score', 0) for p in pillars},
            'category_scores': {},
        }

        for p in pillars:
            for cat in p.get('categories', []):
                positioning['category_scores'][cat['name']] = cat.get('score', 0)

        return {'success': True, 'positioning': positioning}

    def get_data_warehouse_hierarchy(self, organization_id: int) -> Dict[str, Any]:
        """Full ESG hierarchy with entry counts and completeness for Data Warehouse page."""

        # 1. Load hierarchy (3 queries)
        categories = self.db.query(EsgDataCategory).filter(
            EsgDataCategory.is_active == True,
        ).order_by(EsgDataCategory.pillar, EsgDataCategory.sort_order).all()

        subcategories = self.db.query(EsgDataSubcategory).filter(
            EsgDataSubcategory.is_active == True,
        ).order_by(EsgDataSubcategory.sort_order).all()

        datapoints = self.db.query(EsgDatapoint).filter(
            EsgDatapoint.is_active == True,
        ).order_by(EsgDatapoint.sort_order).all()

        # 2. Per-datapoint stats — derived from each EsgRecord's
        # JSONB datapoints array. A datapoint is "filled" if any
        # record under any category references its id. We also
        # approximate latest_value / latest_unit / total_tco2e by
        # scanning the array (small N — typically <500 records/org).
        all_records_for_dp = (
            self.db.query(
                EsgRecord.id,
                EsgRecord.datapoints,
                EsgRecord.kgco2e,
            )
            .filter(
                EsgRecord.organization_id == organization_id,
                EsgRecord.is_active == True,
            )
            .all()
        )
        entry_data: dict = {}
        for _rec_id, dp_array, kgco2e in all_records_for_dp:
            for d in (dp_array or []):
                dp_id = d.get('datapoint_id')
                if not dp_id:
                    continue
                bucket = entry_data.setdefault(dp_id, {
                    'count': 0,
                    'latest_value': None,
                    'latest_unit': None,
                    'total_tco2e': 0.0,
                })
                bucket['count'] += 1
                v = d.get('value')
                if v is not None:
                    try:
                        bucket['latest_value'] = float(v)
                    except (TypeError, ValueError):
                        pass
                u = d.get('unit')
                if u:
                    bucket['latest_unit'] = u
            if kgco2e is not None:
                # Distribute the record's tco2e equally to each
                # datapoint that has an id (best-effort attribution).
                ids = [d.get('datapoint_id') for d in (dp_array or []) if d.get('datapoint_id')]
                if ids:
                    share = float(kgco2e) / 1000.0 / len(ids)
                    for i in ids:
                        entry_data.setdefault(i, {
                            'count': 0, 'latest_value': None,
                            'latest_unit': None, 'total_tco2e': 0.0,
                        })
                        entry_data[i]['total_tco2e'] += share

        # Total entries (including unlinked)
        total_entries = self.db.query(func.count(EsgRecord.id)).filter(
            EsgRecord.organization_id == organization_id,
            EsgRecord.is_active == True,
        ).scalar() or 0

        # Record + entry counts per category — keyed off
        # `EsgRecord.category_id` directly so we still count entries
        # whose datapoint_id falls outside the canonical hierarchy
        # (mis-classified rows still belong to the right category).
        #
        # A "record" = one **atomic GHG-calculatable item** — one trip,
        # one stay, one invoice line — represented as one
        # `(record_label, evidence_url)` group. This mirrors exactly
        # how `get_scope3_category_records` groups rows in the modal,
        # so the card and the modal always agree on the count.
        cat_entry_rows = (
            self.db.query(
                EsgRecord.id,
                EsgRecord.category_id,
                EsgRecord.evidence_image_url,
                EsgRecord.file_key,
                EsgRecord.datapoints,
            )
            .filter(
                EsgRecord.organization_id == organization_id,
                EsgRecord.is_active == True,
                EsgRecord.category_id.isnot(None),
            )
            .all()
        )
        record_groups_by_cat: dict[int, set[tuple]] = {}
        entry_count_by_cat: dict[int, int] = {}
        for row_id, cat_id, ev_url, file_key, extra in cat_entry_rows:
            entry_count_by_cat[cat_id] = entry_count_by_cat.get(cat_id, 0) + 1
            record_label = ''
            if isinstance(extra, dict):
                record_label = (extra.get('record_label') or '').strip()
            evidence = (ev_url or file_key or '').strip()
            group_key = (record_label or f'entry-{row_id}', evidence)
            record_groups_by_cat.setdefault(cat_id, set()).add(group_key)
        record_count_by_cat: dict[int, int] = {
            cat_id: len(groups) for cat_id, groups in record_groups_by_cat.items()
        }

        # Direct count by EsgRecord.category_id — one row = one record,
        # so this is exact and matches the modal grouping.
        try:
            rec_counts = (
                self.db.query(
                    EsgRecord.category_id,
                    func.count(EsgRecord.id),
                )
                .filter(
                    EsgRecord.organization_id == organization_id,
                    EsgRecord.is_active == True,
                    EsgRecord.category_id.isnot(None),
                )
                .group_by(EsgRecord.category_id)
                .all()
            )
            for cat_id, cnt in rec_counts:
                record_count_by_cat[cat_id] = int(cnt or 0)
        except Exception:
            logger.exception('record_count_by_cat from esg_records failed — using entries fallback')

        # 3. Build maps
        sub_by_cat = {}
        for s in subcategories:
            sub_by_cat.setdefault(s.esg_data_category_id, []).append(s)

        dp_by_sub = {}
        for d in datapoints:
            dp_by_sub.setdefault(d.esg_data_subcategory_id, []).append(d)

        # 4. Assemble nested hierarchy
        pillar_names = {'E': ('Environment', 'สิ่งแวดล้อม'), 'S': ('Social', 'สังคม'), 'G': ('Governance', 'บรรษัทภิบาล')}
        pillar_map = {}

        for cat in categories:
            p = cat.pillar
            if p not in pillar_map:
                pillar_map[p] = {
                    'pillar': p,
                    'name': pillar_names.get(p, (p, p))[0],
                    'name_th': pillar_names.get(p, (p, p))[1],
                    'categories': [],
                    '_dp_total': 0, '_dp_filled': 0, '_entries': 0,
                }

            cat_subs = sub_by_cat.get(cat.id, [])
            cat_dp_total = 0
            cat_dp_filled = 0
            cat_entries = 0
            sub_list = []

            for sc in cat_subs:
                sc_dps = dp_by_sub.get(sc.id, [])
                sc_dp_total = len(sc_dps)
                sc_dp_filled = 0
                sc_entries = 0
                dp_list = []

                for dp in sc_dps:
                    ed = entry_data.get(dp.id, {})
                    ec = ed.get('count', 0)
                    has = ec > 0
                    if has:
                        sc_dp_filled += 1
                    sc_entries += ec

                    dp_list.append({
                        'id': dp.id,
                        'name': dp.name,
                        'name_th': dp.name_th,
                        'description': dp.description,
                        'unit': dp.unit,
                        'data_type': dp.data_type or 'numeric',
                        'entry_count': ec,
                        'latest_value': ed.get('latest_value'),
                        'latest_tco2e': ed.get('total_tco2e'),
                        'has_data': has,
                    })

                pct = round(sc_dp_filled / sc_dp_total * 100, 1) if sc_dp_total > 0 else 0
                sub_list.append({
                    'id': sc.id,
                    'name': sc.name,
                    'name_th': sc.name_th,
                    'datapoint_count': sc_dp_total,
                    'filled_datapoints': sc_dp_filled,
                    'entry_count': sc_entries,
                    'completeness_pct': pct,
                    'datapoints': dp_list,
                })

                cat_dp_total += sc_dp_total
                cat_dp_filled += sc_dp_filled
                cat_entries += sc_entries

            cat_pct = round(cat_dp_filled / cat_dp_total * 100, 1) if cat_dp_total > 0 else 0
            # Direct-by-category counts — these include entries whose
            # datapoint_id sits outside this category's canonical
            # hierarchy (LLM mis-classified onto the wrong datapoint
            # but still tagged the right category_id). Falls back to
            # the walked count when the direct count isn't populated.
            direct_entries = entry_count_by_cat.get(cat.id, cat_entries)
            direct_records = record_count_by_cat.get(cat.id, 0)
            pillar_map[p]['categories'].append({
                'id': cat.id,
                'name': cat.name,
                'name_th': cat.name_th,
                'is_scope3': bool(cat.is_scope3),
                'scope3_category_id': cat.scope3_category_id,
                'subcategory_count': len(cat_subs),
                'datapoint_count': cat_dp_total,
                'filled_datapoints': cat_dp_filled,
                'entry_count': direct_entries,
                'record_count': direct_records,
                'completeness_pct': cat_pct,
                'subcategories': sub_list,
            })

            pillar_map[p]['_dp_total'] += cat_dp_total
            pillar_map[p]['_dp_filled'] += cat_dp_filled
            pillar_map[p]['_entries'] += direct_entries

        # 5. Finalize pillars
        pillars = []
        grand_dp = 0
        grand_filled = 0
        for pk in ['E', 'S', 'G']:
            if pk in pillar_map:
                pm = pillar_map[pk]
                dt = pm.pop('_dp_total')
                df = pm.pop('_dp_filled')
                ec = pm.pop('_entries')
                pm['category_count'] = len(pm['categories'])
                pm['datapoint_count'] = dt
                pm['filled_datapoints'] = df
                pm['entry_count'] = ec
                pm['completeness_pct'] = round(df / dt * 100, 1) if dt > 0 else 0
                pillars.append(pm)
                grand_dp += dt
                grand_filled += df

        return {
            'success': True,
            'pillars': pillars,
            'totals': {
                'categories': len(categories),
                'subcategories': len(subcategories),
                'datapoints': len(datapoints),
                'filled_datapoints': grand_filled,
                'entries': total_entries,
                'completeness_pct': round(grand_filled / grand_dp * 100, 1) if grand_dp > 0 else 0,
            },
        }

    def get_datapoint_records(self, organization_id: int, datapoint_id: int) -> Dict[str, Any]:
        """
        Get entries for a datapoint, structured as:
          documents[] → instances[] → attrs[]
        Each document = one evidence source (invoice image, uploaded file, manual).
        Each instance = one row/line item within that document.
        Each attr = one datapoint value within that instance.
        """
        dp = self.db.query(EsgDatapoint).filter(
            EsgDatapoint.id == datapoint_id, EsgDatapoint.is_active == True,
        ).first()
        if not dp:
            return {'success': False, 'message': 'Datapoint not found'}

        subcat = self.db.query(EsgDataSubcategory).filter(
            EsgDataSubcategory.id == dp.esg_data_subcategory_id,
        ).first()

        # 1. Get all entries for this datapoint
        entries = (
            self.db.query(EsgRecord)
            .filter(
                EsgRecord.organization_id == organization_id,
                EsgRecord.id == datapoint_id,
                EsgRecord.is_active == True,
            )
            .order_by(EsgRecord.entry_date.desc(), EsgRecord.created_date.desc())
            .all()
        )
        if not entries:
            return {
                'success': True, 'datapoint': dp.to_dict(),
                'subcategory': subcat.to_dict() if subcat else None,
                'document_count': 0, 'documents': [],
            }

        # 2. Collect evidence keys and find matching extraction records
        evidence_keys = list(set(
            e.evidence_image_url or e.file_key
            for e in entries if (e.evidence_image_url or e.file_key)
        ))

        # Lookup extraction records by raw_content (= s3 url)
        extraction_map = {}  # evidence_key -> extraction
        if evidence_keys:
            extractions = (
                self.db.query(EsgOrganizationDataExtraction)
                .filter(
                    EsgOrganizationDataExtraction.organization_id == organization_id,
                    EsgOrganizationDataExtraction.raw_content.in_(evidence_keys),
                )
                .all()
            )
            for ext in extractions:
                extraction_map[ext.raw_content] = ext

        # 3. Get ALL sibling entries (same subcategory + same evidence sources)
        all_siblings = []
        if evidence_keys:
            all_siblings = (
                self.db.query(EsgRecord)
                .filter(
                    EsgRecord.organization_id == organization_id,
                    EsgRecord.is_active == True,
                    EsgRecord.subcategory_id == dp.esg_data_subcategory_id,
                    EsgRecord.evidence_image_url.in_(evidence_keys),
                )
                .all()
            )

        # Add manual entries (no evidence)
        manual_entries = [e for e in entries if not e.evidence_image_url and not e.file_key]

        # 4. Datapoint name lookup
        all_dp_ids = list(set(
            [s.datapoint_id for s in all_siblings if s.datapoint_id] +
            [datapoint_id] +
            [e.datapoint_id for e in manual_entries if e.datapoint_id]
        ))
        dp_names = {}
        if all_dp_ids:
            dps_q = self.db.query(EsgDatapoint).filter(EsgDatapoint.id.in_(all_dp_ids)).all()
            dp_names = {d.id: {'name': d.name, 'name_th': d.name_th, 'unit': d.unit, 'data_type': d.data_type} for d in dps_q}

        # 5. Helper: extract record_label from entry
        def _get_label(entry):
            extra = entry.extra_data or {}
            if extra.get('record_label'):
                return extra['record_label']
            if entry.notes and '[' in entry.notes and ']' in entry.notes:
                return entry.notes.split('[')[1].split(']')[0]
            return ''

        # 6. Helper: build attr dict
        def _build_attr(s):
            dp_info = dp_names.get(s.datapoint_id, {})
            return {
                'entry_id': s.id,
                'datapoint_id': s.datapoint_id,
                'datapoint_name': dp_info.get('name', ''),
                'datapoint_name_th': dp_info.get('name_th', ''),
                'value': float(s.value) if s.value else None,
                'unit': s.unit,
                'data_type': dp_info.get('data_type', 'numeric'),
                'is_current': s.datapoint_id == datapoint_id,
                'tco2e': float(s.calculated_tco2e) if s.calculated_tco2e else None,
            }

        # 7. Group: evidence_key → label → [entries]
        #    Level 1: document (evidence_key)
        #    Level 2: instance (record_label within document)
        doc_instance_map = {}  # evidence_key -> {label -> [entries]}
        for s in all_siblings:
            ev_key = s.evidence_image_url or s.file_key
            label = _get_label(s)
            doc_instance_map.setdefault(ev_key, {}).setdefault(label, []).append(s)

        # 8. Build documents → instances → attrs
        documents = []

        # Process evidence-based documents
        target_evidence_keys = list(set(
            e.evidence_image_url or e.file_key for e in entries
            if (e.evidence_image_url or e.file_key)
        ))

        for ev_key in target_evidence_keys:
            if ev_key not in doc_instance_map:
                continue

            ext = extraction_map.get(ev_key)
            refs = (ext.refs or {}) if ext else {}
            dm = {}
            if ext and ext.structured_data:
                dm = ext.structured_data.get('dm', {})

            doc_info = {
                'extraction_id': ext.id if ext else None,
                'evidence_url': ev_key,
                'vendor': refs.get('vendor') or dm.get('vnd', ''),
                'reference': refs.get('reference_number') or dm.get('ref', ''),
                'document_date': refs.get('document_date') or dm.get('dt', ''),
                'source': 'LINE_CHAT' if ext else 'upload',
                'processed_at': str(ext.processed_at) if ext and ext.processed_at else None,
                'instances': [],
            }

            label_groups = doc_instance_map[ev_key]
            for label, siblings in label_groups.items():
                # Only include instances that contain our target datapoint
                has_target = any(s.datapoint_id == datapoint_id for s in siblings)
                if not has_target:
                    continue

                # Deduplicate: one attr per datapoint_id
                seen_dp = set()
                attrs = []
                target_entry = None
                for s in sorted(siblings, key=lambda x: x.datapoint_id or 0):
                    if s.datapoint_id in seen_dp:
                        continue
                    seen_dp.add(s.datapoint_id)
                    attrs.append(_build_attr(s))
                    if s.datapoint_id == datapoint_id:
                        target_entry = s

                if not target_entry:
                    continue

                doc_info['instances'].append({
                    'label': label,
                    'entry_date': str(target_entry.entry_date) if target_entry.entry_date else None,
                    'status': target_entry.status,
                    'this_value': float(target_entry.value) if target_entry.value else None,
                    'this_unit': target_entry.unit,
                    'attrs': attrs,
                })

            if doc_info['instances']:
                documents.append(doc_info)

        # Process manual entries (no evidence) — each is its own document+instance
        for entry in manual_entries:
            documents.append({
                'extraction_id': None,
                'evidence_url': None,
                'vendor': '',
                'reference': '',
                'document_date': str(entry.entry_date) if entry.entry_date else '',
                'source': 'LIFF_MANUAL',
                'processed_at': None,
                'instances': [{
                    'label': _get_label(entry) or 'Manual entry',
                    'entry_date': str(entry.entry_date) if entry.entry_date else None,
                    'status': entry.status,
                    'this_value': float(entry.value) if entry.value else None,
                    'this_unit': entry.unit,
                    'attrs': [_build_attr(entry)],
                }],
            })

        # Sort documents by date desc
        documents.sort(key=lambda d: d.get('document_date') or '', reverse=True)

        return {
            'success': True,
            'datapoint': {
                'id': dp.id, 'name': dp.name, 'name_th': dp.name_th,
                'description': dp.description, 'unit': dp.unit, 'data_type': dp.data_type,
            },
            'subcategory': {
                'id': subcat.id, 'name': subcat.name, 'name_th': subcat.name_th,
            } if subcat else None,
            'document_count': len(documents),
            'instance_count': sum(len(d['instances']) for d in documents),
            'documents': documents,
        }

    def get_scope3_category_records(self, organization_id: int,
                                    scope3_category_id: int) -> Dict[str, Any]:
        """
        Records under a Scope 3 category — used by the Data Warehouse
        modal. Reads from `esg_records` (one row = one atomic record,
        datapoints stored as JSONB array). Falls back to the legacy
        `esg_data_entries` grouping when no record-rows exist yet for
        this org/category (e.g. rows imported before migration 058).

          { columns: [datapoint_name, ...],
            records: [
              { id, record_label, source_doc, fields: {dp_name: '...'},
                kgco2e_total, entry_date,
                ghg_status, ghg_missing_fields, ghg_reason }
            ]
          }
        """
        from ...models.esg.records import EsgRecord

        # 1. Try the new record-centric table first.
        rec_rows = (
            self.db.query(EsgRecord)
            .filter(
                EsgRecord.organization_id == organization_id,
                EsgRecord.is_active == True,
                EsgRecord.scope3_category_id == int(scope3_category_id),
            )
            .order_by(EsgRecord.id.desc())
            .all()
        )

        # esg_data_entries fallback removed — table has been retired.
        return self._scope3_records_from_records_table(rec_rows, scope3_category_id)

    def _scope3_records_from_records_table(
        self, rows, scope3_category_id: int,
    ) -> Dict[str, Any]:
        """
        Build the modal payload from EsgRecord rows. Columns are the
        union of every datapoint identity (most-specific first), in
        first-seen order across the rows.
        """
        column_seen: set[str] = set()
        column_set: list[str] = []
        records_out = []

        # Generic-name blocklist — when the LLM emits the category name
        # as datapoint_name (sparse hierarchy fallback), we don't want
        # that as a column header. The first descriptive tag wins instead.
        from .esg_dashboard_service import SCOPE3_CATEGORY_LABELS
        scope3_label = SCOPE3_CATEGORY_LABELS.get(int(scope3_category_id), {})
        GENERIC_NAMES = {
            (scope3_label.get('en') or '').strip().lower(),
            (scope3_label.get('th') or '').strip().lower(),
            'business travel', 'employee commuting', 'capital goods',
            'purchased goods and services', 'fuel- and energy-related activities',
            'upstream transportation and distribution', 'waste generated in operations',
            'upstream leased assets', 'downstream transportation and distribution',
            'processing of sold products', 'use of sold products',
            'end-of-life treatment of sold products', 'downstream leased assets',
            'franchises', 'investments',
            'value', '', None,
        }

        # Currency codes never make good column headers
        CURRENCY_CODES = {'USD', 'THB', 'EUR', 'GBP', 'JPY', 'CNY', 'SGD',
                          'HKD', 'AUD', 'KRW', 'INR', 'IDR', 'VND', 'PHP', 'MYR'}

        def _humanize(s: str) -> str:
            s = (s or '').strip().replace('_', ' ').replace('-', ' ')
            return ' '.join(w.capitalize() for w in s.split() if w) or s

        def _is_generic(name: str) -> bool:
            return (name or '').strip().lower() in GENERIC_NAMES

        def _resolve_field_name(d: dict) -> str:
            """
            Most-specific identity wins:
              1. tags' last non-currency, non-generic entry  (LLM emits
                 general → specific so reverse iteration finds the
                 most descriptive label, e.g. "base fare", "expressway fee").
              2. canonical_name from EsgDatapoint table (when not generic).
              3. datapoint_name (LLM-reported, when not generic).
              4. 'Value' as last resort.
            """
            tags = d.get('tags') or []
            for t in reversed(tags):
                if not isinstance(t, str):
                    continue
                ts = t.strip()
                if not ts:
                    continue
                if ts.upper() in CURRENCY_CODES:
                    continue
                if _is_generic(ts):
                    continue
                return _humanize(ts)
            cn = (d.get('canonical_name') or '').strip()
            if cn and not _is_generic(cn):
                return _humanize(cn)
            dn = (d.get('datapoint_name') or '').strip()
            if dn and not _is_generic(dn):
                return _humanize(dn)
            return 'Value'

        # Real measurement units only — anything else (field labels
        # the LLM mis-classified into `unit`) gets dropped from the
        # cell render so we don't end up with rows like
        # "Sukhumvit Hotel Bangkok hotel_name".
        REAL_UNITS = {
            'kg', 'g', 't', 'tonne', 'tonnes', 'mg',
            'km', 'm', 'mile', 'miles', 'mi',
            'kwh', 'mwh', 'wh', 'gj', 'mj', 'kj',
            'l', 'litre', 'liter', 'gallon', 'm3', 'ml',
            'sqm', 'm²', 'm2', 'sqft', 'ft²',
            'hour', 'hours', 'h', 'min', 'minute', 'second',
            'night', 'nights', 'day', 'days', 'year', 'years',
            'piece', 'pieces', 'pc', 'pcs', 'unit', 'units',
            'flight', 'flights', 'leg', 'legs', 'trip', 'trips',
            'passenger-km', 'pkm', 'tonne-km', 'tkm', 't-km', 'kg-km',
            'tco2e', 'kgco2e', 'co2e', 'tco2', 'kgco2',
            '%', 'percent',
        }
        REAL_UNITS |= CURRENCY_CODES        # currency units OK
        REAL_UNITS |= {c.lower() for c in CURRENCY_CODES}

        def _clean_unit(u: str) -> str:
            """Drop unit when it isn't actually a measurement unit."""
            us = (u or '').strip()
            if not us:
                return ''
            if us.lower() in REAL_UNITS:
                return us
            # Tolerate composite real units (e.g. "kg/year", "USD per MT")
            if any(part.strip().lower() in REAL_UNITS for part in us.replace('/', ' ').split()):
                return us
            return ''   # looks like a label, not a unit — drop

        # Pull in the same name-to-unit inference the carbon service
        # uses, so the modal cell displays "28.60 km" even when the
        # LLM left `unit` empty (it always sets `datapoint_name`).
        from .esg_carbon_service import _infer_unit_from_field

        for r in rows:
            fields_map: dict[str, str] = {}
            datapoints = r.datapoints or []
            for d in datapoints:
                name = _resolve_field_name(d)
                if not name:
                    continue
                value = d.get('value')
                unit = _clean_unit(d.get('unit') or '')
                if not unit:
                    inferred = _infer_unit_from_field(
                        d.get('datapoint_name') or d.get('canonical_name') or '',
                        d.get('tags') or [],
                    )
                    unit = _clean_unit(inferred)
                if value is None or value == '':
                    text = '—'
                else:
                    try:
                        text = f'{float(value):,.2f}'
                    except (TypeError, ValueError):
                        text = str(value)
                if unit:
                    text = f'{text} {unit}'.strip()
                fields_map[name] = text
                if name not in column_seen:
                    column_seen.add(name)
                    column_set.append(name)

            kg = float(r.kgco2e) if r.kgco2e is not None else 0.0
            records_out.append({
                'id': r.id,
                'record_label': r.record_label or 'รายการ',
                'category_name': '',
                'source_doc': r.evidence_image_url or r.file_key or '',
                'entry_date': str(r.entry_date) if r.entry_date else '',
                'created_date': r.created_date.isoformat() if r.created_date else '',
                'fields': fields_map,
                'kgco2e_total': kg,
                'ghg_status': r.ghg_status or 'pending',
                'ghg_method': r.ghg_method,
                'ghg_missing_fields': r.ghg_missing_fields or [],
                'ghg_reason': r.ghg_reason,
                'ghg_source_name': r.ghg_source_name,
                'ghg_source_url': r.ghg_source_url,
                'ghg_ef_value': float(r.ghg_ef_value) if r.ghg_ef_value is not None else None,
                'ghg_ef_unit': r.ghg_ef_unit,
            })

        # Category metadata for the response header (re-uses the
        # SCOPE3_CATEGORY_LABELS we imported above for GENERIC_NAMES).
        category_meta = {
            'scope3_category_id': int(scope3_category_id),
            'name_en': scope3_label.get('en'),
            'name_th': scope3_label.get('th'),
        }

        return {
            'success': True,
            'category': category_meta,
            'columns': column_set,
            'records': records_out,
            'record_count': len(records_out),
            'source': 'esg_records',
        }

