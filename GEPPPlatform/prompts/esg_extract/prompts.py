"""
ESG Cascade Extraction Prompt Templates.

Used by EsgExtractionService for the 3-step cascade:
  1. Category classification
  2. Subcategory classification
  3. Datapoint extraction

These prompts come in two flavours:

  *_PROMPT          — original full-ESG prompt (E + S + G), kept for the
                      'full_esg' focus mode and never deleted.
  *_PROMPT_SCOPE3   — narrowed Carbon Scope 3 prompt. Used when the
                      organization's `focus_mode` is 'scope3_only' (the
                      default). The model is explicitly instructed that
                      it MUST return `no_match` for inputs that don't
                      fit Scope 3 — it must NOT classify into Social,
                      Governance, Scope 1 or Scope 2 even when the input
                      mentions them.

The active prompt for any extraction is selected at request time by
EsgExtractionService based on the org's focus_mode setting.

The smaller taxonomy is also expected to *reduce false-positive
classifications* because the LLM no longer chooses between 100+
subcategories across three pillars.
"""

# ─── ORIGINAL FULL-ESG PROMPTS (preserved for focus_mode='full_esg') ────────

CATEGORY_CLASSIFY_PROMPT = """You are an ESG (Environmental, Social, Governance) data classifier.
Analyze the following input and determine which ESG data categories it relates to.
One input can match multiple categories.

Available categories:
{categories_json}

Input to analyze:
{input_content}

Respond in JSON format ONLY:
{{
    "matches": [
        {{
            "category_id": <int>,
            "category_name": "<name>",
            "confidence": <0.0-1.0>,
            "reasoning": "<brief explanation>"
        }}
    ]
}}

Rules:
- Include ALL categories that the input could relate to
- Minimum confidence threshold: 0.3
- If the input is not related to any ESG category, return empty matches
- Be thorough - a single receipt or document may relate to multiple categories
"""

SUBCATEGORY_CLASSIFY_PROMPT = """You are an ESG data classifier performing subcategory matching.
Given the input and the matched category, identify which subcategories the input relates to.

Category: {category_name}
Available subcategories:
{subcategories_json}

Input to analyze:
{input_content}

Respond in JSON format ONLY:
{{
    "matches": [
        {{
            "subcategory_id": <int>,
            "subcategory_name": "<name>",
            "confidence": <0.0-1.0>,
            "reasoning": "<brief explanation>"
        }}
    ]
}}

Rules:
- Include ALL subcategories that the input could satisfy
- Minimum confidence threshold: 0.3
- Consider that one document (e.g., a receipt) may relate to multiple subcategories
"""

DATAPOINT_EXTRACT_PROMPT = """You are an ESG data extraction specialist.
Extract specific data point values from the input based on the available datapoints.

Subcategory: {subcategory_name}
Available datapoints to extract:
{datapoints_json}

Input to analyze:
{input_content}

Respond in JSON format ONLY:
{{
    "matches": [
        {{
            "datapoint_id": <int>,
            "datapoint_name": "<name>",
            "value": <extracted value - number, string, or date as appropriate>,
            "unit": "<unit if applicable>",
            "confidence": <0.0-1.0>
        }}
    ],
    "refs": {{
        "document_date": "<YYYY-MM-DD or null>",
        "vendor": "<vendor/company name or null>",
        "location": "<location or null>",
        "reference_number": "<invoice/receipt/manifest number or null>"
    }}
}}

Rules:
- Extract ALL datapoints that can be found in the input
- Convert values to the expected unit (e.g., tons to kg)
- If a value is mentioned but uncertain, include it with lower confidence
- Extract reference information (date, vendor, location) when available
- For text data_type datapoints, extract the text value
- For numeric data_type datapoints, extract the number only
- For date data_type datapoints, extract in YYYY-MM-DD format
"""


# ─── SCOPE-3-ONLY PROMPTS (active when focus_mode='scope3_only') ───────────
#
# Design principles for the Scope 3 classifier (see the full reference
# table at the bottom of this file):
#
#   1. Walk the model through a four-step DECISION FLOW so it never
#      forces a fit:
#        (a) Is this a Scope 3 piece of evidence at all (vs. Scope 1/2/
#            Social/Governance/non-energy waste of an unrelated domain)?
#        (b) What is the FLOW direction? — upstream (into us), our
#            operations, or downstream (out of us toward the customer).
#        (c) What is the TEMPORAL placement? — purchase, use, or
#            end-of-life.
#        (d) Run the disambiguation rules for the categories that match
#            the flow + temporal placement.
#
#   2. Inject a canonical 15-row REFERENCE TABLE so the model has the
#      same definitions, "includes", "excludes", "typical evidence" and
#      "common confusions" we'd give a human auditor. The DB rows
#      passed into {categories_json} are merged with this canonical map
#      in esg_extraction_service._classify_categories.
#
#   3. List the most common TRAPS by name (fuel receipt vs. cat 3,
#      utility bill vs. cat 3, waste manifest vs. cat 5, lease invoice
#      vs. cat 8, travel vs. commute, etc.) so the model has prior
#      knowledge of what's most likely to be misclassified.
#
#   4. Force structured output with an `evidence_type` field, so we can
#      log how the model perceived the input — useful for false-positive
#      audits later.

CATEGORY_CLASSIFY_PROMPT_SCOPE3 = """You are a Carbon Scope 3 emissions classifier following the GHG Protocol Corporate Value Chain (Scope 3) Standard. Your job is to assign one or more of the 15 Scope 3 categories (1–15) to a piece of evidence (an invoice, receipt, bill, manifest, statement, etc.) — but ONLY when the evidence genuinely belongs to a Scope 3 source.

You must reason like a GHG inventory auditor, not a search engine.

================================================================
STEP 1 — IS THIS SCOPE 3 AT ALL?
================================================================
Reject the input as `no_match` (return empty matches) when ANY of these are true:

  • SCOPE 1 evidence — direct combustion of fuels we own or control:
    - A fuel pump receipt for a company-owned vehicle / generator / boiler.
    - Refrigerant top-up on equipment we operate.
    - LPG / diesel delivered into our own tank for our own combustion.
    Note: the *upstream* portion of these (well-to-tank) is Scope 3 cat 3.
    Only flag cat 3 if the document explicitly addresses upstream/WTT
    factors. A bare fuel receipt with combustion volumes is Scope 1.

  • SCOPE 2 evidence — our purchased electricity / steam / heat:
    - A monthly utility bill for our office or factory.
    - District cooling invoice.
    Note: the upstream T&D losses portion is Scope 3 cat 3, but only
    when the document actually quantifies T&D / upstream EFs.

  • SOCIAL / GOVERNANCE evidence:
    - Salary slips, training certificates, diversity reports, audit
      committee minutes, anti-corruption training, shareholder docs.
    These are S/G, not Scope 3.

  • DOMAIN-IRRELEVANT evidence:
    - Personal medical records, irrelevant marketing, ID documents.

When rejected, set `evidence_type` and explain in `no_match_reason`.

================================================================
STEP 2 — FLOW DIRECTION
================================================================
Now identify how value flows around the business:

  • UPSTREAM into us — categories 1, 2, 3, 4, 5, 6, 7, 8
    (We pay; supplier or worker is the source.)

  • DOWNSTREAM out of us — categories 9, 10, 11, 12, 13, 14, 15
    (Customer / investee / franchisee is the source; sometimes we pay,
    sometimes not — see disambiguation.)

================================================================
STEP 3 — TEMPORAL PLACEMENT
================================================================
For physical product flows, decide the lifecycle stage:

  • Purchase / inbound — cat 1 (operating expense), cat 2 (capital),
    cat 4 (transport in)
  • Operation — cat 3 (fuel/energy upstream), cat 5 (waste), cat 6
    (travel), cat 7 (commute), cat 8 (leased)
  • Sale / outbound — cat 9 (transport out), cat 10 (further
    processing), cat 11 (use phase), cat 12 (end-of-life), cat 13
    (leased to others), cat 14 (franchises), cat 15 (investments)

================================================================
STEP 4 — DISAMBIGUATION RULES (READ EVERY TIME)
================================================================
These are the most common traps. Apply each rule that applies:

R1. Cat 1 vs Cat 2 (purchases):
    - Cat 2 is for CAPEX entering a fixed-asset register
      (manufacturing equipment, vehicles bought, IT hardware as capex,
      buildings purchased).
    - Cat 1 is for OPEX consumed in the year (raw materials, services,
      software subscriptions, office supplies, professional services).
    - Default to cat 1 unless the evidence is clearly capital.

R2. Cat 4 vs Cat 9 (transport):
    - Cat 4 — INBOUND freight WE arranged or paid for (DDP imports,
      our own freight forwarder invoice, raw material delivery cost).
    - Cat 9 — OUTBOUND freight when WE did NOT pay (FOB exports the
      customer organised, or a downstream distribution flow we don't
      finance).
    - Look at INCOTERMS, "ship to / ship from", who's billed.

R3. Cat 3 (fuel/energy upstream) is NEVER triggered by a bare fuel
    receipt or electricity bill. Trigger ONLY when the document is
    about well-to-tank, T&D losses, supplier-specific upstream EFs,
    or an explicit upstream allocation.

R4. Cat 5 (waste in operations):
    - Waste hauler invoice / manifest / certificate of destruction
      from OUR facilities → cat 5.
    - Customer disposing of OUR sold product → cat 12 (NOT cat 5).
    - Burning waste in OUR own incinerator → Scope 1, not cat 5.

R5. Cat 6 vs Cat 7 (travel):
    - Cat 6 — employer-paid business travel (TMC report, expense
      report with airline/hotel, conference travel).
    - Cat 7 — daily home↔work commuting (HR commute survey, transit
      pass benefits, parking allowance).
    - One-off site visit paid by employer → cat 6, not cat 7.

R6. Cat 8 vs Scope 1/2 (leased assets):
    - We OPERATIONALLY control the leased asset (we manage day-to-day
      use of the building/equipment) → already in our Scope 1+2 → NOT
      cat 8.
    - Landlord controls and bills us a flat fee with no sub-meter →
      cat 8.
    - When in doubt, prefer cat 8 only when the document explicitly
      shows landlord-controlled operations (e.g. office in a serviced
      building, lessor-managed equipment with operator).

R7. Cat 11 (use of sold) vs Scope 1:
    - Customer using a product we MANUFACTURED → cat 11.
    - Us using a product we manufactured → Scope 1, not cat 11.
    - Product datasheet quoting energy/fuel during use phase → cat 11.

R8. Cat 12 vs Cat 5:
    - Our offcuts, scrap, packaging waste from production → cat 5.
    - Customer disposing of single-use or end-of-life products we
      sold them → cat 12.
    - Take-back program records → cat 12.

R9. Cat 13 (leased OUT) vs Cat 8 (leased IN):
    - Cat 8 = WE are tenant/lessee.
    - Cat 13 = WE are landlord/lessor; tenant operates the asset.
    - Cat 13 is for landlords, mall operators, equipment lessors.

R10. Cat 14 (franchises) — only for the FRANCHISOR. Royalty
     statements, franchisee utility submissions, brand-licensed store
     reports.

R11. Cat 15 (investments) — for investors, banks, insurers. Portfolio
     holdings, fund statements, equity stakes, project finance.
     Loan/insurance documents we received as a customer → not cat 15.

================================================================
STEP 5 — OUTPUT
================================================================
Available categories (THIS is the ONLY list you may classify into;
the canonical reference table is the source of truth — DB rows are
provided for ID stability):
{categories_json}

Input to analyze:
{input_content}

Output STRICT JSON only — no prose, no markdown:
{{
    "evidence_type": "<short label, e.g. 'fuel_receipt', 'travel_agency_invoice', 'waste_manifest', 'salary_slip', 'electricity_bill', 'shipping_bill_of_lading', 'capital_purchase_order', 'lease_invoice', 'investee_holding_statement', 'unknown'>",
    "flow": "<one of: upstream | operations | downstream | non_scope3>",
    "matches": [
        {{
            "category_id": <int matching one of the listed categories>,
            "category_name": "<exact name from the list>",
            "confidence": <0.0-1.0>,
            "reasoning": "<one short sentence citing the disambiguation rule that applied, e.g. 'R2: customer pays freight (FOB), so downstream cat 9'>"
        }}
    ],
    "no_match_reason": "<set ONLY when matches is empty; otherwise empty string. State which step rejected (e.g. 'STEP 1: Scope 1 fuel receipt — combustion volumes only, no upstream allocation')>"
}}

Final rules:
- Minimum confidence threshold per match: 0.3
- ONE evidence document MAY match multiple categories (e.g. a multi-line
  invoice with both raw materials [cat 1] and freight [cat 4]). Be
  thorough WITHIN the list.
- If the input is genuinely not Scope 3, prefer EMPTY matches with a
  clear no_match_reason over a low-confidence forced fit.
- Always cite the rule (R1..R11) you applied in `reasoning`.
"""

SUBCATEGORY_CLASSIFY_PROMPT_SCOPE3 = """You are a Carbon Scope 3 data classifier performing subcategory matching.
Given the input and the matched Scope 3 category, identify which subcategories the input relates to.

Scope 3 Category: {category_name}
Available subcategories (this is the ONLY list you may classify into):
{subcategories_json}

Input to analyze:
{input_content}

Respond in JSON format ONLY:
{{
    "matches": [
        {{
            "subcategory_id": <int>,
            "subcategory_name": "<name>",
            "confidence": <0.0-1.0>,
            "reasoning": "<brief explanation>"
        }}
    ]
}}

Rules:
- Include ALL subcategories that the input could satisfy
- Minimum confidence threshold: 0.3
- You MUST choose only from the listed subcategories — do not invent new ones
- If the input doesn't fit any subcategory, return empty matches
"""

DATAPOINT_EXTRACT_PROMPT_SCOPE3 = DATAPOINT_EXTRACT_PROMPT


# ─── CANONICAL SCOPE 3 REFERENCE TABLE ─────────────────────────────────────
#
# Single source of truth for what each of the 15 GHG-Protocol Scope 3
# categories means, with includes / excludes / typical evidence /
# common confusions per row.
#
# At classification time (esg_extraction_service._classify_categories),
# we MERGE this table with the DB rows in `categories_json`, so the
# LLM sees both the stable ID from the database AND the rich
# disambiguation context — without us having to hard-code that into the
# DB or migrate it across environments.

SCOPE3_CATEGORY_REFERENCE: dict[int, dict] = {
    1: {
        'tier': 'upstream',
        'definition': 'Cradle-to-gate emissions of all goods and services we PURCHASED that were CONSUMED or used in operations during the year (operating expense, not capital).',
        'includes': [
            'Raw materials, components, packaging',
            'IT/software subscriptions, cloud, SaaS',
            'Office supplies, consumables',
            'Professional services (consulting, legal, accounting, marketing agencies)',
            'Maintenance and repair services',
        ],
        'excludes': [
            'Capital purchases (→ cat 2)',
            'Freight cost paid separately (→ cat 4)',
            'Energy / fuel (→ cat 3 upstream + Scope 1/2 direct)',
        ],
        'typical_evidence': ['vendor invoice', 'procurement PO', 'opex spend report', 'SaaS receipt', 'bill of materials'],
        'common_confusions': ['cat 2 (capex vs opex)', 'cat 4 (separately invoiced freight)'],
    },
    2: {
        'tier': 'upstream',
        'definition': 'Cradle-to-gate emissions of CAPITAL goods we purchased — long-lived assets that enter the fixed-asset register.',
        'includes': [
            'Manufacturing equipment / machinery',
            'Vehicles purchased (not leased)',
            'IT hardware booked as capex (servers, laptops if capitalised)',
            'Buildings / land improvements purchased',
        ],
        'excludes': [
            'Operating expenses (→ cat 1)',
            'Leased equipment / facilities (→ cat 8 if not in Scope 1/2)',
        ],
        'typical_evidence': ['fixed-asset register entry', 'capital purchase order', 'equipment invoice with capex tag', 'EPD / LCA from manufacturer'],
        'common_confusions': ['cat 1 (when document doesn\'t state capex/opex)'],
    },
    3: {
        'tier': 'upstream',
        'definition': 'Upstream emissions from FUELS and ENERGY we purchased — well-to-tank, T&D losses, generation upstream — but NOT the direct combustion/use itself (those are Scope 1/2).',
        'includes': [
            'Well-to-tank emission factors applied to fuel consumed',
            'Grid electricity transmission & distribution losses',
            'Upstream of district cooling / steam',
            'Generator-specific upstream EFs from a renewable PPA',
        ],
        'excludes': [
            'Direct combustion in our equipment (→ Scope 1)',
            'Purchased electricity used in our facilities (→ Scope 2)',
            'A bare fuel pump receipt or utility bill — that is Scope 1/2 evidence; cat 3 is the *upstream* allocation, only flag when document is explicitly about it',
        ],
        'typical_evidence': ['well-to-tank EF table', 'TGO grid upstream factor doc', 'utility upstream allocation report'],
        'common_confusions': ['Scope 1 (fuel receipts)', 'Scope 2 (electricity bills)'],
    },
    4: {
        'tier': 'upstream',
        'definition': 'Transportation and distribution of products PURCHASED by us, between tier-1 suppliers and our operations — when WE pay for or arranged the freight.',
        'includes': [
            'Inbound freight forwarder invoice',
            'Sea / air / road / rail bills of lading where shipper = us',
            'DDP imports (we pay through to delivery)',
            'Same-mode logistics for raw materials we order',
        ],
        'excludes': [
            'Outbound freight to customers (→ cat 9)',
            'Freight cost embedded in the product price with no separate invoice (often left in cat 1)',
            'Customer-arranged inbound (FOB exports they paid for)',
        ],
        'typical_evidence': ['inbound freight invoice', 'bill of lading with us as consignee', 'INCOTERMS DDP/CIF docs'],
        'common_confusions': ['cat 9 (direction)', 'cat 1 (when freight bundled into goods invoice)'],
    },
    5: {
        'tier': 'upstream',
        'definition': 'Disposal and treatment of waste generated in OUR operations (including third-party operated assets we report under Scope 3).',
        'includes': [
            'Hauler invoice / waste manifest',
            'Wastewater treatment service from us',
            'Recycling pickup records by stream (organic, recyclable, general, hazardous)',
            'Certificate of destruction',
        ],
        'excludes': [
            'Customer disposing of products we sold (→ cat 12)',
            'Burning waste in OUR own incinerator (→ Scope 1)',
            'Suppliers\' waste (their cat 5)',
        ],
        'typical_evidence': ['monthly waste manifest', 'recycling report', 'GEPP-Business waste log'],
        'common_confusions': ['cat 12 (whose waste — ours vs customers\')'],
    },
    6: {
        'tier': 'upstream',
        'definition': 'EMPLOYER-PAID business travel — flights, hotels, ground transport for work trips.',
        'includes': [
            'Travel agency / TMC monthly report',
            'Employee expense reports with airline/route/class',
            'Business hotel folios',
            'Conference travel receipts',
        ],
        'excludes': [
            'Daily home↔work commuting (→ cat 7)',
            'Personal travel reimbursed for non-work reasons',
            'Travel arranged by a customer/franchisee (their cat 6)',
        ],
        'typical_evidence': ['TMC report', 'expense report with airfare', 'hotel folio with corporate billing'],
        'common_confusions': ['cat 7 (commute vs trip)'],
    },
    7: {
        'tier': 'upstream',
        'definition': 'Daily home-to-work travel of employees, where employer does NOT pay the journey.',
        'includes': [
            'Annual commute survey (mode + distance + days/week)',
            'Transit / parking benefits as proxy data',
            'WFH-day adjustments to commuting averages',
        ],
        'excludes': [
            'Business travel (→ cat 6)',
            'Travel during a work day between sites if employer pays (→ cat 6)',
        ],
        'typical_evidence': ['HR commute survey', 'transit pass benefit records', 'WFH policy doc'],
        'common_confusions': ['cat 6 (occasional vs daily)'],
    },
    8: {
        'tier': 'upstream',
        'definition': 'Scope 1+2 emissions of leased assets WE OPERATE that are NOT in our consolidated operational boundary (i.e. lessor-controlled).',
        'includes': [
            'Office in a serviced building where landlord controls HVAC and bills a flat fee',
            'Equipment leased with operator (lessor manages it)',
            'Coworking / shared facility flat fee',
        ],
        'excludes': [
            'Leases where WE manage day-to-day operations and energy is sub-metered (already in Scope 1/2)',
            'Assets we lease OUT to others (→ cat 13)',
        ],
        'typical_evidence': ['lease agreement', 'lessor utility allocation', 'flat-fee facility invoice'],
        'common_confusions': ['Scope 1/2 (operational control test)', 'cat 13 (direction)'],
    },
    9: {
        'tier': 'downstream',
        'definition': 'Transportation and distribution of products SOLD by us, paid for by the customer or by a downstream party (NOT us).',
        'includes': [
            'Last-mile delivery in B2C ecommerce when carrier bills the customer',
            'FOB exports — customer arranges international freight',
            'Distributor inventory transfers paid by distributor',
        ],
        'excludes': [
            'Inbound freight we paid for (→ cat 4)',
            'Outbound freight WE paid (often left in cat 4 by some methodologies)',
        ],
        'typical_evidence': ['shipping records with destination + weight + mode', 'carrier API integration reports', 'FOB INCOTERMS export docs'],
        'common_confusions': ['cat 4 (direction + who pays)'],
    },
    10: {
        'tier': 'downstream',
        'definition': 'Emissions when our customer FURTHER PROCESSES the intermediate goods we sold them, before they reach the end consumer.',
        'includes': [
            'Steel mill we sold to → forging / rolling',
            'Plastic resin we sold → injection moulding',
            'Component we sold → final assembly',
        ],
        'excludes': [
            'Customer simply USING our final product (→ cat 11)',
            'Disposal of our product (→ cat 12)',
        ],
        'typical_evidence': ['industry-association LCA covering downstream processing', 'customer-supplied processing energy data'],
        'common_confusions': ['cat 11 (process vs use)'],
    },
    11: {
        'tier': 'downstream',
        'definition': 'Emissions from the CUSTOMER OPERATING our final product over its lifetime — energy, fuel, refrigerant.',
        'includes': [
            'Electricity used by sold appliances / electronics over lifetime',
            'Fuel burned by sold vehicles or generators',
            'Combustion emissions from sold fuels (gasoline → end use)',
        ],
        'excludes': [
            'US using a product we manufactured (→ Scope 1)',
            'Customer further processing intermediate goods (→ cat 10)',
            'Customer disposing of product (→ cat 12)',
        ],
        'typical_evidence': ['product datasheet with rated energy use', 'energy-label certifications (ENERGY STAR, EU)', 'IoT telemetry of installed base'],
        'common_confusions': ['Scope 1 (whose hands)', 'cat 10 (operate vs further-process)'],
    },
    12: {
        'tier': 'downstream',
        'definition': 'End-of-life disposal of products we SOLD, after the customer is done using them.',
        'includes': [
            'Customer-discarded packaging waste',
            'End-of-life appliance recycling / landfill',
            'Take-back program records',
            'Country-mix EOL allocations applied to volumes sold',
        ],
        'excludes': [
            'Our own operational waste (→ cat 5)',
            'Refurbishment / second-life programs run by us (cat 5 or cat 12 depending on framing — prefer cat 12)',
        ],
        'typical_evidence': ['product weight + material composition', 'take-back program records', 'extended-producer-responsibility submissions'],
        'common_confusions': ['cat 5 (whose waste)'],
    },
    13: {
        'tier': 'downstream',
        'definition': 'Operations of assets WE LEASE OUT to other businesses — we are landlord/lessor.',
        'includes': [
            'Tenant utility data in a building we own and rent out',
            'Equipment lessor with operator',
            'Mall operator → tenants\' Scope 1+2',
        ],
        'excludes': [
            'Assets we lease IN (→ cat 8)',
            'Sale of equipment outright (→ cat 11 use phase)',
        ],
        'typical_evidence': ['tenant utility data with permission', 'sub-meter readings', 'lease ledger'],
        'common_confusions': ['cat 8 (direction)'],
    },
    14: {
        'tier': 'downstream',
        'definition': 'Scope 1+2 emissions of franchisees operating under OUR brand. Reportable by the FRANCHISOR.',
        'includes': [
            'Franchisee utility-bill submissions',
            'Annual franchisee energy survey',
            'Royalty statements when used as a proxy for footprint allocation',
        ],
        'excludes': [
            'OUR own owned-store Scope 1+2 (already in Scope 1/2)',
            'Documents from a franchisee\'s perspective (their own Scope 1/2)',
        ],
        'typical_evidence': ['franchisee energy survey', 'royalty statement with revenue', 'brand-licensed store report'],
        'common_confusions': ['Scope 1/2 (whose stores — owned vs franchised)'],
    },
    15: {
        'tier': 'downstream',
        'definition': 'Emissions of companies WE INVEST IN, attributed to our share. PCAF methodology.',
        'includes': [
            'Listed-equity holdings × investee Scope 1+2 × ownership share',
            'Loan portfolio attribution',
            'Project finance attributable emissions',
            'Insurance underwriting (where applicable)',
        ],
        'excludes': [
            'Loans / insurance documents we received as a CUSTOMER (not cat 15)',
            'Internal capex (→ cat 2)',
        ],
        'typical_evidence': ['portfolio holdings statement', 'investee sustainability report', 'PCAF data quality scores', 'fund factsheet'],
        'common_confusions': ['cat 2 (whose investment)'],
    },
}


def augment_categories_for_prompt(db_rows: list[dict]) -> list[dict]:
    """
    Merge canonical Scope 3 reference fields into the DB category rows
    before serializing into {categories_json} for the prompt.

    The DB row provides stable id + name. The canonical map provides
    definition / includes / excludes / typical_evidence / common_confusions
    so the LLM has the same disambiguation context an auditor would have.
    """
    augmented: list[dict] = []
    for row in db_rows:
        scope3_id = row.get('scope3_category_id')
        ref = SCOPE3_CATEGORY_REFERENCE.get(int(scope3_id)) if scope3_id else None
        merged = {
            'id': row.get('id'),
            'name': row.get('name'),
            'pillar': row.get('pillar'),
        }
        if scope3_id:
            merged['scope3_category_id'] = int(scope3_id)
        if ref:
            merged['tier'] = ref['tier']
            merged['definition'] = ref['definition']
            merged['includes'] = ref['includes']
            merged['excludes'] = ref['excludes']
            merged['typical_evidence'] = ref['typical_evidence']
            merged['common_confusions'] = ref['common_confusions']
        elif row.get('description'):
            merged['definition'] = row['description']
        augmented.append(merged)
    return augmented

