"""
ESG Service — CRUD for settings, documents, org setup, platform bindings, data hierarchy, extractions, completeness
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_
from datetime import datetime, date
from decimal import Decimal
import logging

from ...models.esg.settings import EsgOrganizationSettings
from ...models.esg.documents import EsgDocument
from ...models.esg.organization_setup import EsgOrganizationSetup
from ...models.esg.platform_binding import EsgExternalPlatformBinding
from ...models.esg.data_hierarchy import EsgDataCategory, EsgDataSubcategory, EsgDatapoint
from ...models.esg.data_extraction import EsgOrganizationDataExtraction
from ...models.esg.data_entries import EsgDataEntry

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

        # 2. Entry counts per datapoint (1 query)
        entry_counts_raw = (
            self.db.query(
                EsgDataEntry.datapoint_id,
                func.count(EsgDataEntry.id),
                func.max(EsgDataEntry.value),
                func.max(EsgDataEntry.unit),
                func.sum(EsgDataEntry.calculated_tco2e),
            )
            .filter(
                EsgDataEntry.organization_id == organization_id,
                EsgDataEntry.is_active == True,
                EsgDataEntry.datapoint_id.isnot(None),
            )
            .group_by(EsgDataEntry.datapoint_id)
            .all()
        )

        entry_data = {}
        for dp_id, cnt, latest_val, latest_unit, total_tco2e in entry_counts_raw:
            entry_data[dp_id] = {
                'count': cnt,
                'latest_value': float(latest_val) if latest_val is not None else None,
                'latest_unit': latest_unit,
                'total_tco2e': float(total_tco2e) if total_tco2e else None,
            }

        # Total entries (including unlinked)
        total_entries = self.db.query(func.count(EsgDataEntry.id)).filter(
            EsgDataEntry.organization_id == organization_id,
            EsgDataEntry.is_active == True,
        ).scalar() or 0

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
            pillar_map[p]['categories'].append({
                'id': cat.id,
                'name': cat.name,
                'name_th': cat.name_th,
                'subcategory_count': len(cat_subs),
                'datapoint_count': cat_dp_total,
                'filled_datapoints': cat_dp_filled,
                'entry_count': cat_entries,
                'completeness_pct': cat_pct,
                'subcategories': sub_list,
            })

            pillar_map[p]['_dp_total'] += cat_dp_total
            pillar_map[p]['_dp_filled'] += cat_dp_filled
            pillar_map[p]['_entries'] += cat_entries

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
