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
from ...prompts.esg_extract.prompts import (
    CATEGORY_CLASSIFY_PROMPT,
    SUBCATEGORY_CLASSIFY_PROMPT,
    DATAPOINT_EXTRACT_PROMPT,
)

logger = logging.getLogger(__name__)


class EsgExtractionService:
    """Cascade extraction: category -> subcategory -> datapoint"""

    def __init__(self, db: Session):
        self.db = db

    def process_extraction(self, extraction_id: int) -> Dict[str, Any]:
        """Run the full cascade extraction pipeline on an extraction record"""
        extraction = self.db.query(EsgOrganizationDataExtraction).filter(
            EsgOrganizationDataExtraction.id == extraction_id
        ).first()

        if not extraction:
            return {'success': False, 'message': 'Extraction record not found'}

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
        """Load all active ESG data categories"""
        cats = self.db.query(EsgDataCategory).filter(
            EsgDataCategory.is_active == True,
            EsgDataCategory.deleted_date.is_(None)
        ).order_by(EsgDataCategory.pillar, EsgDataCategory.sort_order).all()
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
        categories_json = json.dumps([
            {'id': c['id'], 'pillar': c['pillar'], 'name': c['name'], 'description': c.get('description', '')}
            for c in categories
        ], indent=2)

        prompt = CATEGORY_CLASSIFY_PROMPT.format(
            categories_json=categories_json,
            input_content=input_content,
        )

        result = self._call_llm(prompt, image_urls)
        parsed = self._parse_json(result)

        if parsed and parsed.get('matches'):
            return sorted(parsed['matches'], key=lambda x: x.get('confidence', 0), reverse=True)
        return []

    def _classify_subcategories(self, input_content: str, category_name: str, subcategories: List[Dict], image_urls: List[str]) -> List[Dict]:
        """Step 2: Classify input into subcategories"""
        subcategories_json = json.dumps([
            {'id': s['id'], 'name': s['name'], 'description': s.get('description', '')}
            for s in subcategories
        ], indent=2)

        prompt = SUBCATEGORY_CLASSIFY_PROMPT.format(
            category_name=category_name,
            subcategories_json=subcategories_json,
            input_content=input_content,
        )

        result = self._call_llm(prompt, image_urls)
        parsed = self._parse_json(result)

        if parsed and parsed.get('matches'):
            return sorted(parsed['matches'], key=lambda x: x.get('confidence', 0), reverse=True)
        return []

    def _extract_datapoints(self, input_content: str, subcategory_name: str, datapoints: List[Dict], image_urls: List[str]) -> Optional[Dict]:
        """Step 3: Extract datapoint values"""
        datapoints_json = json.dumps([
            {'id': d['id'], 'name': d['name'], 'description': d.get('description', ''), 'unit': d.get('unit'), 'data_type': d.get('data_type', 'numeric')}
            for d in datapoints
        ], indent=2)

        prompt = DATAPOINT_EXTRACT_PROMPT.format(
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
