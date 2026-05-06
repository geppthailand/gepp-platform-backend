"""
ESG Cascade Extraction Service
Implements 3-step cascade: Category -> Subcategory -> Datapoint extraction
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from ...models.esg.data_hierarchy import EsgDataCategory, EsgDataSubcategory, EsgDatapoint
from ...models.esg.data_extraction import EsgOrganizationDataExtraction
from ...models.esg.settings import EsgOrganizationSettings
from ...prompts.esg_extract.prompts import (
    CATEGORY_CLASSIFY_PROMPT,
    SUBCATEGORY_CLASSIFY_PROMPT,
    DATAPOINT_EXTRACT_PROMPT,
    CATEGORY_CLASSIFY_PROMPT_SCOPE3,
    SUBCATEGORY_CLASSIFY_PROMPT_SCOPE3,
    DATAPOINT_EXTRACT_PROMPT_SCOPE3,
)

logger = logging.getLogger(__name__)


class EsgExtractionService:
    """Cascade extraction: category -> subcategory -> datapoint"""

    def __init__(self, db: Session):
        self.db = db
        # Per-extraction focus context (resolved at run start). Default to
        # scope3_only so misconfigured orgs still get the narrowed taxonomy.
        self._focus_mode: str = 'scope3_only'
        self._enabled_scope3_ids: Optional[List[int]] = None

    def _resolve_focus_context(self, organization_id: Optional[int]) -> None:
        """Look up org settings to decide which prompt + category list to use."""
        if not organization_id:
            self._focus_mode = 'scope3_only'
            self._enabled_scope3_ids = None
            return
        try:
            settings = (
                self.db.query(EsgOrganizationSettings)
                .filter(EsgOrganizationSettings.organization_id == organization_id)
                .first()
            )
            if settings:
                self._focus_mode = settings.focus_mode or 'scope3_only'
                whitelist = list(settings.enabled_scope3_categories or [])
                self._enabled_scope3_ids = whitelist if whitelist else None
            else:
                self._focus_mode = 'scope3_only'
                self._enabled_scope3_ids = None
        except Exception:
            logger.exception('Failed to resolve focus context; defaulting to scope3_only')
            self._focus_mode = 'scope3_only'
            self._enabled_scope3_ids = None

    def process_extraction(self, extraction_id: int) -> Dict[str, Any]:
        """Run the full cascade extraction pipeline on an extraction record"""
        extraction = self.db.query(EsgOrganizationDataExtraction).filter(
            EsgOrganizationDataExtraction.id == extraction_id
        ).first()

        if not extraction:
            return {'success': False, 'message': 'Extraction record not found'}

        # Decide focus mode + Scope-3 whitelist based on the org's settings.
        # Drives both the prompt template choice and the validation guard.
        self._resolve_focus_context(getattr(extraction, 'organization_id', None))

        if extraction.type == 'none':
            extraction.processing_status = 'completed'
            self.db.flush()
            return {'success': True, 'message': 'Skipped non-data message'}

        try:
            extraction.processing_status = 'extracting'
            self.db.flush()

            # Prepare input content for LLM
            input_content = self._prepare_input(extraction)
            image_urls = self._get_image_urls(extraction)

            # Step 1: Category classification
            categories = self._load_categories()
            if not categories:
                extraction.processing_status = 'failed'
                extraction.error_message = 'No ESG categories found in database'
                self.db.flush()
                return {'success': False, 'message': 'No categories configured'}

            category_matches = self._classify_categories(input_content, categories, image_urls)

            if not category_matches:
                extraction.processing_status = 'completed'
                extraction.extractions = {'category_match': None, 'message': 'No matching ESG category found'}
                extraction.processed_at = datetime.utcnow()
                self.db.flush()
                return {'success': True, 'message': 'No ESG category matched'}

            # Step 2: Subcategory classification for each matched category
            extraction.processing_status = 'matching'
            self.db.flush()

            all_datapoint_matches = []
            all_refs = {}
            best_category = category_matches[0] if category_matches else {}
            best_subcategory = {}

            for cat_match in category_matches:
                cat_id = cat_match.get('category_id')
                subcategories = self._load_subcategories(cat_id)
                if not subcategories:
                    continue

                subcat_matches = self._classify_subcategories(
                    input_content, cat_match.get('category_name', ''), subcategories, image_urls
                )

                if not subcat_matches:
                    continue

                if not best_subcategory:
                    best_subcategory = subcat_matches[0]

                # Step 3: Datapoint extraction for each matched subcategory
                for subcat_match in subcat_matches:
                    subcat_id = subcat_match.get('subcategory_id')
                    datapoints = self._load_datapoints(subcat_id)
                    if not datapoints:
                        continue

                    dp_result = self._extract_datapoints(
                        input_content, subcat_match.get('subcategory_name', ''), datapoints, image_urls
                    )

                    if dp_result:
                        matches = dp_result.get('matches', [])
                        all_datapoint_matches.extend(matches)
                        # Merge refs
                        refs = dp_result.get('refs', {})
                        for k, v in refs.items():
                            if v and not all_refs.get(k):
                                all_refs[k] = v

            # Store results
            extraction.extractions = {
                'category_match': best_category,
                'subcategory_match': best_subcategory,
                'all_category_matches': category_matches,
            }
            extraction.datapoint_matches = all_datapoint_matches
            extraction.refs = all_refs
            extraction.processing_status = 'completed'
            extraction.processed_at = datetime.utcnow()
            self.db.flush()

            return {
                'success': True,
                'message': f'Extracted {len(all_datapoint_matches)} datapoints',
                'datapoint_matches': all_datapoint_matches,
            }

        except Exception as e:
            logger.error(f"Extraction pipeline failed for {extraction_id}: {e}", exc_info=True)
            extraction.processing_status = 'failed'
            extraction.error_message = str(e)
            extraction.processed_at = datetime.utcnow()
            self.db.flush()
            return {'success': False, 'message': str(e)}

    # ==========================================
    # DATA LOADING
    # ==========================================

    def _load_categories(self) -> List[Dict]:
        """
        Load active ESG data categories, narrowed by focus mode + the org's
        Scope 3 whitelist when applicable.

        - focus_mode='scope3_only' (default):
            * is_scope3 = TRUE
            * if the org has a non-empty enabled_scope3_categories list,
              further narrow to scope3_category_id IN that list
            * if the whitelist is empty (org hasn't completed materiality
              yet), all 15 Scope 3 categories are still allowed (sensible
              default — narrowing past Scope 3 boundary already cuts the
              taxonomy by ~80%, which is what reduces false positives).

        - focus_mode='full_esg': returns all rows as before.
        """
        query = self.db.query(EsgDataCategory).filter(
            EsgDataCategory.is_active == True,
            EsgDataCategory.deleted_date.is_(None),
        )
        if self._focus_mode == 'scope3_only':
            query = query.filter(EsgDataCategory.is_scope3 == True)
            if self._enabled_scope3_ids:
                query = query.filter(
                    EsgDataCategory.scope3_category_id.in_(self._enabled_scope3_ids)
                )
        cats = query.order_by(
            EsgDataCategory.pillar, EsgDataCategory.sort_order
        ).all()
        return [c.to_dict() for c in cats]

    def _load_subcategories(self, category_id: int) -> List[Dict]:
        """Load subcategories for a given category"""
        subs = self.db.query(EsgDataSubcategory).filter(
            EsgDataSubcategory.esg_data_category_id == category_id,
            EsgDataSubcategory.is_active == True,
            EsgDataSubcategory.deleted_date.is_(None)
        ).order_by(EsgDataSubcategory.sort_order).all()
        return [s.to_dict() for s in subs]

    def _load_datapoints(self, subcategory_id: int) -> List[Dict]:
        """Load datapoints for a given subcategory"""
        dps = self.db.query(EsgDatapoint).filter(
            EsgDatapoint.esg_data_subcategory_id == subcategory_id,
            EsgDatapoint.is_active == True,
            EsgDatapoint.deleted_date.is_(None)
        ).order_by(EsgDatapoint.sort_order).all()
        return [d.to_dict() for d in dps]

    # ==========================================
    # LLM CALLS
    # ==========================================

    def _classify_categories(self, input_content: str, categories: List[Dict], image_urls: List[str]) -> List[Dict]:
        """Step 1: Classify input into ESG categories"""
        # Include scope3_category_id in the prompt menu when narrowed so the
        # model sees stable GHG numbering (1..15) alongside the row id.
        is_scope3 = self._focus_mode == 'scope3_only'
        categories_json = json.dumps(
            [
                {
                    'id': c['id'],
                    'pillar': c['pillar'],
                    'name': c['name'],
                    'description': c.get('description', ''),
                    **({'scope3_category_id': c['scope3_category_id']}
                       if is_scope3 and c.get('scope3_category_id')
                       else {}),
                }
                for c in categories
            ],
            indent=2,
        )

        template = CATEGORY_CLASSIFY_PROMPT_SCOPE3 if is_scope3 else CATEGORY_CLASSIFY_PROMPT
        prompt = template.format(
            categories_json=categories_json,
            input_content=input_content,
        )

        result = self._call_llm(prompt, image_urls)
        parsed = self._parse_json(result)

        if parsed and parsed.get('matches'):
            sorted_matches = sorted(
                parsed['matches'], key=lambda x: x.get('confidence', 0), reverse=True
            )
            # Validation safety net: drop any category id the LLM hallucinated
            # outside the prompt's menu. With scope3_only this also drops any
            # would-be S/G/non-Scope-3 classifications.
            allowed_ids = {c['id'] for c in categories}
            valid = [m for m in sorted_matches if m.get('category_id') in allowed_ids]
            dropped = len(sorted_matches) - len(valid)
            if dropped:
                logger.warning(
                    'Dropped %d category match(es) outside allowed menu '
                    '(focus_mode=%s); kept %d',
                    dropped, self._focus_mode, len(valid),
                )
            return valid
        return []

    def _classify_subcategories(self, input_content: str, category_name: str, subcategories: List[Dict], image_urls: List[str]) -> List[Dict]:
        """Step 2: Classify input into subcategories"""
        subcategories_json = json.dumps([
            {'id': s['id'], 'name': s['name'], 'description': s.get('description', '')}
            for s in subcategories
        ], indent=2)

        template = (
            SUBCATEGORY_CLASSIFY_PROMPT_SCOPE3
            if self._focus_mode == 'scope3_only'
            else SUBCATEGORY_CLASSIFY_PROMPT
        )
        prompt = template.format(
            category_name=category_name,
            subcategories_json=subcategories_json,
            input_content=input_content,
        )

        result = self._call_llm(prompt, image_urls)
        parsed = self._parse_json(result)

        if parsed and parsed.get('matches'):
            sorted_matches = sorted(
                parsed['matches'], key=lambda x: x.get('confidence', 0), reverse=True
            )
            allowed_ids = {s['id'] for s in subcategories}
            valid = [m for m in sorted_matches if m.get('subcategory_id') in allowed_ids]
            dropped = len(sorted_matches) - len(valid)
            if dropped:
                logger.warning(
                    'Dropped %d subcategory match(es) outside allowed menu',
                    dropped,
                )
            return valid
        return []

    def _extract_datapoints(self, input_content: str, subcategory_name: str, datapoints: List[Dict], image_urls: List[str]) -> Optional[Dict]:
        """Step 3: Extract datapoint values"""
        datapoints_json = json.dumps([
            {'id': d['id'], 'name': d['name'], 'description': d.get('description', ''), 'unit': d.get('unit'), 'data_type': d.get('data_type', 'numeric')}
            for d in datapoints
        ], indent=2)

        template = (
            DATAPOINT_EXTRACT_PROMPT_SCOPE3
            if self._focus_mode == 'scope3_only'
            else DATAPOINT_EXTRACT_PROMPT
        )
        prompt = template.format(
            subcategory_name=subcategory_name,
            datapoints_json=datapoints_json,
            input_content=input_content,
        )

        result = self._call_llm(prompt, image_urls)
        return self._parse_json(result)

    # ==========================================
    # HELPERS
    # ==========================================

    def _prepare_input(self, extraction: EsgOrganizationDataExtraction) -> str:
        """Prepare the input content string for LLM prompts"""
        if extraction.raw_content:
            return extraction.raw_content
        if extraction.file_id:
            return f"[Document/Image file - see attached image]"
        return "[No content available]"

    def _get_image_urls(self, extraction: EsgOrganizationDataExtraction) -> List[str]:
        """Get image URLs for the extraction if applicable"""
        if extraction.type != 'image' or not extraction.file_id:
            return []

        # Try to get file URL from the files table
        try:
            from ...models.cores.files import File
            file_record = self.db.query(File).filter(File.id == extraction.file_id).first()
            if file_record and file_record.s3_key:
                bucket = file_record.s3_bucket or 'gepp-platform-files'
                return [f's3://{bucket}/{file_record.s3_key}']
        except Exception:
            pass

        return []

    def _call_llm(self, prompt: str, image_urls: List[str] = None) -> str:
        """Call LLM with optional images, reusing the existing LLM client"""
        from ...prompts.esg_classify.clients.llm_client import (
            _call_llm_with_images, _call_llm_text_only
        )

        if image_urls:
            result = _call_llm_with_images(prompt, image_urls)
        else:
            result = _call_llm_text_only(prompt)

        return result.get('content', '')

    def _parse_json(self, text: str) -> Optional[Dict]:
        """Parse JSON from LLM response"""
        from ...prompts.esg_classify.clients.llm_client import _parse_json_response
        return _parse_json_response(text)
