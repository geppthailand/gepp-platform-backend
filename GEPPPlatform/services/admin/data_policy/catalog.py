"""
v3 Data Policy catalog — what an ORGANIZATION holds, as category specs.

The legal data unit on v3 is `organizations.id`. Each category below is one
kind of data an organization holds that carries retention / PII risk, written
as a *base SELECT* that yields exactly these columns, one row per record:

    unit_id     bigint       organization id
    age_at      timestamptz  the date the retention clock runs from
    deleted_at  timestamptz  when it was soft-deleted (NULL = live)
    pii         int 0/1      the row still holds personal data (NULL = n/a)
    items       int          sub-items to sum, e.g. image refs (NULL = n/a)

`/*UF:<expr>*/` marks where the engine injects the unit filter for a scoped
run (`AND <expr> = ANY(:unit_ids)`); every branch of a UNION needs its own.

Adding a category = add a spec here (and to the docs). The UI is driven by
`/catalog`, so nothing else changes. See
docs/Services/GEPP-Backoffice/features/data_policy.md → "Adding a category".
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

# ─── Shared vocabulary (MIRRORED in v2/gepp-new-api/src/data-policy/catalog.ts) ───

ACTIONS: List[Dict[str, Any]] = [
    {'key': 'purge', 'label': 'Purge (delete) when older than', 'labelTh': 'ลบข้อมูลเมื่อเก่ากว่า',
     'description': 'Records older than the retention period must no longer exist.',
     'descriptionTh': 'ข้อมูลที่เก่ากว่าระยะเวลาที่กำหนดต้องถูกลบออกจากระบบ',
     'verifiable': True, 'needsRetention': True, 'needsSchedule': False},
    {'key': 'anonymize', 'label': 'Anonymize personal data when older than', 'labelTh': 'ทำให้เป็นข้อมูลนิรนามเมื่อเก่ากว่า',
     'description': 'Records may stay, but personal-data fields must be blanked or masked after the period.',
     'descriptionTh': 'เก็บรายการไว้ได้ แต่ต้องลบ/ปิดบังฟิลด์ข้อมูลส่วนบุคคลเมื่อครบกำหนด',
     'verifiable': True, 'needsRetention': True, 'needsSchedule': False},
    {'key': 'purge_soft_deleted', 'label': 'Hard-delete app-deleted records after', 'labelTh': 'ลบถาวรข้อมูลที่ถูกลบในแอปหลังจาก',
     'description': 'Rows deleted in the app (soft-deleted) are still physically stored; they must be removed after the period.',
     'descriptionTh': 'ข้อมูลที่ผู้ใช้ลบในแอป (soft delete) ยังถูกเก็บอยู่จริง ต้องลบถาวรเมื่อครบกำหนด',
     'verifiable': True, 'needsRetention': True, 'needsSchedule': False},
    {'key': 'retain_min', 'label': 'Keep for at least (legal minimum)', 'labelTh': 'ต้องเก็บไว้อย่างน้อย (ขั้นต่ำตามกฎหมาย)',
     'description': 'Records must not be deleted before this age (e.g. tax/accounting documents). Detects early soft-deletes.',
     'descriptionTh': 'ห้ามลบก่อนครบอายุนี้ (เช่น เอกสารภาษี/บัญชี) ตรวจจับการลบก่อนกำหนด',
     'verifiable': True, 'needsRetention': True, 'needsSchedule': False},
    {'key': 'inactive_unit_purge', 'label': 'Remove when the unit has been inactive for', 'labelTh': 'ลบเมื่อหน่วยข้อมูลไม่ใช้งานนานกว่า',
     'description': 'Once the unit is closed/ended for the period, it must no longer hold this data.',
     'descriptionTh': 'เมื่อหน่วยข้อมูลปิด/สิ้นสุดเกินระยะเวลา ต้องไม่มีข้อมูลประเภทนี้เหลืออยู่',
     'verifiable': True, 'needsRetention': True, 'needsSchedule': False},
    {'key': 'review', 'label': 'Flag for review when older than', 'labelTh': 'แจ้งให้ตรวจสอบเมื่อเก่ากว่า',
     'description': 'Not a violation — lists data due for a human retention review.',
     'descriptionTh': 'ไม่ใช่การละเมิด — แสดงข้อมูลที่ถึงเวลาต้องทบทวนการเก็บรักษา',
     'verifiable': True, 'needsRetention': True, 'needsSchedule': False},
    {'key': 'backup', 'label': 'Back up every', 'labelTh': 'สำรองข้อมูลทุก',
     'description': 'Backup cadence. Recorded as policy; cannot be verified from the database yet.',
     'descriptionTh': 'ความถี่การสำรองข้อมูล บันทึกเป็นนโยบาย ยังตรวจสอบอัตโนมัติไม่ได้',
     'verifiable': False, 'needsRetention': False, 'needsSchedule': True},
    {'key': 'archive', 'label': 'Archive to cold storage when older than', 'labelTh': 'ย้ายไปจัดเก็บระยะยาวเมื่อเก่ากว่า',
     'description': 'Move to cold storage. Recorded as policy; cannot be verified from the database yet.',
     'descriptionTh': 'ย้ายไปที่จัดเก็บระยะยาว บันทึกเป็นนโยบาย ยังตรวจสอบอัตโนมัติไม่ได้',
     'verifiable': False, 'needsRetention': True, 'needsSchedule': False},
]
ACTION_KEYS = [a['key'] for a in ACTIONS]

UNIT = {'key': 'organization', 'label': 'Organization', 'labelTh': 'องค์กร'}

GROUPS: List[Dict[str, str]] = [
    {'key': 'transactions', 'label': 'Transactions', 'labelTh': 'ธุรกรรม'},
    {'key': 'files', 'label': 'Files & images', 'labelTh': 'ไฟล์และรูปภาพ'},
    {'key': 'identity', 'label': 'Identity & personal data', 'labelTh': 'ข้อมูลระบุตัวตนและข้อมูลส่วนบุคคล'},
    {'key': 'finance', 'label': 'Financial records', 'labelTh': 'ข้อมูลการเงิน'},
    {'key': 'access', 'label': 'Access, activity & logs', 'labelTh': 'การเข้าใช้งาน กิจกรรม และ log'},
    {'key': 'credentials', 'label': 'Credentials & tokens', 'labelTh': 'ข้อมูลรับรองและโทเคน'},
    {'key': 'operations', 'label': 'Operations (rewards, IoT, traceability)', 'labelTh': 'การดำเนินงาน (รางวัล, IoT, ตรวจสอบย้อนกลับ)'},
    {'key': 'esg', 'label': 'ESG & reporting', 'labelTh': 'ESG และรายงาน'},
    {'key': 'maintenance', 'label': 'Imports & maintenance copies', 'labelTh': 'ไฟล์นำเข้าและสำเนาจากการบำรุงรักษา'},
]

# ─── SQL helpers ──────────────────────────────────────────────────────────────

def _sd(a: str) -> str:
    """BaseModel soft-delete moment: deleted_date, or updated_date when is_active was switched off."""
    return f"COALESCE({a}.deleted_date, CASE WHEN {a}.is_active = false THEN {a}.updated_date END)"


def _nz(col: str) -> str:
    """Text column holds a non-blank value."""
    return f"(NULLIF(BTRIM(CAST({col} AS text)), '') IS NOT NULL)"


def _jnz(col: str) -> str:
    """JSON column holds something other than null/{}/[]."""
    return f"({col} IS NOT NULL AND CAST({col} AS text) NOT IN ('null', '{{}}', '[]', '\"\"'))"


def _any(*conds: str) -> str:
    return 'CASE WHEN ' + ' OR '.join(conds) + ' THEN 1 ELSE 0 END'


def _jlen(col: str) -> str:
    return f"CASE WHEN jsonb_typeof({col}) = 'array' THEN jsonb_array_length({col}) ELSE 0 END"


def sel(unit: str, age: str, frm: str, where: str = 'TRUE', deleted: str = 'NULL',
        pii: str = 'NULL', items: str = 'NULL') -> str:
    return (
        f"SELECT CAST({unit} AS bigint) AS unit_id, CAST({age} AS timestamptz) AS age_at, "
        f"CAST({deleted} AS timestamptz) AS deleted_at, CAST({pii} AS int) AS pii, "
        f"CAST({items} AS int) AS items FROM {frm} WHERE ({where}) /*UF:{unit}*/"
    )


def union(*parts: str) -> str:
    return '\nUNION ALL\n'.join(parts)


# Hosts that serve objects without a signed URL. `gepp-app` is the v2 bucket
# (every upload ACL public-read); `gepp-prod` is the legacy public bucket.
PUBLIC_HOST_RE = r"(gepp-app|gepp-prod)\.s3[.a-z0-9-]*amazonaws\.com|drive\.google\.com"


def _public_refs(col: str) -> str:
    return (f"(SELECT COUNT(*) FROM jsonb_array_elements(CASE WHEN jsonb_typeof({col}) = 'array' "
            f"THEN {col} ELSE '[]'::jsonb END) e WHERE jsonb_typeof(e) = 'string' AND (e #>> '{{}}') ~* '{PUBLIC_HOST_RE}')")


def _cat(key: str, group: str, label: str, label_th: str, description: str, description_th: str,
         sensitivity: str, source: str, age_column: str, tables: List[str], sql: Any,
         soft_delete: bool = True, pii_fields: Optional[List[str]] = None, item_label: Optional[str] = None,
         holds_files: bool = False, legal_refs: Optional[List[str]] = None, primary: bool = True) -> Dict[str, Any]:
    pii_fields = pii_fields or []
    supported = ['purge', 'review', 'inactive_unit_purge', 'backup', 'archive']
    if pii_fields:
        supported.insert(1, 'anonymize')
    if soft_delete:
        supported[1:1] = ['purge_soft_deleted', 'retain_min']
    return {
        'key': key, 'group': group, 'label': label, 'labelTh': label_th,
        'description': description, 'descriptionTh': description_th,
        'sensitivity': sensitivity, 'source': source, 'ageColumn': age_column,
        'softDelete': soft_delete, 'piiFields': pii_fields, 'itemLabel': item_label,
        'holdsFiles': holds_files, 'legalRefs': legal_refs or [],
        'supportedActions': [a for a in ACTION_KEYS if a in supported],
        # engine-only (stripped from /catalog)
        '_tables': tables, '_sql': sql, '_primary': primary,
    }


PDPA = 'PDPA ม.37(3)'          # delete/destroy when retention period ends
PDPA_SEC = 'PDPA ม.37(1)'      # appropriate security measures
CCA = 'พ.ร.บ.คอมพิวเตอร์ ม.26'  # traffic data ≥ 90 days
ACC = 'พ.ร.บ.การบัญชี ม.14'     # accounting documents ≥ 5 years
REV = 'ประมวลรัษฎากร ม.87/3'    # tax documents ≥ 5 years


def _backup_tables_sql(db) -> Optional[str]:
    """
    Maintenance copies left behind by one-off fixes (`*_backup_*` tables).
    They copy transaction data outside any soft delete, so a purge in the app
    never reaches them. Discovered at plan time; mapped to the org through the
    column shape they have.
    """
    from sqlalchemy import text
    rows = db.execute(text(
        "SELECT c.table_name, array_agg(c.column_name::text) AS cols "
        "FROM information_schema.columns c JOIN information_schema.tables t "
        "  ON t.table_schema = c.table_schema AND t.table_name = c.table_name AND t.table_type = 'BASE TABLE' "
        "WHERE c.table_schema = 'public' AND c.table_name ILIKE '%backup%' "
        "GROUP BY c.table_name ORDER BY c.table_name"
    )).fetchall()
    parts: List[str] = []
    for name, cols in rows:
        if not name.replace('_', '').isalnum():
            continue  # identifiers come from the catalog, but never trust a quote
        cols = set(cols)
        tbl = f'"{name}" b'
        age = 'b.captured_at' if 'captured_at' in cols else ('b.created_date' if 'created_date' in cols else 'NULL')
        if 'organization_id' in cols:
            parts.append(sel('b.organization_id', age, tbl))
        elif {'entity_type', 'entity_id'} <= cols:
            parts.append(sel('t.organization_id', age,
                             f"{tbl} JOIN transactions t ON t.id = b.entity_id",
                             "b.entity_type = 'transaction'"))
            parts.append(sel('t.organization_id', age,
                             f"{tbl} JOIN transaction_records r ON r.id = b.entity_id "
                             f"JOIN transactions t ON t.id = r.created_transaction_id",
                             "b.entity_type = 'transaction_record'"))
        elif 'transaction_id' in cols:
            parts.append(sel('t.organization_id', age, f"{tbl} JOIN transactions t ON t.id = b.transaction_id"))
    return union(*parts) if parts else None


def _ul_user(a: str = 'ul') -> str:
    return f"{a}.is_user = true"


CATEGORIES: List[Dict[str, Any]] = [
    # ── Transactions ──────────────────────────────────────────────────────
    _cat('transactions', 'transactions', 'Waste transactions', 'ธุรกรรมขยะ',
         'Transaction headers: dates, weights, amounts, notes, driver/vehicle info and GPS coordinates.',
         'หัวรายการธุรกรรม: วันที่ น้ำหนัก มูลค่า หมายเหตุ ข้อมูลคนขับ/ยานพาหนะ และพิกัด GPS',
         'medium', 'transactions', 'transaction_date', ['transactions'],
         sel('t.organization_id', 'COALESCE(t.transaction_date, t.created_date)', 'transactions t',
             't.organization_id IS NOT NULL', _sd('t'),
             _any(_jnz('t.driver_info'), _jnz('t.vehicle_info'))),
         pii_fields=['driver_info', 'vehicle_info'], legal_refs=[PDPA]),
    _cat('transaction_records', 'transactions', 'Transaction line items', 'รายการย่อยของธุรกรรม',
         'Per-material records under each transaction (weights, prices, notes, coordinates).',
         'รายการวัสดุภายใต้แต่ละธุรกรรม (น้ำหนัก ราคา หมายเหตุ พิกัด)',
         'medium', 'transaction_records → transactions', 'transaction_date', ['transaction_records', 'transactions'],
         sel('t.organization_id', 'COALESCE(r.transaction_date, r.created_date)',
             'transaction_records r JOIN transactions t ON t.id = r.created_transaction_id',
             't.organization_id IS NOT NULL', _sd('r'))),
    _cat('traceability', 'transactions', 'Traceability & transport', 'การตรวจสอบย้อนกลับและการขนส่ง',
         'Traceability groups, transport legs and consolidations (origins, destinations, weights).',
         'กลุ่มการตรวจสอบย้อนกลับ เที่ยวขนส่ง และการรวมสินค้า (ต้นทาง ปลายทาง น้ำหนัก)',
         'low', 'traceability_transaction_group + traceability_transport_transactions + traceability_consolidations',
         'created_date',
         ['traceability_transaction_group', 'traceability_transport_transactions', 'traceability_consolidations'],
         union(
             sel('g.organization_id', 'g.created_date', 'traceability_transaction_group g', 'TRUE', _sd('g')),
             sel('x.organization_id', 'COALESCE(x.arrival_date, x.created_date)', 'traceability_transport_transactions x', 'TRUE', _sd('x')),
             sel('c.organization_id', 'c.created_date', 'traceability_consolidations c', 'TRUE', _sd('c')),
         )),

    # ── Files & images ────────────────────────────────────────────────────
    _cat('transaction_images', 'files', 'Transaction photos', 'รูปภาพประกอบธุรกรรม',
         'Transactions / line items that carry photos (JSON `images`: file ids and legacy URLs). Item count = number of image references.',
         'ธุรกรรม/รายการย่อยที่มีรูปภาพ (ฟิลด์ images: file id และ URL แบบเก่า) จำนวนรายการย่อย = จำนวนรูปที่อ้างถึง',
         'high', 'transactions.images + transaction_records.images', 'transaction_date',
         ['transactions', 'transaction_records'],
         union(
             sel('t.organization_id', 'COALESCE(t.transaction_date, t.created_date)', 'transactions t',
                 f"t.organization_id IS NOT NULL AND {_jlen('t.images')} > 0", _sd('t'), items=_jlen('t.images')),
             sel('t.organization_id', 'COALESCE(r.transaction_date, r.created_date)',
                 'transaction_records r JOIN transactions t ON t.id = r.created_transaction_id',
                 f"{_jlen('r.images')} > 0", _sd('r'), items=_jlen('r.images')),
         ),
         item_label='image references', holds_files=True, legal_refs=[PDPA], primary=False),
    _cat('public_storage_files', 'files', 'Photos in publicly readable storage', 'รูปภาพที่อยู่ในพื้นที่เก็บแบบสาธารณะ',
         'Image references hosted on public-read buckets (gepp-app, gepp-prod) or Google Drive — reachable by anyone holding the URL.',
         'รูปภาพที่เก็บใน bucket แบบ public-read (gepp-app, gepp-prod) หรือ Google Drive ใครมี URL ก็เปิดได้',
         'high', 'transactions.images + transaction_records.images (public hosts)', 'transaction_date',
         ['transactions', 'transaction_records'],
         union(
             sel('t.organization_id', 'COALESCE(t.transaction_date, t.created_date)', 'transactions t',
                 f"t.organization_id IS NOT NULL AND jsonb_typeof(t.images) = 'array' AND CAST(t.images AS text) ~* '{PUBLIC_HOST_RE}'",
                 _sd('t'), items=_public_refs('t.images')),
             sel('t.organization_id', 'COALESCE(r.transaction_date, r.created_date)',
                 'transaction_records r JOIN transactions t ON t.id = r.created_transaction_id',
                 f"jsonb_typeof(r.images) = 'array' AND CAST(r.images AS text) ~* '{PUBLIC_HOST_RE}'",
                 _sd('r'), items=_public_refs('r.images')),
         ),
         item_label='public image URLs', holds_files=True, legal_refs=[PDPA_SEC], primary=False),
    _cat('stored_files', 'files', 'Uploaded files (S3 registry)', 'ไฟล์ที่อัปโหลด (ทะเบียน S3)',
         'Completed uploads in the files registry: transaction images, profile images, IoT screenshots and other objects in S3.',
         'ไฟล์ที่อัปโหลดสำเร็จในทะเบียนไฟล์: รูปธุรกรรม รูปโปรไฟล์ ภาพหน้าจอ IoT และไฟล์อื่นใน S3',
         'medium', 'files (status ≠ pending/failed, type ≠ document)', 'created_date', ['files'],
         sel('f.organization_id', 'f.created_date', 'files f',
             "f.status NOT IN ('pending', 'failed') AND f.file_type <> 'document'",
             f"COALESCE(f.deleted_date, CASE WHEN f.is_active = false OR f.status = 'deleted' THEN f.updated_date END)"),
         holds_files=True),
    _cat('documents', 'files', 'Uploaded documents', 'เอกสารที่อัปโหลด',
         'Files registered as documents (e.g. IoT device documents, contracts, certificates).',
         'ไฟล์ประเภทเอกสาร (เช่น เอกสารอุปกรณ์ IoT สัญญา ใบรับรอง)',
         'high', "files (file_type = 'document')", 'created_date', ['files'],
         sel('f.organization_id', 'f.created_date', 'files f',
             "f.file_type = 'document' AND f.status NOT IN ('pending', 'failed')",
             f"COALESCE(f.deleted_date, CASE WHEN f.is_active = false OR f.status = 'deleted' THEN f.updated_date END)"),
         holds_files=True, legal_refs=[PDPA]),
    _cat('pending_uploads', 'files', 'Abandoned upload slots', 'ช่องอัปโหลดที่ค้าง',
         'File rows created for a presigned upload that never completed (status pending/failed). The S3 object may or may not exist.',
         'แถวไฟล์ที่สร้างไว้สำหรับอัปโหลดแต่ไม่เสร็จ (pending/failed) อาจมีหรือไม่มีไฟล์จริงใน S3',
         'low', "files (status IN ('pending','failed'))", 'created_date', ['files'],
         sel('f.organization_id', 'f.created_date', 'files f', "f.status IN ('pending', 'failed')", _sd('f')),
         holds_files=True, primary=False),

    # ── Identity & personal data ──────────────────────────────────────────
    _cat('user_accounts', 'identity', 'User accounts', 'บัญชีผู้ใช้',
         'People with a login in the organization: names, email, phone, username, social/LINE ids, address.',
         'ผู้ใช้ที่มีบัญชีในองค์กร: ชื่อ อีเมล เบอร์โทร username บัญชีโซเชียล/LINE ที่อยู่',
         'high', 'user_locations (is_user)', 'created_date', ['user_locations'],
         sel('ul.organization_id', 'ul.created_date', 'user_locations ul', _ul_user(), _sd('ul'),
             _any(_nz('ul.email'), _nz('ul.phone'), _nz('ul.first_name'), _nz('ul.last_name'),
                  _nz('ul.line_user_id'), _nz('ul.address'))),
         pii_fields=['first_name', 'last_name', 'email', 'phone', 'username', 'line_user_id', 'address'],
         legal_refs=[PDPA]),
    _cat('identity_documents', 'identity', 'National ID numbers & ID-card images', 'เลขบัตรประชาชนและรูปบัตรประชาชน',
         'Users/locations holding a national ID number or an ID-card image. Item count = ID-card images.',
         'ผู้ใช้/สถานที่ที่มีเลขบัตรประชาชนหรือรูปบัตรประชาชน จำนวนรายการย่อย = รูปบัตร',
         'critical', 'user_locations.national_id / national_card_image', 'created_date', ['user_locations'],
         sel('ul.organization_id', 'ul.created_date', 'user_locations ul',
             f"{_nz('ul.national_id')} OR {_nz('ul.national_card_image')}", _sd('ul'),
             _any(_nz('ul.national_id'), _nz('ul.national_card_image')),
             f"CASE WHEN {_nz('ul.national_card_image')} THEN 1 ELSE 0 END"),
         pii_fields=['national_id', 'national_card_image'], item_label='ID-card images', holds_files=True,
         legal_refs=[PDPA, 'PDPA ม.26'], primary=False),
    _cat('locations_addresses', 'identity', 'Sites & addresses', 'สถานที่และที่อยู่',
         'Locations/sites with address, GPS coordinate, phone or tax id.',
         'สถานที่/ไซต์งานที่มีที่อยู่ พิกัด GPS เบอร์โทร หรือเลขผู้เสียภาษี',
         'medium', 'user_locations (is_location)', 'created_date', ['user_locations'],
         sel('ul.organization_id', 'ul.created_date', 'user_locations ul',
             'ul.is_location = true AND COALESCE(ul.is_user, false) = false', _sd('ul'),
             _any(_nz('ul.address'), _nz('ul.coordinate'), _nz('ul.phone'), _nz('ul.tax_id'))),
         pii_fields=['address', 'coordinate', 'phone', 'company_phone', 'company_email', 'tax_id']),
    _cat('company_profile', 'identity', 'Company legal profile', 'ข้อมูลนิติบุคคลขององค์กร',
         "The organization's own registration data: tax id, national id, phones, email, address, registration certificate.",
         'ข้อมูลจดทะเบียนขององค์กร: เลขผู้เสียภาษี เลขบัตร เบอร์โทร อีเมล ที่อยู่ หนังสือรับรองบริษัท',
         'high', 'organizations → organization_info', 'created_date', ['organizations', 'organization_info'],
         sel('o.id', 'COALESCE(oi.created_date, o.created_date)',
             'organizations o JOIN organization_info oi ON oi.id = o.organization_info_id', 'TRUE', _sd('oi'),
             _any(_nz('oi.tax_id'), _nz('oi.national_id'), _nz('oi.phone_number'), _nz('oi.company_email'),
                  _nz('oi.address'), _nz('oi.business_registration_certificate'))),
         pii_fields=['tax_id', 'national_id', 'phone_number', 'company_phone', 'company_email', 'address',
                     'business_registration_certificate'], holds_files=True),
    _cat('line_identities', 'identity', 'LINE / chat identities', 'บัญชี LINE / แชต',
         'LINE user ids linked to users, and ESG chat users (LINE/WhatsApp platform ids, profile pictures).',
         'LINE user id ที่ผูกกับผู้ใช้ และผู้ใช้แชต ESG (platform id ของ LINE/WhatsApp รูปโปรไฟล์)',
         'medium', 'user_locations.line_user_id + esg_users', 'created_date', ['user_locations', 'esg_users'],
         union(
             sel('ul.organization_id', 'ul.created_date', 'user_locations ul', _nz('ul.line_user_id'), _sd('ul'),
                 _any(_nz('ul.line_user_id'))),
             sel('eu.organization_id', 'eu.created_date', 'esg_users eu', 'TRUE', _sd('eu'),
                 _any(_nz('eu.platform_user_id'), _nz('eu.profile_image_url'))),
         ),
         pii_fields=['line_user_id', 'platform_user_id', 'profile_image_url'], primary=False),
    _cat('reward_members', 'identity', 'Reward programme members', 'สมาชิกโครงการรางวัล',
         'Members enrolled in the organization’s reward programme: name, email, phone, address, date of birth, LINE/WhatsApp/WeChat ids. One person can belong to several organizations.',
         'สมาชิกโครงการรางวัลขององค์กร: ชื่อ อีเมล เบอร์โทร ที่อยู่ วันเกิด LINE/WhatsApp/WeChat (หนึ่งคนอยู่ได้หลายองค์กร)',
         'high', 'organization_reward_users → reward_users', 'created_date (membership)',
         ['organization_reward_users', 'reward_users'],
         sel('m.organization_id', 'm.created_date',
             'organization_reward_users m JOIN reward_users ru ON ru.id = m.reward_user_id', 'TRUE',
             f"COALESCE({_sd('m')}, {_sd('ru')})",
             _any(_nz('ru.email'), _nz('ru.phone_number'), _nz('ru.address'), 'ru.date_of_birth IS NOT NULL',
                  _nz('ru.line_user_id'), _nz('ru.whatsapp_user_id'), _nz('ru.wechat_user_id'))),
         pii_fields=['display_name', 'email', 'phone_number', 'address', 'date_of_birth', 'line_user_id',
                     'line_picture_url', 'whatsapp_user_id', 'wechat_user_id'], legal_refs=[PDPA]),
    _cat('invitations', 'identity', 'Invitations & magic links', 'คำเชิญและลิงก์เข้าใช้งาน',
         'Pending/used user invitations, ESG external invitation links and supplier magic links (email, phone, tokens).',
         'คำเชิญผู้ใช้ ลิงก์เชิญภายนอก ESG และ magic link ของซัพพลายเออร์ (อีเมล เบอร์โทร โทเคน)',
         'medium', 'user_invitations + esg_external_invitation_links + esg_supplier_magic_links', 'created_date',
         ['user_invitations', 'esg_external_invitation_links', 'esg_supplier_magic_links'],
         union(
             sel('i.organization_id', 'i.created_date', 'user_invitations i', 'TRUE', _sd('i'),
                 _any(_nz('i.email'), _nz('i.phone'))),
             sel('l.organization_id', 'l.created_date', 'esg_external_invitation_links l', 'TRUE', _sd('l'),
                 _any(_nz('l.used_by_platform_user_id'), _nz('l.used_by_display_name'))),
             sel('s.organization_id', 's.created_date', 'esg_supplier_magic_links s', 'TRUE', _sd('s'),
                 _any(_nz('s.email_sent_to'))),
         ),
         pii_fields=['email', 'phone', 'email_sent_to', 'used_by_platform_user_id']),

    # ── Financial ─────────────────────────────────────────────────────────
    _cat('bank_accounts', 'finance', 'Bank accounts', 'บัญชีธนาคาร',
         'Bank account numbers and holder names of users/locations.',
         'เลขบัญชีและชื่อบัญชีธนาคารของผู้ใช้/สถานที่',
         'critical', 'user_bank', 'created_date', ['user_bank'],
         sel('b.organization_id', 'b.created_date', 'user_bank b', 'TRUE', _sd('b'),
             _any(_nz('b.account_number'), _nz('b.account_name'))),
         pii_fields=['account_number', 'account_name'], legal_refs=[PDPA, PDPA_SEC]),
    _cat('reward_finance_docs', 'finance', 'Reward campaign expenses & receipts', 'ค่าใช้จ่ายและใบเสร็จแคมเปญรางวัล',
         'Campaign expense lines with vendor, amount and receipt files — accounting evidence.',
         'รายการค่าใช้จ่ายแคมเปญ พร้อมผู้ขาย จำนวนเงิน และไฟล์ใบเสร็จ (หลักฐานทางบัญชี)',
         'high', 'reward_campaign_expenses', 'expense_date', ['reward_campaign_expenses'],
         sel('x.organization_id', 'COALESCE(x.expense_date, x.created_date)', 'reward_campaign_expenses x', 'TRUE',
             _sd('x'), items='CASE WHEN x.receipt_file_id IS NOT NULL THEN 1 ELSE 0 END'),
         item_label='receipt files', holds_files=True, legal_refs=[ACC, REV]),

    # ── Access & logs ─────────────────────────────────────────────────────
    _cat('login_history', 'access', 'Login history', 'ประวัติการเข้าสู่ระบบ',
         'Successful and failed logins with IP address and user agent.',
         'การเข้าสู่ระบบสำเร็จและล้มเหลว พร้อม IP และ user agent',
         'medium', "crm_events (user_login, user_login_failed)", 'occurred_at', ['crm_events'],
         sel('e.organization_id', 'COALESCE(e.occurred_at, e.created_date)', 'crm_events e',
             "e.event_type IN ('user_login', 'user_login_failed')", 'NULL',
             _any('e.ip_address IS NOT NULL', _nz('e.user_agent'))),
         soft_delete=False, pii_fields=['ip_address', 'user_agent'], legal_refs=[CCA, PDPA]),
    _cat('usage_events', 'access', 'Usage & telemetry events', 'เหตุการณ์การใช้งานและ telemetry',
         'Product analytics and device heartbeat events (crm_events other than logins).',
         'เหตุการณ์การใช้งานระบบและ heartbeat ของอุปกรณ์ (crm_events ที่ไม่ใช่การล็อกอิน)',
         'low', 'crm_events (other types)', 'occurred_at', ['crm_events'],
         sel('e.organization_id', 'COALESCE(e.occurred_at, e.created_date)', 'crm_events e',
             "e.event_type NOT IN ('user_login', 'user_login_failed')", 'NULL',
             _any('e.ip_address IS NOT NULL', _nz('e.user_agent'))),
         soft_delete=False, pii_fields=['ip_address', 'user_agent']),
    _cat('user_activities', 'access', 'User activity log', 'บันทึกกิจกรรมผู้ใช้',
         'Audit log of user actions with IP address, user agent and details.',
         'บันทึกการกระทำของผู้ใช้ พร้อม IP, user agent และรายละเอียด',
         'medium', 'user_activities', 'created_date', ['user_activities'],
         sel('a.organization_id', 'a.created_date', 'user_activities a', 'TRUE', _sd('a'),
             _any('a.ip_address IS NOT NULL', _nz('a.user_agent'))),
         pii_fields=['ip_address', 'user_agent', 'details'], legal_refs=[CCA]),
    _cat('api_call_logs', 'access', 'Custom API call log', 'บันทึกการเรียก Custom API',
         'Calls made through the organization’s custom API path.',
         'การเรียกใช้งานผ่าน custom API ขององค์กร',
         'low', 'custom_api_callings', 'created_date', ['custom_api_callings'],
         sel('c.organization_id', 'c.created_date', 'custom_api_callings c', 'TRUE', _sd('c'))),

    # ── Credentials ───────────────────────────────────────────────────────
    _cat('integration_credentials', 'credentials', 'Integration credentials & tokens', 'ข้อมูลรับรองการเชื่อมต่อและโทเคน',
         'Stored third-party credentials (ESG platform bindings `auth_json`), long-lived integration JWTs and password-reset tokens.',
         'ข้อมูลรับรองระบบภายนอก (auth_json) JWT สำหรับการเชื่อมต่อ และโทเคนรีเซ็ตรหัสผ่าน',
         'critical', 'esg_external_platform_binding + integration_tokens + user_reset_password_log', 'created_date',
         ['esg_external_platform_binding', 'integration_tokens', 'user_reset_password_log', 'user_locations'],
         union(
             sel('p.organization_id', 'p.created_date', 'esg_external_platform_binding p', 'TRUE', _sd('p'),
                 _any(_jnz('p.auth_json'))),
             sel('ul.organization_id', 'it.created_date',
                 'integration_tokens it JOIN user_locations ul ON ul.id = it.user_id', 'TRUE',
                 f"COALESCE({_sd('it')}, CASE WHEN it.valid = false THEN it.updated_date END)", _any(_nz('it.jwt'))),
             sel('ul.organization_id', 'rp.created_date',
                 'user_reset_password_log rp JOIN user_locations ul ON ul.id = rp.user_id', 'TRUE', _sd('rp'),
                 _any(_nz('rp.jwt'), 'rp.ip_address IS NOT NULL')),
         ),
         pii_fields=['auth_json', 'jwt', 'ip_address'], legal_refs=[PDPA_SEC]),

    # ── Operations ────────────────────────────────────────────────────────
    _cat('ai_audits', 'operations', 'AI / human audit results', 'ผลการตรวจสอบ (AI / เจ้าหน้าที่)',
         'Transaction audit verdicts, audit notes, model/token usage and batch audit runs.',
         'ผลตรวจสอบธุรกรรม หมายเหตุ การใช้โมเดล/โทเคน และรอบตรวจสอบแบบกลุ่ม',
         'low', 'transaction_audits + transaction_audit_history', 'created_date',
         ['transaction_audits', 'transaction_audit_history'],
         union(
             sel('a.organization_id', 'a.created_date', 'transaction_audits a', 'TRUE', _sd('a')),
             sel('h.organization_id', 'COALESCE(h.started_at, h.created_date)', 'transaction_audit_history h',
                 'TRUE', 'h.deleted_date'),
         )),
    _cat('reward_activity', 'operations', 'Reward points, claims & redemptions', 'แต้ม การขอรับ และการแลกรางวัล',
         'Point ledger, member claim requests (with photos) and redemptions.',
         'บัญชีแต้ม คำขอรับแต้มของสมาชิก (พร้อมรูป) และการแลกรางวัล',
         'medium', 'reward_point_transactions + reward_claim_requests + reward_redemptions', 'created_date',
         ['reward_point_transactions', 'reward_claim_requests', 'reward_redemptions'],
         union(
             sel('p.organization_id', 'COALESCE(p.claimed_date, p.created_date)', 'reward_point_transactions p',
                 'TRUE', _sd('p'), items=_jlen('p.image_ids')),
             sel('c.organization_id', 'COALESCE(c.submitted_date, c.created_date)', 'reward_claim_requests c',
                 'TRUE', _sd('c'), items=_jlen('c.image_ids')),
             sel('d.organization_id', 'd.created_date', 'reward_redemptions d', 'TRUE', _sd('d'), items='0'),
         ),
         item_label='attached photos', holds_files=True),
    _cat('iot_devices', 'operations', 'IoT devices', 'อุปกรณ์ IoT',
         'Registered scales/tablets with MAC addresses, serials and device passwords.',
         'อุปกรณ์ที่ลงทะเบียน (เครื่องชั่ง/แท็บเล็ต) พร้อม MAC address ซีเรียล และรหัสผ่านอุปกรณ์',
         'medium', 'iot_devices', 'created_date', ['iot_devices'],
         sel('d.organization_id', 'd.created_date', 'iot_devices d', 'TRUE', _sd('d'),
             _any(_nz('d.password'))),
         pii_fields=['password', 'mac_address_bluetooth', 'mac_address_tablet']),
    _cat('iot_telemetry', 'operations', 'IoT telemetry & device logs', 'ข้อมูล telemetry และ log ของอุปกรณ์ IoT',
         "Device events, commands, debug logs and health history (attributed to the device's current organization).",
         'เหตุการณ์ คำสั่ง debug log และประวัติสถานะของอุปกรณ์ (นับตามองค์กรปัจจุบันของอุปกรณ์)',
         'low', 'iot_device_events/commands/debug_logs/health_history → iot_devices', 'occurred_at',
         ['iot_devices', 'iot_device_events', 'iot_device_commands', 'iot_debug_logs', 'iot_device_health_history'],
         union(
             sel('d.organization_id', 'ev.occurred_at', 'iot_device_events ev JOIN iot_devices d ON d.id = ev.device_id'),
             sel('d.organization_id', 'cm.issued_at', 'iot_device_commands cm JOIN iot_devices d ON d.id = cm.device_id'),
             sel('d.organization_id', 'dl.captured_at', 'iot_debug_logs dl JOIN iot_devices d ON d.id = dl.iot_device_id'),
             sel('d.organization_id', 'hh.last_seen_at', 'iot_device_health_history hh JOIN iot_devices d ON d.id = hh.device_id'),
         ),
         soft_delete=False),

    # ── ESG ───────────────────────────────────────────────────────────────
    _cat('esg_records', 'esg', 'ESG data entries & evidence', 'รายการข้อมูล ESG และหลักฐาน',
         'ESG data points with evidence images, submitted via the app or LINE.',
         'ข้อมูล ESG พร้อมรูปหลักฐาน ที่ส่งผ่านแอปหรือ LINE',
         'medium', 'esg_records', 'entry_date', ['esg_records'],
         sel('r.organization_id', 'COALESCE(r.entry_date, r.created_date)', 'esg_records r', 'TRUE', _sd('r'),
             _any(_nz('r.line_user_id')),
             f"CASE WHEN {_nz('r.evidence_image_url')} OR {_nz('r.file_key')} THEN 1 ELSE 0 END"),
         pii_fields=['line_user_id'], item_label='evidence files', holds_files=True),
    _cat('esg_documents', 'esg', 'ESG documents & extracted content', 'เอกสาร ESG และข้อความที่สกัดได้',
         'Uploaded ESG documents (invoices, bills, reports), their AI-extracted raw content, and supplier submission files.',
         'เอกสาร ESG ที่อัปโหลด (ใบแจ้งหนี้ บิล รายงาน) ข้อความดิบที่ AI สกัด และไฟล์ที่ซัพพลายเออร์ส่ง',
         'high', 'esg_documents + esg_organization_data_extraction + esg_supplier_submissions', 'created_date',
         ['esg_documents', 'esg_organization_data_extraction', 'esg_supplier_submissions'],
         union(
             sel('d.organization_id', 'COALESCE(d.document_date, d.created_date)', 'esg_documents d', 'TRUE', _sd('d'),
                 _any(_nz('d.line_user_id')), f"CASE WHEN {_nz('d.file_url')} THEN 1 ELSE 0 END"),
             sel('x.organization_id', 'x.created_date', 'esg_organization_data_extraction x', 'TRUE', _sd('x'),
                 _any(_nz('x.source_user_id')), 'CASE WHEN x.file_id IS NOT NULL THEN 1 ELSE 0 END'),
             sel('s.organization_id', 'COALESCE(s.submitted_at, s.created_date)', 'esg_supplier_submissions s', 'TRUE',
                 _sd('s'), 'NULL', f"CASE WHEN {_nz('s.file_key')} THEN 1 ELSE 0 END"),
         ),
         pii_fields=['line_user_id', 'source_user_id'], item_label='files', holds_files=True, legal_refs=[ACC]),
    _cat('esg_chat_logs', 'esg', 'LINE messages & AI chat history', 'ข้อความ LINE และประวัติแชต AI',
         'Inbound LINE messages and LLM chat transcripts with LINE user ids.',
         'ข้อความ LINE ขาเข้า และบทสนทนากับ AI พร้อม LINE user id',
         'medium', 'esg_line_messages + esg_line_chat_histories + esg_materiality_submissions', 'created_date',
         ['esg_line_messages', 'esg_line_chat_histories', 'esg_materiality_submissions'],
         union(
             sel('m.organization_id', 'm.created_date', 'esg_line_messages m', 'TRUE', _sd('m'), _any(_nz('m.line_user_id'))),
             sel('h.organization_id', 'h.created_date', 'esg_line_chat_histories h', 'h.organization_id IS NOT NULL',
                 _sd('h'), _any(_nz('h.line_user_id'), _nz('h.content'))),
             sel('s.organization_id', 'COALESCE(s.submitted_at, s.created_date)', 'esg_materiality_submissions s',
                 's.organization_id IS NOT NULL', _sd('s'), _any(_nz('s.line_user_id'), _nz('s.submitter_name'))),
         ),
         pii_fields=['line_user_id', 'content', 'submitter_name'], legal_refs=[PDPA]),
    _cat('esg_suppliers', 'esg', 'Supplier contacts', 'ข้อมูลติดต่อซัพพลายเออร์',
         'Supplier master data with contact names, emails, phones and tax ids.',
         'ข้อมูลซัพพลายเออร์ พร้อมชื่อผู้ติดต่อ อีเมล เบอร์โทร และเลขผู้เสียภาษี',
         'medium', 'esg_suppliers', 'created_date', ['esg_suppliers'],
         sel('s.organization_id', 's.created_date', 'esg_suppliers s', 'TRUE', _sd('s'),
             _any(_nz('s.contact_email'), _nz('s.contact_phone'), _nz('s.contact_name'))),
         pii_fields=['contact_name', 'contact_email', 'contact_phone', 'tax_id']),
    _cat('gri_disclosures', 'esg', 'GRI 306 waste disclosures', 'ข้อมูลเปิดเผย GRI 306',
         'GRI 306-1/2/3 disclosure rows entered for reporting.',
         'ข้อมูล GRI 306-1/2/3 ที่กรอกเพื่อรายงาน',
         'low', 'gri306_1 + gri306_2 + gri306_3 (column `organization`)', 'created_date',
         ['gri306_1', 'gri306_2', 'gri306_3'],
         union(*[sel('g.organization', 'g.created_date', f'{t} g', 'TRUE', _sd('g')) for t in ('gri306_1', 'gri306_2', 'gri306_3')])),
    _cat('report_exports', 'esg', 'Generated report exports', 'ไฟล์รายงานที่สร้างแล้ว',
         'Exported GRI and CBAM report files kept in storage.',
         'ไฟล์รายงาน GRI และ CBAM ที่ export ไว้ในที่จัดเก็บ',
         'medium', 'gri306_export + esg_cbam_reports', 'created_date', ['gri306_export', 'esg_cbam_reports'],
         union(
             sel('g.organization', 'g.created_date', 'gri306_export g', 'TRUE', _sd('g'),
                 items=f"CASE WHEN {_nz('g.export_file_url')} THEN 1 ELSE 0 END"),
             sel('c.organization_id', 'c.created_date', 'esg_cbam_reports c', 'TRUE', _sd('c'),
                 items=f"CASE WHEN {_nz('c.export_url')} THEN 1 ELSE 0 END"),
         ),
         item_label='export files', holds_files=True),

    # ── Imports & maintenance ─────────────────────────────────────────────
    _cat('import_files', 'maintenance', 'Bulk-import files & previews', 'ไฟล์นำเข้าข้อมูลและพรีวิว',
         'Uploaded spreadsheets for transaction/setup imports; `preview_payload` keeps every parsed row, including any personal data in them.',
         'ไฟล์ Excel ที่อัปโหลดเพื่อนำเข้าธุรกรรม/โครงสร้างองค์กร preview_payload เก็บทุกแถวที่อ่านได้ รวมข้อมูลส่วนบุคคลที่อยู่ในไฟล์',
         'high', 'import_files + organization_setup_imports', 'created_date',
         ['import_files', 'organization_setup_imports'],
         union(
             sel('i.organization_id', 'i.created_date', 'import_files i', 'TRUE', _sd('i'),
                 _any(_jnz('i.preview_payload')), f"CASE WHEN {_nz('i.s3_key')} THEN 1 ELSE 0 END"),
             sel('s.organization_id', 's.created_date', 'organization_setup_imports s', 'TRUE', _sd('s'),
                 _any(_jnz('s.preview_payload')), f"CASE WHEN {_nz('s.s3_key')} THEN 1 ELSE 0 END"),
         ),
         pii_fields=['preview_payload'], item_label='source files', holds_files=True, legal_refs=[PDPA]),
    _cat('maintenance_backups', 'maintenance', 'Copies in maintenance backup tables', 'สำเนาในตาราง backup จากการแก้ข้อมูล',
         'Rows copied into `*_backup_*` tables by one-off data fixes (old dates, removed image URLs…). They sit outside soft delete, so deleting in the app never reaches them.',
         'แถวที่ถูกคัดลอกไว้ในตาราง *_backup_* ระหว่างการแก้ข้อมูล (วันที่เดิม URL รูปที่ถูกลบ…) อยู่นอกระบบ soft delete การลบในแอปจึงไม่ถึงสำเนาเหล่านี้',
         'high', '*_backup_* tables (auto-discovered)', 'captured_at', [], _backup_tables_sql,
         soft_delete=False, legal_refs=[PDPA], primary=False),
]


CATEGORY_BY_KEY: Dict[str, Dict[str, Any]] = {c['key']: c for c in CATEGORIES}


def public_category(c: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in c.items() if not k.startswith('_')}


def catalog_doc(engine_version: str) -> Dict[str, Any]:
    return {
        'platform': 'v3',
        'engineVersion': engine_version,
        'unit': UNIT,
        'groups': GROUPS,
        'categories': [public_category(c) for c in CATEGORIES],
        'actions': ACTIONS,
    }


def category_sql(c: Dict[str, Any], db) -> Optional[str]:
    sql = c['_sql']
    return sql(db) if callable(sql) else sql
