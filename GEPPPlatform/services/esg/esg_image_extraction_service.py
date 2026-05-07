"""
ESG Image Extraction Service — Single-shot Gemini vision pipeline.
Sends image + full ESG hierarchy to OpenRouter/Gemini, extracts ALL matching datapoints.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy.orm import Session

from ...models.esg.data_hierarchy import EsgDataCategory, EsgDataSubcategory, EsgDatapoint
from ...models.esg.data_extraction import EsgOrganizationDataExtraction
from ...models.esg.data_entries import EsgDataEntry, EntrySource, EntryStatus
from .esg_carbon_service import EsgCarbonService
from .extraction_schema import from_legacy_records, flatten_for_entries, SCHEMA_VERSION

logger = logging.getLogger(__name__)

LIFF_BASE_URL = os.environ.get('LIFF_BASE_URL', 'https://esg.gepp.me')


class EsgImageExtractionService:

    def __init__(self, db: Session):
        self.db = db
        self.carbon = EsgCarbonService(db)

    # ==========================================
    # MAIN ENTRY POINT
    # ==========================================

    def extract_from_image(self, s3_url: str, org_id: int,
                           line_user_id: str, message_id: str,
                           existing_extraction=None) -> Dict[str, Any]:
        """
        Full pipeline: image → Gemini → structured data → entries → Flex card data.

        Args:
            existing_extraction: optional pre-created EsgOrganizationDataExtraction.
                When supplied (e.g. by `_process_image` which reserves the doc
                number up-front for the immediate ack), we re-use it instead
                of inserting a duplicate row.
        """
        if existing_extraction is not None:
            extraction = existing_extraction
            logger.info(f"[EXTRACT] Reusing extraction {extraction.id} (pre-reserved by caller)")
        else:
            extraction = EsgOrganizationDataExtraction(
                organization_id=org_id,
                channel='line',
                type='image',
                source_user_id=line_user_id,
                source_message_id=message_id,
                raw_content=s3_url,
                processing_status='pending',
            )
            self.db.add(extraction)
            self.db.flush()
            logger.info(f"[EXTRACT] Created extraction {extraction.id} for org={org_id}, s3={s3_url[:60]}")

        try:
            # 2. Load hierarchy
            hierarchy, lookup = self._load_full_hierarchy()
            if not hierarchy:
                extraction.processing_status = 'failed'
                extraction.error_message = 'No ESG hierarchy configured'
                self.db.commit()
                return {'success': False, 'message': 'ยังไม่มีโครงสร้าง ESG ในระบบ', 'extraction_id': extraction.id}

            hierarchy_json = json.dumps(hierarchy, ensure_ascii=False, indent=None)
            logger.info(f"[EXTRACT] Hierarchy loaded: {len(hierarchy)} categories, {len(lookup)} datapoints, json_len={len(hierarchy_json)}")

            # 3. Build prompt
            prompt = self._build_extraction_prompt(hierarchy_json)

            # 4. Call Gemini
            logger.info(f"[EXTRACT] Calling Gemini with image...")
            from ...prompts.esg_classify.clients.llm_client import _call_llm_with_images, _parse_json_response
            result = _call_llm_with_images(prompt, [s3_url])
            logger.info(f"[EXTRACT] Gemini response: {result.get('usage', {})}, content_len={len(result.get('content', ''))}")

            # 5. Parse JSON
            raw_content = result.get('content', '')
            logger.info(f"[EXTRACT] Raw Gemini response (first 500 chars): {raw_content[:500]}")
            parsed = _parse_json_response(raw_content)
            if not parsed:
                logger.error(f"[EXTRACT] JSON parse FAILED")
                extraction.processing_status = 'failed'
                extraction.error_message = f"JSON parse failed. Raw: {raw_content[:500]}"
                self.db.commit()
                return {'success': False, 'message': 'ไม่สามารถอ่านข้อมูลจากรูปได้', 'extraction_id': extraction.id}

            logger.info(f"[EXTRACT] Parsed: records={len(parsed.get('records', []))}, matches={len(parsed.get('matches', []))}, totals={len(parsed.get('totals', []))}")

            # 6. Validate — returns list of record dicts
            validated_records, refs = self._validate_extraction(parsed, lookup)
            logger.info(f"[EXTRACT] Validated: {len(validated_records)} records")

            # 7. Create entries from records
            entries = []
            entry_ids = []
            if validated_records:
                logger.info(f"[EXTRACT] Creating entries from {len(validated_records)} records...")
                entries, entry_ids = self._create_entries(validated_records, org_id, line_user_id, s3_url, refs)
                logger.info(f"[EXTRACT] Created {len(entries)} entries, ids={entry_ids}")

            # 8. Store — clean internal keys from records before persisting
            clean_records = []
            for rec in validated_records:
                clean_rec = {k: v for k, v in rec.items() if not k.startswith('_')}
                if 'fields' in clean_rec:
                    clean_rec['fields'] = [{k: v for k, v in f.items() if not k.startswith('_')} for f in clean_rec['fields']]
                clean_records.append(clean_rec)

            additional_info = parsed.get('additional_info', []) or []
            totals = parsed.get('totals', []) or []

            extraction.extractions = {
                'model': 'google/gemini-3-flash-preview',
                'method': 'single_shot_records',
                'raw_response': raw_content[:2000],
                'entry_ids': entry_ids,
                's3_url': s3_url,
            }
            extraction.datapoint_matches = clean_records  # legacy
            extraction.refs = refs                         # legacy

            # Build compact structured_data (ver=2)
            extraction.structured_data = from_legacy_records(
                records=validated_records,
                refs=refs,
                totals=totals,
                additional_info=additional_info,
                summary=parsed.get('document_summary', ''),
            )
            extraction.processing_status = 'completed'
            extraction.processed_at = datetime.now(timezone.utc)
            self.db.commit()

            return {
                'success': True,
                'extraction_id': extraction.id,
                'entries': entries,
                'records': validated_records,
                'refs': refs,
                'match_count': len(entries),
                'document_summary': parsed.get('document_summary', ''),
                'additional_info': additional_info,
                'totals': totals,
            }

        except Exception as e:
            logger.error(f"[EXTRACT] Error: {e}", exc_info=True)
            extraction.processing_status = 'failed'
            extraction.error_message = str(e)[:500]
            self.db.commit()
            return {'success': False, 'message': str(e), 'extraction_id': extraction.id}

    # ==========================================
    # HIERARCHY LOADER
    # ==========================================

    def _load_full_hierarchy(self) -> Tuple[List[Dict], Dict]:
        """Load full ESG hierarchy as nested structure + flat lookup."""
        categories = self.db.query(EsgDataCategory).filter(
            EsgDataCategory.is_active == True,
        ).order_by(EsgDataCategory.pillar, EsgDataCategory.sort_order).all()

        subcategories = self.db.query(EsgDataSubcategory).filter(
            EsgDataSubcategory.is_active == True,
        ).order_by(EsgDataSubcategory.sort_order).all()

        datapoints = self.db.query(EsgDatapoint).filter(
            EsgDatapoint.is_active == True,
        ).order_by(EsgDatapoint.sort_order).all()

        # Build lookup maps
        sub_by_cat = {}
        for s in subcategories:
            sub_by_cat.setdefault(s.esg_data_category_id, []).append(s)

        dp_by_sub = {}
        for d in datapoints:
            dp_by_sub.setdefault(d.esg_data_subcategory_id, []).append(d)

        # Build nested structure
        hierarchy = []
        flat_lookup = {}

        for cat in categories:
            cat_dict = {
                'id': cat.id, 'pillar': cat.pillar,
                'name': cat.name, 'name_th': cat.name_th,
                'subcategories': [],
            }
            for sub in sub_by_cat.get(cat.id, []):
                sub_dict = {
                    'id': sub.id, 'name': sub.name, 'name_th': sub.name_th,
                    'datapoints': [],
                }
                for dp in dp_by_sub.get(sub.id, []):
                    dp_dict = {
                        'id': dp.id, 'name': dp.name, 'name_th': dp.name_th,
                        'unit': dp.unit, 'data_type': dp.data_type,
                    }
                    sub_dict['datapoints'].append(dp_dict)
                    flat_lookup[dp.id] = {
                        'category_id': cat.id, 'category_name': cat.name,
                        'subcategory_id': sub.id, 'subcategory_name': sub.name,
                        'pillar': cat.pillar,
                    }
                cat_dict['subcategories'].append(sub_dict)
            hierarchy.append(cat_dict)

        return hierarchy, flat_lookup

    # ==========================================
    # PROMPT
    # ==========================================

    def _build_extraction_prompt(self, hierarchy_json: str) -> str:
        return f"""You are an ESG (Environmental, Social, Governance) data extraction specialist.
Analyze the document/image and extract ALL ESG-related data points.

ESG Data Hierarchy:
{hierarchy_json}

Instructions:
1. Examine the image carefully (receipt, invoice, bill, report, manifest, certificate, etc.)
2. Extract ALL data that matches datapoints in the hierarchy — map EVERY column/field in the document to the closest matching datapoint
3. One document can have MULTIPLE categories, subcategories, and datapoints
4. IMPORTANT: When data appears as a TABLE or LIST of similar items (e.g. multiple assets, multiple transactions), group related fields into RECORDS. Each record represents one row/item.
5. Convert values to the units specified in the datapoint definition when possible
6. FINANCIAL DATA: Extract ALL monetary values (rates, unit prices, total costs, amounts) as separate datapoint entries. Include the currency code (e.g. "USD", "THB") in the tags array.
7. EMISSION DATA: Extract emission factors (e.g. tCO2e per unit) and calculated emissions (e.g. total tCO2e per line) as separate datapoint entries — do NOT combine them into a single value.
8. CROSS-TABLE EXTRACTION: When a document has multiple tables (e.g. Table 1 = invoice details, Table 2 = GHG data), correlate rows across tables by matching identifiers (line numbers, product references) and merge all fields into a single record per item.

Respond in JSON format ONLY:
{{
    "records": [
        {{
            "record_label": "<short label for this record, e.g. asset name or row identifier>",
            "category_id": <int>,
            "category_name": "<name>",
            "subcategory_id": <int>,
            "subcategory_name": "<name>",
            "fields": [
                {{
                    "datapoint_id": <int>,
                    "datapoint_name": "<name>",
                    "value": <value - numeric or text>,
                    "unit": "<unit>",
                    "confidence": <0.0-1.0>,
                    "tags": ["<metadata tag>", "<currency code if monetary, e.g. USD>", "<description of what value represents>"]
                }}
            ]
        }}
    ],
    "totals": [
        {{
            "label": "<e.g. TOTAL CATEGORY 2 EMISSIONS>",
            "value": <numeric>,
            "unit": "<unit>"
        }}
    ],
    "refs": {{
        "document_date": "<YYYY-MM-DD or null>",
        "vendor": "<vendor/company name or null>",
        "location": "<location or null>",
        "reference_number": "<invoice/receipt number or null>"
    }},
    "additional_info": [
        {{
            "label": "<info label, e.g. Emission calculation methodology>",
            "value": "<extracted text or description>",
            "section": "<which section of the document this came from>"
        }}
    ],
    "document_summary": "<brief 1-sentence Thai summary>"
}}

Rules:
- Group related fields into RECORDS (e.g. one asset = one record with ALL its fields: type, quantity, rate, cost, emission factor, emissions, etc.)
- Each record belongs to one category/subcategory
- For each field, add relevant "tags" — metadata descriptors that describe what the number represents. For monetary values, ALWAYS include the currency code (e.g. "USD", "THB") as the first tag.
- Extract EVERY column from EVERY table in the document — do not skip columns just because they seem secondary. Financial data (rates, costs, totals) and emission data (factors, calculated emissions) are equally important.
- When a document has multiple tables about the same items, merge data from all tables into unified records.
- additional_info: Extract ANY useful information from the document that doesn't fit into datapoints — methodology descriptions, footnotes, assumptions, certification info, reporting boundaries, data sources, etc.
- Totals are summary numbers found at the bottom of tables
- Minimum confidence: 0.3
- If no ESG data found, return {{"records": [], "totals": [], "refs": {{}}, "additional_info": [], "document_summary": "ไม่พบข้อมูล ESG"}}"""

    # ==========================================
    # VALIDATION
    # ==========================================

    def _validate_extraction(self, parsed: Dict, lookup: Dict) -> Tuple[List[Dict], Dict]:
        """
        Validate Gemini response. Supports both:
        - New format: { records: [{record_label, fields: [{datapoint_id, value, ...}]}] }
        - Legacy flat: { matches: [{datapoint_id, value, ...}] }
        Returns (validated_records, refs) where each record has 'fields' list.
        """
        refs = parsed.get('refs', {}) or {}
        totals = parsed.get('totals', []) or []
        validated_records = []

        # Handle new "records" format
        records = parsed.get('records', [])
        if records:
            for rec in records:
                fields = rec.get('fields', [])
                valid_fields = []
                for f in fields:
                    dp_id = f.get('datapoint_id')
                    confidence = f.get('confidence', 0.5)
                    value = f.get('value')
                    if value is None:
                        continue

                    # Tag value type
                    try:
                        float(value)
                        f['_value_type'] = 'numeric'
                    except (ValueError, TypeError):
                        f['_value_type'] = 'text'

                    # Enrich from hierarchy
                    if dp_id and dp_id in lookup:
                        hier = lookup[dp_id]
                        f['category_id'] = hier['category_id']
                        f['subcategory_id'] = hier['subcategory_id']
                    valid_fields.append(f)

                if valid_fields:
                    validated_records.append({
                        'record_label': rec.get('record_label', ''),
                        'category_id': rec.get('category_id'),
                        'category_name': rec.get('category_name', ''),
                        'subcategory_id': rec.get('subcategory_id'),
                        'subcategory_name': rec.get('subcategory_name', ''),
                        'fields': valid_fields,
                    })

        # Handle legacy flat "matches" format (backward compat)
        matches = parsed.get('matches', [])
        if matches and not records:
            for m in matches:
                dp_id = m.get('datapoint_id')
                value = m.get('value')
                if value is None:
                    continue
                try:
                    float(value)
                    m['_value_type'] = 'numeric'
                except (ValueError, TypeError):
                    m['_value_type'] = 'text'
                if dp_id and dp_id in lookup:
                    hier = lookup[dp_id]
                    m['category_id'] = hier['category_id']
                    m['subcategory_id'] = hier['subcategory_id']
                    m['category_name'] = hier['category_name']
                    m['subcategory_name'] = hier['subcategory_name']
                # Wrap as single-field record
                validated_records.append({
                    'record_label': m.get('datapoint_name', ''),
                    'category_name': m.get('category_name', ''),
                    'subcategory_name': m.get('subcategory_name', ''),
                    'fields': [m],
                })

        # Add totals as a special record
        if totals:
            total_fields = []
            for t in totals:
                try:
                    float(t.get('value', 0))
                    t['_value_type'] = 'numeric'
                except (ValueError, TypeError):
                    t['_value_type'] = 'text'
                t['datapoint_name'] = t.get('label', 'Total')
                total_fields.append(t)
            validated_records.append({
                'record_label': 'TOTALS',
                'category_name': 'Summary',
                'subcategory_name': '',
                'fields': total_fields,
                '_is_total': True,
            })

        logger.info(f"[EXTRACT] Validated: {len(validated_records)} records")
        return validated_records, refs

    # ==========================================
    # ENTRY CREATION
    # ==========================================

    def _create_entries(self, records: List[Dict], org_id: int,
                        line_user_id: str, s3_url: str, refs: Dict) -> Tuple[List[Dict], List[int]]:
        """Create EsgDataEntry for each field in each record. Return (entry_dicts, entry_ids)."""
        entries = []
        entry_ids = []
        doc_date = None
        if refs.get('document_date'):
            try:
                doc_date = datetime.strptime(refs['document_date'], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                doc_date = datetime.now(timezone.utc).date()

        for rec in records:
            if rec.get('_is_total'):
                continue  # Don't create entries for totals — just display

            cat_name = rec.get('category_name', '') or 'Unknown'
            rec_label = rec.get('record_label', '')

            for f in rec.get('fields', []):
                raw_value = f.get('value')
                unit = f.get('unit', '') or '-'
                is_numeric = f.get('_value_type') == 'numeric'
                dp_name = f.get('datapoint_name', '')
                logger.info(f"[ENTRY] Creating: rec={rec_label}, dp={dp_name}, val={raw_value}, unit={unit}")

                if is_numeric:
                    num_value = float(raw_value)
                    notes_text = f"AI: [{rec_label}] {dp_name} ({f.get('confidence', 0):.0%})"
                else:
                    num_value = 0
                    notes_text = f"AI: [{rec_label}] {dp_name} = {raw_value} ({f.get('confidence', 0):.0%})"

                tco2e = None
                if is_numeric and num_value and unit:
                    try:
                        tco2e = self.carbon.calculate_tco2e(cat_name, num_value, unit)
                    except Exception:
                        pass

                scope_tag = None
                try:
                    scope_tag = self.carbon.get_scope_for_category(cat_name)
                except Exception:
                    pass

                # Build metadata from LLM response context
                tags = f.get('tags', []) or []
                entry_metadata = {
                    'record_label': rec_label,
                    'confidence': f.get('confidence', 0),
                    'tags': tags,
                }

                # Detect currency from tags (e.g. ["USD", "rate per MT"])
                currency = None
                currency_codes = {'USD', 'THB', 'EUR', 'GBP', 'JPY', 'CNY', 'SGD', 'HKD', 'AUD', 'KRW'}
                for tag in tags:
                    if isinstance(tag, str) and tag.upper() in currency_codes:
                        currency = tag.upper()
                        break

                entry = EsgDataEntry(
                    organization_id=org_id,
                    line_user_id=line_user_id,
                    category_id=f.get('category_id') or rec.get('category_id'),
                    subcategory_id=f.get('subcategory_id') or rec.get('subcategory_id'),
                    datapoint_id=f.get('datapoint_id'),
                    category=cat_name,
                    value=num_value,
                    unit=unit,
                    calculated_tco2e=tco2e,
                    scope_tag=scope_tag,
                    extra_data=entry_metadata,
                    currency=currency,
                    evidence_image_url=s3_url,
                    file_key=s3_url,
                    entry_source=EntrySource.LINE_CHAT,
                    status=EntryStatus.PENDING_VERIFY,
                    entry_date=doc_date or datetime.now(timezone.utc).date(),
                    notes=notes_text,
                )
                self.db.add(entry)
                self.db.flush()
                entries.append(entry.to_dict())
                entry_ids.append(entry.id)

        self.db.commit()
        return entries, entry_ids

    # ==========================================
    # FLEX MESSAGE CARD BUILDER
    # ==========================================

    def build_result_flex_card(self, entries: List[Dict], refs: Dict,
                               extraction_id: int, document_summary: str = '',
                               records: List[Dict] = None) -> Dict:
        """Build a LINE Flex Message card with records grouped as sub-components."""
        count = len(entries)
        if count == 0:
            return self._build_empty_flex()

        body_contents = []

        # ── Scope 3 category chip — explicitly tell the user which of the
        # 15 GHG Protocol categories we assigned this evidence to. Picks
        # the most-frequent assignment across all extracted entries.
        from collections import Counter
        from .scope3_assignment import (
            assign_scope3_category,
            missing_fields_for,
            SCOPE3_LABELS,
        )

        cat_votes: Counter = Counter()
        present_fields: set = set()
        first_unit = ''
        for e in entries:
            ent_unit = (e.get('unit') or '').lower()
            if ent_unit and not first_unit:
                first_unit = ent_unit
            cid, _, _, _ = assign_scope3_category(
                self.db,
                category_name=e.get('category'),
                category_id=e.get('category_id'),
                unit=ent_unit,
                raw_input=document_summary or '',
            )
            if cid:
                cat_votes[cid] += 1
            for f_name in (e.get('field') or e.get('datapoint_name') or '',):
                if f_name:
                    present_fields.add(f_name.lower())
            if ent_unit:
                present_fields.add(ent_unit)

        scope3_id = cat_votes.most_common(1)[0][0] if cat_votes else None
        if scope3_id:
            lbl = SCOPE3_LABELS.get(scope3_id, {})
            chip_text = f'หมวด {scope3_id} · {lbl.get("th") or lbl.get("en") or "Scope 3"}'
            body_contents.append({
                'type': 'box', 'layout': 'vertical', 'cornerRadius': '8px',
                'backgroundColor': '#ECFDF5', 'paddingAll': '8px',
                'contents': [
                    {'type': 'text', 'text': 'Carbon Scope 3',
                     'size': 'xxs', 'color': '#047857', 'weight': 'bold'},
                    {'type': 'text', 'text': chip_text,
                     'size': 'sm', 'color': '#047857', 'weight': 'bold',
                     'wrap': True, 'margin': 'xs'},
                ],
            })
            body_contents.append({'type': 'separator', 'margin': 'md'})

        # ── Refs row ──
        refs_parts = []
        if refs.get('vendor'):
            refs_parts.append(refs['vendor'])
        if refs.get('document_date'):
            refs_parts.append(refs['document_date'])
        if refs.get('reference_number'):
            refs_parts.append(f"#{refs['reference_number']}")
        if refs_parts:
            body_contents.append({
                'type': 'text', 'text': f"📄 {' · '.join(refs_parts)}",
                'size': 'xs', 'color': '#888888', 'wrap': True,
            })

        # ── Document summary ──
        if document_summary:
            body_contents.append({
                'type': 'text', 'text': document_summary,
                'size': 'xs', 'color': '#666666', 'margin': 'sm', 'wrap': True,
            })

        if refs_parts or document_summary:
            body_contents.append({'type': 'separator', 'margin': 'md'})

        # Stash for the missing-fields footer (rendered after records)
        _scope3_id_for_footer = scope3_id
        _present_for_footer = list(present_fields)

        # ── Records as grouped cards ──
        shown_records = 0
        max_records = 6  # max records to show in card
        use_records = records or []

        for rec in use_records:
            if shown_records >= max_records:
                break

            is_total = rec.get('_is_total', False)
            label = rec.get('record_label', '')
            cat_name = rec.get('category_name', '')
            fields = rec.get('fields', [])

            if is_total:
                # ── Totals section ──
                body_contents.append({'type': 'separator', 'margin': 'lg'})
                for f in fields:
                    dp_name = f.get('datapoint_name', f.get('label', 'Total'))
                    val = f.get('value', 0)
                    unit = f.get('unit', '')
                    try:
                        val_text = f"{float(val):,.2f} {unit}"
                    except (ValueError, TypeError):
                        val_text = f"{val} {unit}"
                    body_contents.append({
                        'type': 'box', 'layout': 'horizontal', 'margin': 'sm',
                        'contents': [
                            {'type': 'text', 'text': dp_name, 'size': 'xs', 'weight': 'bold', 'color': '#2d6a4f', 'flex': 4},
                            {'type': 'text', 'text': val_text, 'size': 'xs', 'weight': 'bold', 'color': '#2d6a4f', 'flex': 3, 'align': 'end'},
                        ],
                    })
                continue

            shown_records += 1

            # ── Category + Record label header ──
            header_text = cat_name
            if label and label != cat_name:
                header_text = f"{cat_name}"

            body_contents.append({
                'type': 'text', 'text': header_text, 'weight': 'bold',
                'size': 'sm', 'color': '#2d6a4f', 'margin': 'lg',
            })

            if label and label != cat_name:
                body_contents.append({
                    'type': 'text', 'text': f"📋 {label}",
                    'size': 'xs', 'color': '#888888', 'margin': 'xs',
                })

            # ── Fields as key-value rows ──
            for f in fields:
                dp_name = f.get('datapoint_name', '')
                raw_val = f.get('value', '')
                unit = f.get('unit', '')
                is_numeric = f.get('_value_type') == 'numeric'

                if is_numeric:
                    try:
                        val_text = f"{float(raw_val):,.2f} {unit}"
                    except (ValueError, TypeError):
                        val_text = f"{raw_val} {unit}"
                else:
                    val_text = str(raw_val) if raw_val else 'None'

                body_contents.append({
                    'type': 'box', 'layout': 'horizontal', 'margin': 'xs',
                    'contents': [
                        {'type': 'text', 'text': dp_name or '-', 'size': 'xxs', 'color': '#888888', 'flex': 4},
                        {'type': 'text', 'text': val_text, 'size': 'xxs', 'weight': 'bold', 'color': '#333333', 'flex': 4, 'align': 'end', 'wrap': True},
                    ],
                })

            # Thin separator between records
            body_contents.append({'type': 'separator', 'margin': 'md', 'color': '#eeeeee'})

        # ── Truncation notice ──
        remaining = len([r for r in use_records if not r.get('_is_total')]) - shown_records
        if remaining > 0:
            body_contents.append({
                'type': 'text',
                'text': f'...และอีก {remaining} รายการ ดูทั้งหมดใน LIFF',
                'size': 'xs', 'color': '#888888', 'margin': 'sm', 'align': 'center',
            })

        # ── Total tCO2e ──
        total_tco2e = sum(e.get('calculated_tco2e', 0) or 0 for e in entries)
        if total_tco2e > 0:
            body_contents.append({'type': 'separator', 'margin': 'lg'})
            body_contents.append({
                'type': 'box', 'layout': 'horizontal', 'margin': 'md',
                'contents': [
                    {'type': 'text', 'text': 'รวม tCO₂e', 'size': 'sm', 'color': '#047857', 'weight': 'bold', 'flex': 3},
                    {'type': 'text', 'text': f'{total_tco2e:.4f}', 'size': 'sm', 'weight': 'bold', 'color': '#047857', 'flex': 2, 'align': 'end'},
                ],
            })
        else:
            # No factor matched — surface that explicitly so the user
            # knows we read the data but didn't compute emissions yet.
            body_contents.append({'type': 'separator', 'margin': 'lg'})
            body_contents.append({
                'type': 'text',
                'text': 'ยังคำนวณ tCO₂e ไม่ได้ — ขาดข้อมูลด้านล่าง',
                'size': 'xs', 'color': '#b45309', 'weight': 'bold',
                'margin': 'md', 'wrap': True,
            })

        # ── Missing fields hint (per assigned Scope 3 category) ──
        if _scope3_id_for_footer:
            try:
                missing = missing_fields_for(
                    _scope3_id_for_footer, _present_for_footer, lang='th'
                )
            except Exception:
                missing = []
            if missing:
                body_contents.append({'type': 'separator', 'margin': 'md'})
                body_contents.append({
                    'type': 'text', 'text': '🟠 ข้อมูลที่ยังขาด:',
                    'size': 'xs', 'color': '#b45309',
                    'weight': 'bold', 'margin': 'md',
                })
                for m in missing[:4]:
                    body_contents.append({
                        'type': 'text', 'text': f'  • {m}',
                        'size': 'xs', 'color': '#92400e',
                        'wrap': True, 'margin': 'xs',
                    })

        return {
            'type': 'flex',
            'altText': f'ESG Data Extracted: {count} รายการ',
            'contents': {
                'type': 'bubble',
                'size': 'giga',
                'header': {
                    'type': 'box', 'layout': 'horizontal',
                    'backgroundColor': '#2d6a4f', 'paddingAll': '14px',
                    'contents': [
                        {'type': 'text', 'text': 'ESG Data Extracted', 'color': '#ffffff', 'weight': 'bold', 'size': 'md', 'flex': 4},
                        {'type': 'text', 'text': f'{count} รายการ', 'color': '#ffffff', 'size': 'sm', 'align': 'end', 'flex': 2},
                    ],
                },
                'body': {
                    'type': 'box', 'layout': 'vertical', 'spacing': 'none',
                    'paddingAll': '14px',
                    'contents': body_contents,
                },
                'footer': {
                    'type': 'box', 'layout': 'horizontal', 'spacing': 'md',
                    'paddingAll': '14px',
                    'contents': [
                        {
                            'type': 'button',
                            'action': {'type': 'postback', 'label': 'ยืนยันทั้งหมด', 'data': f'action=confirm_all&extraction_id={extraction_id}'},
                            'style': 'primary', 'color': '#2d6a4f', 'height': 'sm',
                        },
                        {
                            'type': 'button',
                            'action': {'type': 'uri', 'label': 'ดูใน LIFF', 'uri': f'{LIFF_BASE_URL}/liff/app/history'},
                            'style': 'secondary', 'height': 'sm',
                        },
                    ],
                },
            },
        }

    def _build_empty_flex(self) -> Dict:
        """Flex message when no data could be extracted."""
        return {
            'type': 'flex',
            'altText': 'ไม่พบข้อมูล ESG',
            'contents': {
                'type': 'bubble',
                'body': {
                    'type': 'box', 'layout': 'vertical', 'spacing': 'md',
                    'paddingAll': '20px',
                    'contents': [
                        {'type': 'text', 'text': 'ไม่พบข้อมูล ESG', 'weight': 'bold', 'size': 'md', 'color': '#333333', 'align': 'center'},
                        {'type': 'text', 'text': 'ไม่สามารถอ่านข้อมูลจากรูปได้\nกรุณาถ่ายใหม่ให้ชัดขึ้น หรือกรอกข้อมูลผ่าน LIFF', 'size': 'xs', 'color': '#888888', 'wrap': True, 'align': 'center', 'margin': 'md'},
                    ],
                },
                'footer': {
                    'type': 'box', 'layout': 'vertical',
                    'contents': [
                        {'type': 'button', 'action': {'type': 'uri', 'label': 'กรอกข้อมูลใน LIFF', 'uri': f'{LIFF_BASE_URL}/liff/app/entry'}, 'style': 'primary', 'color': '#2d6a4f'},
                    ],
                },
            },
        }
