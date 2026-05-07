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
from ...models.esg.records import EsgRecord, GhgStatus
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
            # 2. Load hierarchy (filtered to Scope 3 when org focus_mode='scope3_only')
            hierarchy, lookup = self._load_full_hierarchy(organization_id=org_id)
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

            # 7. Record-centric write — one EsgRecord row per atomic
            # record, datapoints stored as JSONB. This is the only
            # write path now (the legacy datapoint-row table
            # `esg_data_entries` is being phased out per the schema
            # refactor; all read paths must move to `esg_records`).
            entries = []      # legacy field name kept in the response shape
            entry_ids = []    # response shape keeps this for now (LIFF flex card)
            record_dicts = []
            if validated_records:
                logger.info(f"[EXTRACT] Creating EsgRecord rows from {len(validated_records)} records...")
                record_dicts = self._create_records(
                    validated_records, org_id, line_user_id, s3_url,
                    refs, extraction.id,
                )
                logger.info(f"[EXTRACT] Created {len(record_dicts)} EsgRecord rows")
                # Synthesise per-field "entry" dicts so existing
                # downstream code (LIFF flex card, response shape)
                # keeps working without a model rewrite. Each EsgRecord
                # explodes into one entry-dict per datapoint.
                # Build a quick lookup: validated_records by index → category name
                _label_to_cat = {
                    rec.get('record_label'): rec.get('category_name', '')
                    for rec in validated_records
                }
                for r in record_dicts:
                    cat_name = _label_to_cat.get(r.get('record_label'), '') or 'Unknown'
                    for d in (r.get('datapoints') or []):
                        entries.append({
                            'id': r.get('id'),
                            'category': cat_name,
                            'category_id': r.get('category_id'),
                            'datapoint_id': d.get('datapoint_id'),
                            'datapoint_name': d.get('datapoint_name'),
                            'field': d.get('canonical_name') or d.get('datapoint_name'),
                            'value': d.get('value'),
                            'unit': d.get('unit'),
                            'calculated_tco2e':
                                (float(r.get('kgco2e')) / 1000.0)
                                if r.get('kgco2e') is not None else None,
                            'extra_data': {
                                'record_label': r.get('record_label'),
                                'tags': d.get('tags'),
                                'datapoint_name': d.get('datapoint_name'),
                            },
                            'evidence_image_url': r.get('evidence_image_url'),
                            'entry_date': r.get('entry_date'),
                        })
                    entry_ids.append(r.get('id'))

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

    def _load_full_hierarchy(self, organization_id: int = None) -> Tuple[List[Dict], Dict]:
        """
        Load ESG hierarchy as nested structure + flat lookup.

        When the org's focus_mode is 'scope3_only' (default), the
        category list is filtered to is_scope3=TRUE rows only — this
        prevents the LLM from picking legacy categories like
        'Materials & Circular Economy' / 'Waste Management' / the
        generic 'Carbon Emissions Scope 3' bucket. The model is then
        forced to choose one of the 15 GHG Protocol Scope 3 categories.
        """
        # Resolve focus context (best-effort — default to scope3_only)
        focus_mode = 'scope3_only'
        try:
            from ...models.esg.settings import EsgOrganizationSettings
            if organization_id:
                settings = (
                    self.db.query(EsgOrganizationSettings)
                    .filter(EsgOrganizationSettings.organization_id == organization_id)
                    .first()
                )
                if settings and settings.focus_mode:
                    focus_mode = settings.focus_mode
        except Exception:
            logger.exception('Could not resolve focus_mode; defaulting to scope3_only')

        cat_query = self.db.query(EsgDataCategory).filter(
            EsgDataCategory.is_active == True,
        )
        if focus_mode == 'scope3_only':
            cat_query = cat_query.filter(
                EsgDataCategory.is_scope3 == True,
                EsgDataCategory.scope3_category_id.isnot(None),
            )
        categories = cat_query.order_by(
            EsgDataCategory.pillar, EsgDataCategory.sort_order
        ).all()
        logger.info(
            f"[EXTRACT] Hierarchy filter: focus_mode={focus_mode}, "
            f"categories={len(categories)}"
        )

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

3a. **EXTRACT EVERY ATOMIC FIELD PER RECORD — NOT JUST THE TOTAL.** A record's `fields[]` must include EVERY label-value pair you can read from the document for that record, not just the bottom-line amount. The hierarchy is intentionally sparse for some categories — when no canonical datapoint matches a field, set `datapoint_id: null` and put the *most specific* human-readable label in `datapoint_name` (NEVER the category name).

   • Hotel folio  → `[hotel_name, room_number, check_in_date, check_out_date, nights, room_rate_per_night, room_charge, vat, service_charge, total_amount]`
   • Taxi receipt → `[origin, destination, distance_km, base_fare, toll_fee, surcharge, vehicle_registration, driver_name, total_fare]`
   • Flight ticket → `[airline, flight_number, origin_airport, destination_airport, class, fare_basis, base_fare, taxes, total_fare]`
   • Train/bus ticket → `[origin_station, destination_station, ticket_type, fare]`
   • Utility bill  → `[meter_id, billing_period_start, billing_period_end, kwh_consumed, unit_rate, energy_charge, vat, total_amount]`
   • Asset register row → `[asset_name, asset_type, useful_life_years, embodied_co2e_kg, purchase_cost]`
   • Invoice line → `[sku, description, quantity, unit_price, total_price]`
   • Waste manifest → `[waste_stream, weight_kg, hauler_name, disposal_method]`

   **NEVER reuse the category name** ("Business travel", "Employee commuting", "Capital goods", etc.) as a `datapoint_name` — those are too coarse for the data warehouse modal columns. Each field deserves its own specific label.

4. **WHAT IS A "RECORD"?** A record is ONE *atomic GHG-calculatable item* — the smallest unit on which an emission factor multiplies a single activity quantity to produce one tCO2e number. Use this rule to decide:

     • One taxi/Grab trip A → B  → ONE record (origin, destination, distance, fare).
     • One hotel stay (3 nights, 1 guest) → ONE record (nights, room rate). Do NOT split per night.
     • One flight leg (BKK → NRT)  → ONE record (origin, destination, class, distance). Each LEG is its own record on a multi-leg ticket.
     • One bus / train ticket → ONE record per journey segment.
     • One shipment / waybill leg (origin → destination, weight, mode) → ONE record per leg.
     • One invoice line item (one SKU, one quantity, one unit price) → ONE record. A 7-line invoice = 7 records.
     • One owned-asset row in an asset register → ONE record (asset name, useful life, GHG embodied).
     • One utility-bill billing period (one electricity meter, one billing cycle) → ONE record. Two meters on the same bill = two records.
     • One employee commute trip (mode + km) → ONE record per direction-day if the document tracks it that way; otherwise one record per row in the data table.

   In other words: if collapsing two rows into one would force you to **average** an emission factor or **lose** a discrete quantity, keep them as separate records. If splitting one row into many would force you to **invent** a quantity that isn't on the document, keep it as one record.

   Each record's `record_label` MUST be a short, human-readable identifier of that single atomic item — e.g. `"Taxi BKK→Suvarnabhumi"`, `"Room — Mr. Nattapong"`, `"Shipment leg #4"`, `"Steel Chassis × 12,500 kg"`. NEVER reuse the same `record_label` across different records on the same document. NEVER use generic placeholders like `"Item"`, `"Record"`, `"Row"` — that breaks the per-atom GHG view downstream.

5. Convert values to the units specified in the datapoint definition when possible
6. FINANCIAL DATA: Extract ALL monetary values (rates, unit prices, total costs, amounts) as separate datapoint entries. Include the currency code (e.g. "USD", "THB") in the tags array.
7. EMISSION DATA: Extract emission factors (e.g. tCO2e per unit) and calculated emissions (e.g. total tCO2e per line) as separate datapoint entries — do NOT combine them into a single value.
8. CROSS-TABLE EXTRACTION: When a document has multiple tables (e.g. Table 1 = invoice details, Table 2 = GHG data), correlate rows across tables by matching identifiers (line numbers, product references) and merge all fields into a single record per item.

9b. **`unit` = MEASUREMENT UNITS ONLY.** The `unit` field on a field is for a real measurement unit (kg, km, kWh, litre, nights, THB, USD, …). NEVER stuff a field label like `"hotel_name"`, `"origin"`, `"description"` into `unit`. For text-only fields (names, codes, addresses) leave `unit` as `null` or `""`. Putting labels into `unit` corrupts the data warehouse modal cells.

9c. **EXPLAIN HOW GHG WAS / WOULD BE CALCULATED + CITE A REAL SOURCE.** Per record, output FOUR fields:

   • `ghg_calculation` — short Thai+English sentence stating *the formula*. e.g. `"distance_km × 0.18 kgCO₂e/km → kgCO₂e per trip"`.

   • `ghg_ef_value` — the numeric emission factor you actually used (e.g. `0.18`).
   • `ghg_ef_unit`  — the EF unit (e.g. `"kgCO2e/km"`, `"kgCO2e/kWh"`, `"kgCO2e/night"`, `"kgCO2e/THB"`).

   • `ghg_source_name` — the publication name (e.g. `"DEFRA 2024 GHG Conversion Factors — Passenger car (average)"`, `"TGO 2023 Grid Emission Factor for Thailand"`, `"IPCC AR6 WG3 Annex II — Hotel night global average"`).

   • `ghg_source_url` — a **real, currently-working URL** that the user can open in a browser to verify the EF. Pick from authoritative sources only; never invent a URL. Trusted roots:
       – DEFRA UK conversion factors:  https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting
       – TGO Thailand:                  https://thaicarbonlabel.tgo.or.th/  ·  https://ghgreduction.tgo.or.th/
       – IPCC reports:                  https://www.ipcc.ch/
       – US EPA emission factors hub:   https://www.epa.gov/climateleadership/ghg-emission-factors-hub
       – IEA:                           https://www.iea.org/data-and-statistics
       – Ecoinvent (public summary):    https://ecoinvent.org/
       – GHG Protocol scope 3 calc:     https://ghgprotocol.org/scope-3-calculation-guidance-2

     If you don't know a precise URL, pick the deepest authoritative root that's verifiable (the DEFRA collection page above, the TGO label site, the EPA hub) — never guess a fake page slug.

   When the record is insufficient, still output the formula + EF + source you *would* apply once the missing field arrives — that lets the user know exactly what to track next AND where the standard came from.

9. **GHG-SUFFICIENCY STEP-THINKING.** For EVERY record, you MUST think out loud (in `ghg_thinking`) about whether the record has the activity data needed to compute kgCO₂e:

     • Cat 6 flight  → needs distance OR (origin+destination+class) OR flight count.
     • Cat 6 hotel   → needs nights OR room-nights.
     • Cat 6 taxi    → needs km.
     • Cat 4 / 9 transport → needs (weight × distance) OR tonne-km.
     • Cat 5 / 10 / 12 waste/products → needs weight (kg / tonne).
     • Cat 3 / 8 / 11 / 13 energy / leased / use-phase → needs kWh / litre / m².
     • Cat 7 commute → needs km or passenger-km.
     • Cat 1 / 2 / 14 / 15 → spend-based is acceptable; THB/USD alone is OK.

   If the record has only a currency value for a category that needs physical activity data (e.g. a flight ticket showing only THB amount), declare `ghg_required_fields` as `["distance_km"]` (or whichever field is needed) and DO NOT pretend the spend gives a credible GHG number for that category. The backend will mark the record as `insufficient` and surface that to the user — better honest than wrong.

   Output per record:
     • `ghg_thinking`  — 1–2 sentences explaining what activity data is in the record and what's missing.
     • `ghg_required_fields` — array of field names needed to compute kgCO₂e if currently insufficient. Empty array means the record HAS what it needs.

Respond in JSON format ONLY:
{{
    "records": [
        {{
            "record_label": "<short label for this record, e.g. asset name or row identifier>",
            "category_id": <int>,
            "category_name": "<name>",
            "subcategory_id": <int>,
            "subcategory_name": "<name>",
            "ghg_thinking": "<1-2 sentences: does this record have the activity data needed to compute kgCO2e? What's present, what's missing?>",
            "ghg_calculation": "<the formula you would use, e.g. 'distance_km × 0.18 kgCO2e/km' or 'nights × ~25 kgCO2e/night'>",
            "ghg_ef_value": <numeric EF you applied, e.g. 0.18>,
            "ghg_ef_unit": "<unit of the EF, e.g. 'kgCO2e/km' or 'kgCO2e/kWh'>",
            "ghg_source_name": "<publication name, e.g. 'DEFRA 2024 GHG Conversion Factors — Passenger car (average)'>",
            "ghg_source_url": "<a REAL working URL to the standard, never invented>",
            "ghg_required_fields": ["<field needed>", "..."],
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
        "document_type": "<short Thai/English doc-class label, e.g. 'ใบเสร็จรับเงิน', 'ใบกำกับภาษี', 'ใบแจ้งหนี้', 'Boarding pass', 'Utility bill', 'Waste manifest' — DO NOT put the vendor name here>",
        "vendor": "<the SELLER / ISSUER company name (e.g. 'บจก. มีสุข เซอร์วิสแอนด์ซัพพลาย', 'Grab', 'Bangchak') — NOT the document type>",
        "document_date": "<YYYY-MM-DD or null>",
        "location": "<location or null>",
        "reference_number": "<invoice/receipt number or null>",
        "total_amount": <numeric — the GRAND TOTAL of the entire document (sum of every line item, NOT one SKU). For receipts/invoices this is the bottom-line "total" / "รวมเงิน" / "ยอดสุทธิ" amount. Null if not present>,
        "currency": "<ISO currency code, e.g. 'THB', 'USD'>",
        "line_item_count": <int — how many distinct line items were on the document>
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
- If no ESG data found, return {{"records": [], "totals": [], "refs": {{}}, "additional_info": [], "document_summary": "ไม่พบข้อมูล ESG"}}

CRITICAL — DO NOT confuse these refs fields (common LLM errors with Thai receipts):

  • `refs.document_type` is the **kind of document**, e.g. "ใบเสร็จรับเงิน",
    "ใบกำกับภาษี", "ใบแจ้งหนี้", "Receipt", "Tax invoice", "Boarding pass",
    "Utility bill". It is NEVER a company name. Common Thai doc types:
    ใบเสร็จรับเงิน / ใบกำกับภาษี / ใบแจ้งหนี้ / ใบส่งของ / ใบเสนอราคา.

  • `refs.vendor` is the **seller / issuer company name** (e.g. "บจก.
    มีสุข เซอร์วิสแอนด์ซัพพลาย", "Grab Taxi", "การไฟฟ้านครหลวง"). Look at
    the "ได้รับเงินจาก" / "From" / "ผู้ขาย" / letterhead area. NEVER set
    vendor to a doc-type word like "ใบเสร็จรับเงิน".

  • `refs.total_amount` is the **GRAND TOTAL of the whole document** —
    the sum of every line. On Thai receipts it sits at the bottom near
    "รวมเงิน" / "ยอดสุทธิ" / "Total". It is NEVER one line item's price.
    Example: a receipt with 5 lines (18,500 + 4,200 + 550 + 550 +
    1,500 = 25,300 THB) → use 25,300, NOT 18,500.

  • `line_item_count` — count distinct rows in the items table.

  • Records: produce ONE record per line item that maps to a Scope 3
    category. 5 SKUs all under "Purchased goods" (cat 1) → 5 records
    under cat 1 (do not merge into a single 'unit-count' record). This
    preserves per-line cost and SKU description.

  • Currency consistency: all monetary fields use the same currency.
    Inspect the document for "บาท" / "฿" / "$" / "USD" symbols and set
    `refs.currency` once based on what the document actually shows.
    Never invent a currency that isn't on the page."""

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
    # RECORD-CENTRIC PERSISTENCE (esg_records)
    # ==========================================

    def _validate_datapoints_against_db(
        self, fields: List[Dict], category_id: Optional[int],
    ) -> List[Dict]:
        """
        For each LLM-emitted field, look up its `datapoint_id` (or
        match by name) against EsgDatapoint. Drop fields that match
        nothing AND have no descriptive tags either — those are pure
        hallucinations. For the rest, attach `canonical_name` and
        `is_canonical` flags so the modal can render them properly.
        """
        if not fields:
            return []

        # Pre-load datapoints for this category for name-fuzzy matching
        canonical_by_id: Dict[int, EsgDatapoint] = {}
        canonical_by_name: Dict[str, EsgDatapoint] = {}
        if category_id:
            try:
                rows = (
                    self.db.query(EsgDatapoint)
                    .join(EsgDataSubcategory,
                          EsgDatapoint.esg_data_subcategory_id == EsgDataSubcategory.id)
                    .filter(EsgDataSubcategory.esg_data_category_id == category_id,
                            EsgDatapoint.is_active == True)
                    .all()
                )
                for r in rows:
                    canonical_by_id[r.id] = r
                    canonical_by_name[(r.name or '').strip().lower()] = r
            except Exception:
                logger.exception('Failed loading canonical datapoints for cat=%s', category_id)

        validated = []
        for f in fields:
            dp_id = f.get('datapoint_id')
            dp_name = (f.get('datapoint_name') or '').strip()
            tags = f.get('tags') or []

            canonical = None
            if dp_id and dp_id in canonical_by_id:
                canonical = canonical_by_id[dp_id]
            elif dp_name:
                canonical = canonical_by_name.get(dp_name.lower())

            f['_canonical_name'] = canonical.name if canonical else None
            f['_canonical_id'] = canonical.id if canonical else None
            f['_is_canonical'] = bool(canonical)

            # Drop only when EVERYTHING is missing (no name, no tags, no value).
            # Otherwise we keep the field and surface it on the modal.
            if not dp_name and not tags and f.get('value') in (None, ''):
                continue
            validated.append(f)
        return validated

    def _create_records(
        self,
        records: List[Dict],
        org_id: int,
        line_user_id: str,
        s3_url: str,
        refs: Dict,
        extraction_id: Optional[int],
    ) -> List[Dict]:
        """
        Persist each record as one EsgRecord row with a JSONB
        `datapoints` array. Run GHG sufficiency analysis per record.
        Returns list of to_dict() representations (for response).
        """
        from ...models.esg.data_hierarchy import EsgDataCategory

        out: List[Dict] = []
        doc_date = None
        if refs.get('document_date'):
            try:
                doc_date = datetime.strptime(refs['document_date'], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                doc_date = datetime.now(timezone.utc).date()

        for rec in records:
            if rec.get('_is_total'):
                continue

            cat_id = rec.get('category_id')
            cat_name = rec.get('category_name', '') or 'Unknown'
            sub_id = rec.get('subcategory_id')
            rec_label = (rec.get('record_label') or '').strip() or 'รายการ'

            # Resolve scope3_category_id + pillar from the DB.
            scope3_id = None
            pillar = None
            if cat_id:
                try:
                    cat_row = self.db.query(EsgDataCategory).filter(
                        EsgDataCategory.id == cat_id,
                    ).first()
                    if cat_row:
                        scope3_id = int(cat_row.scope3_category_id) if cat_row.scope3_category_id else None
                        pillar = cat_row.pillar
                except Exception:
                    logger.exception('cat lookup failed for cat_id=%s', cat_id)

            fields = rec.get('fields') or []
            fields = self._validate_datapoints_against_db(fields, cat_id)

            # Build datapoints JSONB array — every field the LLM emitted
            # with stable canonical-name annotation.
            dp_array = []
            currency = None
            for f in fields:
                value = f.get('value')
                unit = (f.get('unit') or '').strip() or None
                tags = f.get('tags') or []
                # Pick currency from tags if present
                if currency is None:
                    for t in tags:
                        if isinstance(t, str) and t.upper() in {
                            'THB', 'USD', 'EUR', 'GBP', 'JPY', 'CNY', 'SGD',
                            'HKD', 'AUD', 'KRW',
                        }:
                            currency = t.upper()
                            break

                dp_array.append({
                    'datapoint_id': f.get('_canonical_id') or f.get('datapoint_id'),
                    'datapoint_name': f.get('datapoint_name') or '',
                    'canonical_name': f.get('_canonical_name'),
                    'is_canonical': bool(f.get('_is_canonical')),
                    'value': value,
                    'unit': unit,
                    'confidence': f.get('confidence'),
                    'tags': tags,
                })

            # GHG sufficiency analysis — does this record have what we need?
            ghg = self.carbon.evaluate_record_ghg(
                scope3_category_id=scope3_id,
                category_id=cat_id,
                category_name=cat_name,
                datapoints=dp_array,
            )

            # Merge LLM-side step-thinking when present. The LLM's
            # `ghg_thinking` is a Thai/English natural-language
            # explanation; `ghg_required_fields` lists the activity
            # data it thinks is missing. We trust the evaluator for the
            # numeric kgCO2e but layer the LLM reasoning on top so the
            # user sees a coherent explanation in the analysis card.
            llm_thinking = (rec.get('ghg_thinking') or '').strip()
            llm_calc = (rec.get('ghg_calculation') or '').strip()
            llm_missing = rec.get('ghg_required_fields') or []

            # EF citation — only persist when the LLM gave us a URL
            # that actually looks like a URL. Reject obvious garbage so
            # the modal never renders a broken link.
            llm_source_name = (rec.get('ghg_source_name') or '').strip() or None
            llm_source_url_raw = (rec.get('ghg_source_url') or '').strip()
            llm_source_url = (
                llm_source_url_raw
                if llm_source_url_raw.startswith(('http://', 'https://'))
                else None
            )
            try:
                llm_ef_value = (
                    float(rec.get('ghg_ef_value'))
                    if rec.get('ghg_ef_value') not in (None, '')
                    else None
                )
            except (TypeError, ValueError):
                llm_ef_value = None
            llm_ef_unit = (rec.get('ghg_ef_unit') or '').strip() or None

            # Only override the carbon-service's per-category default
            # citation when the LLM actually supplied a value. Otherwise
            # keep the default — gives every record a verifiable EF
            # source even if the LLM was silent.
            if llm_source_name:
                ghg['source_name'] = llm_source_name
            if llm_source_url:
                ghg['source_url'] = llm_source_url
            if llm_ef_value is not None:
                ghg['ef_value'] = llm_ef_value
            if llm_ef_unit:
                ghg['ef_unit'] = llm_ef_unit
            if isinstance(llm_missing, list) and llm_missing:
                merged = list(ghg.get('missing_fields') or [])
                for m in llm_missing:
                    if m and m not in merged:
                        merged.append(m)
                ghg['missing_fields'] = merged

            # Compose a single human-readable reason. Always include the
            # LLM's calculation formula when present — that's the most
            # actionable piece for the user (it tells them what we did
            # or what we'd need). Falls back to the evaluator's reason.
            base_reason = ghg.get('reason') or ''
            parts = []
            if llm_calc:
                parts.append(f'การคำนวณ: {llm_calc}')
            if llm_thinking:
                parts.append(llm_thinking)
            if base_reason:
                parts.append(base_reason)
            if parts:
                ghg['reason'] = '  ·  '.join(parts)
            # Also persist the formula on its own column for the
            # analysis-card / modal-tooltip consumers.
            ghg['llm_calculation'] = llm_calc or None

            row = EsgRecord(
                organization_id=org_id,
                line_user_id=line_user_id,
                user_id=None,
                extraction_id=extraction_id,
                evidence_image_url=s3_url,
                file_key=s3_url,
                category_id=cat_id,
                subcategory_id=sub_id,
                scope3_category_id=scope3_id,
                pillar=pillar,
                record_label=rec_label,
                entry_date=doc_date or datetime.now(timezone.utc).date(),
                datapoints=dp_array,
                kgco2e=ghg.get('kgco2e'),
                ghg_status=ghg.get('status') or GhgStatus.PENDING,
                ghg_method=ghg.get('method'),
                ghg_missing_fields=ghg.get('missing_fields') or [],
                ghg_reason=ghg.get('reason'),
                ghg_source_name=ghg.get('source_name'),
                ghg_source_url=ghg.get('source_url'),
                ghg_ef_value=ghg.get('ef_value'),
                ghg_ef_unit=ghg.get('ef_unit'),
                currency=currency,
                status='PENDING_VERIFY',
                entry_source='LINE_CHAT',
            )
            self.db.add(row)
            self.db.flush()
            out.append(row.to_dict())

        self.db.commit()
        return out

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
