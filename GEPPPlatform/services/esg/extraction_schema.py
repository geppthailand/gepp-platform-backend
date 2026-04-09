"""
ESG Extraction JSONB Schema — Compact key format for `structured_data` column.

One extraction record = one document.
Inside: list of rows, each row has list of datapoint values.

Structure (stored in `structured_data` JSONB):
{
    "rows": [                           # list of data rows from the document
        {
            "lbl": "Steel Coil #8821",  # row label (short identifier)
            "cat": 3,                   # esg_data_category.id
            "sub": 15,                  # esg_data_subcategory.id
            "attrs": [                  # list of datapoint values
                {
                    "dp": 101,          # esg_datapoint.id
                    "v": "Steel Coil",  # value (str | int | float | bool)
                    "u": null,          # unit (str | null)
                    "c": 95,            # confidence 0-100 (int, saves space vs float)
                    "t": "text",        # data type: "text" | "num" | "date"
                    "cur": null,        # currency code if monetary (e.g. "USD")
                    "tags": ["material"]# optional tags for extra context
                },
                {"dp": 105, "v": 20, "u": "MT", "c": 100, "t": "num"},
                {"dp": 113, "v": 1200, "u": "USD/MT", "c": 90, "t": "num", "cur": "USD"}
            ],
            "atm": {                    # attribute_metadata (per-row)
                "src": "Table 1, Row 1",# source location in document
                "dt": "2023-09-23",     # row-level date (if different from doc)
                "ref": "P.O. #8821"     # row-level reference
            }
        }
    ],
    "tots": [                           # totals found in document
        {"lbl": "Total GHG", "v": 9.75, "u": "tCO2e"},
        {"lbl": "Total Amount", "v": 66000, "u": "USD", "cur": "USD"}
    ],
    "dm": {                             # document_metadata
        "dt": "2023-10-28",            # document_date
        "vnd": "Global Processing Partners",  # vendor
        "loc": "Advanced Mfg Zone, IL",# location
        "ref": "GPP-2023-0112",        # reference/invoice number
        "sum": "ใบแจ้งหนี้ค่าบริการ..",  # 1-sentence Thai summary
        "cur": "USD",                  # default currency
        "typ": "invoice"               # document type
    },
    "add": [                            # additional_info (methodology, footnotes, etc.)
        {"lbl": "Emission Methodology", "v": "Detailed calculation...", "sec": "Summary"}
    ],
    "ver": 2                            # schema version for future migration
}

Key abbreviations:
    rows    = data rows
    lbl     = label
    cat     = category_id
    sub     = subcategory_id
    attrs   = attributes (datapoint values)
    dp      = datapoint_id
    v       = value
    u       = unit
    c       = confidence (0-100)
    t       = data type (text/num/date)
    cur     = currency
    tags    = context tags
    atm     = attribute_metadata (per-row)
    src     = source location in doc
    dt      = date
    ref     = reference
    tots    = totals
    dm      = document_metadata
    vnd     = vendor
    loc     = location
    sum     = summary
    typ     = document type
    add     = additional_info
    sec     = section
    ver     = schema version
"""

SCHEMA_VERSION = 2


# ---------------------------------------------------------------------------
# Builder helpers — create structured_data from LLM output
# ---------------------------------------------------------------------------

def build_structured_data(rows, totals=None, doc_meta=None, additional=None):
    """Build a structured_data dict from extraction results."""
    return {
        'rows': rows or [],
        'tots': totals or [],
        'dm': doc_meta or {},
        'add': additional or [],
        'ver': SCHEMA_VERSION,
    }


def build_row(label, category_id, subcategory_id, attrs, attr_meta=None):
    """Build a single row dict."""
    row = {
        'lbl': label or '',
        'cat': category_id,
        'sub': subcategory_id,
        'attrs': attrs,
    }
    if attr_meta:
        row['atm'] = attr_meta
    return row


def build_attr(datapoint_id, value, unit=None, confidence=50,
               data_type='num', currency=None, tags=None):
    """Build a single attribute (datapoint value) dict."""
    a = {'dp': datapoint_id, 'v': value, 'c': confidence, 't': data_type}
    if unit:
        a['u'] = unit
    if currency:
        a['cur'] = currency
    if tags:
        a['tags'] = tags
    return a


def build_doc_meta(date=None, vendor=None, location=None,
                   reference=None, summary=None, currency=None, doc_type=None):
    """Build document_metadata dict."""
    dm = {}
    if date:
        dm['dt'] = date
    if vendor:
        dm['vnd'] = vendor
    if location:
        dm['loc'] = location
    if reference:
        dm['ref'] = reference
    if summary:
        dm['sum'] = summary
    if currency:
        dm['cur'] = currency
    if doc_type:
        dm['typ'] = doc_type
    return dm


# ---------------------------------------------------------------------------
# Reader helpers — extract data from structured_data for reports/queries
# ---------------------------------------------------------------------------

def iter_rows(structured_data):
    """Yield (row_index, row_dict) for each data row."""
    if not structured_data:
        return
    for i, row in enumerate(structured_data.get('rows', [])):
        yield i, row


def iter_attrs(row):
    """Yield each attribute dict from a row."""
    for attr in row.get('attrs', []):
        yield attr


def get_attr_value(row, datapoint_id):
    """Get the value of a specific datapoint from a row. Returns None if not found."""
    for attr in row.get('attrs', []):
        if attr.get('dp') == datapoint_id:
            return attr.get('v')
    return None


def get_all_attrs_by_dp(structured_data, datapoint_id):
    """Get all values for a specific datapoint across all rows. Returns list of (row_label, value, unit)."""
    results = []
    for _, row in iter_rows(structured_data):
        for attr in iter_attrs(row):
            if attr.get('dp') == datapoint_id:
                results.append((row.get('lbl', ''), attr.get('v'), attr.get('u')))
    return results


def get_doc_meta(structured_data):
    """Get document metadata."""
    if not structured_data:
        return {}
    return structured_data.get('dm', {})


def get_totals(structured_data):
    """Get totals list."""
    if not structured_data:
        return []
    return structured_data.get('tots', [])


def get_additional_info(structured_data):
    """Get additional_info list."""
    if not structured_data:
        return []
    return structured_data.get('add', [])


def get_rows_by_category(structured_data, category_id):
    """Get all rows belonging to a specific category."""
    return [row for _, row in iter_rows(structured_data) if row.get('cat') == category_id]


def get_rows_by_subcategory(structured_data, subcategory_id):
    """Get all rows belonging to a specific subcategory."""
    return [row for _, row in iter_rows(structured_data) if row.get('sub') == subcategory_id]


def flatten_for_entries(structured_data):
    """
    Flatten structured_data into a list of dicts ready for EsgDataEntry creation.
    Each attr in each row becomes one entry dict.
    Returns list of:
        {
            'category_id', 'subcategory_id', 'datapoint_id',
            'value', 'unit', 'confidence', 'data_type', 'currency',
            'row_label', 'tags', 'doc_date', 'row_date', 'row_ref'
        }
    """
    if not structured_data:
        return []

    dm = get_doc_meta(structured_data)
    doc_date = dm.get('dt')
    results = []

    for _, row in iter_rows(structured_data):
        atm = row.get('atm', {})
        row_date = atm.get('dt') or doc_date
        row_ref = atm.get('ref', '')

        for attr in iter_attrs(row):
            results.append({
                'category_id': row.get('cat'),
                'subcategory_id': row.get('sub'),
                'datapoint_id': attr.get('dp'),
                'value': attr.get('v'),
                'unit': attr.get('u', '-'),
                'confidence': attr.get('c', 50),
                'data_type': attr.get('t', 'num'),
                'currency': attr.get('cur'),
                'row_label': row.get('lbl', ''),
                'tags': attr.get('tags', []),
                'doc_date': doc_date,
                'row_date': row_date,
                'row_ref': row_ref,
            })

    return results


# ---------------------------------------------------------------------------
# Conversion: old format → new format
# ---------------------------------------------------------------------------

def from_legacy_records(records, refs=None, totals=None, additional_info=None, summary=''):
    """Convert old-format records (from existing extraction) to new structured_data."""
    rows = []
    for rec in (records or []):
        if rec.get('_is_total'):
            continue
        attrs = []
        for f in rec.get('fields', []):
            a = {
                'dp': f.get('datapoint_id'),
                'v': f.get('value'),
                'c': int((f.get('confidence', 0.5)) * 100),
                't': 'num' if f.get('_value_type') == 'numeric' else 'text',
            }
            if f.get('unit'):
                a['u'] = f['unit']
            if f.get('tags'):
                a['tags'] = f['tags']
            # detect currency from tags
            if f.get('tags'):
                currency_codes = {'USD', 'THB', 'EUR', 'GBP', 'JPY', 'CNY', 'SGD'}
                for tag in f['tags']:
                    if isinstance(tag, str) and tag.upper() in currency_codes:
                        a['cur'] = tag.upper()
                        break
            attrs.append(a)

        row = {
            'lbl': rec.get('record_label', ''),
            'cat': rec.get('category_id'),
            'sub': rec.get('subcategory_id'),
            'attrs': attrs,
        }
        rows.append(row)

    # totals
    tots = []
    for t in (totals or []):
        tot = {'lbl': t.get('label', 'Total'), 'v': t.get('value')}
        if t.get('unit'):
            tot['u'] = t['unit']
        tots.append(tot)

    # doc metadata
    r = refs or {}
    dm = build_doc_meta(
        date=r.get('document_date'),
        vendor=r.get('vendor'),
        location=r.get('location'),
        reference=r.get('reference_number'),
        summary=summary,
    )

    # additional
    add = []
    for ai in (additional_info or []):
        item = {'lbl': ai.get('label', ''), 'v': ai.get('value', '')}
        if ai.get('section'):
            item['sec'] = ai['section']
        add.append(item)

    return build_structured_data(rows, tots, dm, add)
