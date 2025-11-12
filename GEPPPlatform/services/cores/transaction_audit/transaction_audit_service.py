"""
Transaction Audit Service - AI-powered transaction auditing
Handles synchronous AI audit processing with multi-threading support
"""

import json
import logging
import os
import re
import tempfile
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    genai = None


from ....models.transactions.transactions import Transaction, TransactionStatus, AIAuditStatus
from ....models.transactions.transaction_records import TransactionRecord
from ....models.transactions.transaction_audits import TransactionAudit
from ....models.audit_rules import AuditRule
from ....models.cores.references import MainMaterial
from ....models.subscriptions.organizations import Organization
from ....models.logs.transaction_audit_history import TransactionAuditHistory
from ..transactions.presigned_url_service import TransactionPresignedUrlService

logger = logging.getLogger(__name__)

# Constants for credential management
SA_JSON_ENV_VAR = 'GCP_SERVICE_ACCOUNT_JSON'
TEMP_FILE_NAME = 'temp_sa_key.json'

def setup_credentials_from_env():
    """
    Read JSON Service Account Key from Environment Variable and create temporary file
    to set GOOGLE_APPLICATION_CREDENTIALS pointing to that file
    """

    # 1. Read JSON String from Environment Variable
    sa_json_string = os.getenv(SA_JSON_ENV_VAR)
    if not sa_json_string:
        logger.warning(f"Environment variable '{SA_JSON_ENV_VAR}' not found.")
        logger.info("Client will attempt to use gcloud ADC default location.")
        return None

    try:
        # 2. Create temporary file
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, TEMP_FILE_NAME)

        # Write JSON Key to temporary file
        with open(temp_file_path, 'w') as f:
            # Use json.loads to validate and handle escaping
            sa_data = json.loads(sa_json_string)
            json.dump(sa_data, f)

        # 3. Set GOOGLE_APPLICATION_CREDENTIALS to point to temporary file
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = temp_file_path
        logger.info(f"Credentials saved to temporary file: {temp_file_path}")
        return temp_file_path

    except json.JSONDecodeError:
        logger.error(f"Invalid JSON format in '{SA_JSON_ENV_VAR}'.")
        return None
    except Exception as e:
        logger.error(f"Unexpected error setting up credentials: {e}")
        return None

def cleanup_credentials_file(file_path):
    """Remove temporary file and delete environment variable."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
                del os.environ['GOOGLE_APPLICATION_CREDENTIALS']
            logger.info(f"Cleaned up temporary file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup credentials file: {e}")

class TransactionAuditService:
    """
    Service for AI-powered transaction auditing using Google Vertex AI
    Supports multi-threaded processing for efficient bulk analysis
    """

    def __init__(self, gemini_api_key: str = None, response_language: str = 'thai',
                 project_id: str = None, location: str = None, extraction_mode: str = 'detailed'):
        """
        Initialize the TransactionAuditService

        Args:
            gemini_api_key: Google Gemini API key (deprecated, kept for backward compatibility)
            response_language: Language for AI responses (default: 'thai')
            project_id: Google Cloud Project ID for Vertex AI
            location: Google Cloud region/location (e.g., 'us-central1', 'asia-southeast1')
            extraction_mode: Extraction mode ('detailed' or 'minimal') - controls token usage
                           'detailed': Full extraction with all categories (more accurate, more tokens)
                           'minimal': Streamlined extraction focusing on critical items (faster, fewer tokens)
        """
        # Setup credentials from environment variable
        self.temp_credentials_file = setup_credentials_from_env()

        # Set extraction mode
        self.extraction_mode = extraction_mode.lower() if extraction_mode else 'detailed'
        if self.extraction_mode not in ['detailed', 'minimal']:
            logger.warning(f"Invalid extraction mode '{extraction_mode}', defaulting to 'detailed'")
            self.extraction_mode = 'detailed'

        # Get configuration from environment or parameters
        self.project_id = os.environ.get('VERTEX_AI_PROJECT_ID')
        self.location = 'us-central1'

        # Initialize Vertex AI client
        if self.project_id and GENAI_AVAILABLE:
            try:
                # self.client = genai.Client(
                #     vertexai=True,  # Force use of Vertex AI
                #     project=self.project_id,
                #     location=self.location
                # )

                self.client = genai.Client(
                    api_key=os.environ.get('GEMINI_API_KEY')
                )
                logger.info(f"Vertex AI client initialized successfully (Project: {self.project_id}, Location: {self.location})")
            except Exception as e:
                logger.error(f"Failed to initialize Vertex AI client: {str(e)}")
                self.client = None
        else:
            logger.warning("Vertex AI project ID not found or genai library not available")
            self.client = None

        # Load prompt configuration
        self.prompts = self._load_prompt_config()
        
        # Language name mapping for prompts
        self.language_names = self.prompts.get('language_mapping', {
            'thai': 'Thai (ภาษาไทย)',
            'english': 'English',
            'en': 'English',
            'th': 'Thai (ภาษาไทย)'
        })

        self.model_name = self.prompts.get('api_settings', {}).get('model_name', 'gemini-2.5-flash-lite')
        self.max_concurrent_threads = 100
        self.response_language = response_language.lower()  # Store language preference

        # Log service configuration
        logger.info(f"TransactionAuditService initialized:")
        logger.info(f"  - Model: {self.model_name}")
        logger.info(f"  - Extraction Mode: {self.extraction_mode.upper()}")
        logger.info(f"  - Language: {self.response_language}")
        logger.info(f"  - Max Threads: {self.max_concurrent_threads}")

        # Initialize presigned URL service for image access
        try:
            self.presigned_url_service = TransactionPresignedUrlService()
            logger.info("Presigned URL service initialized for image access")
        except Exception as e:
            logger.warning(f"Failed to initialize presigned URL service: {str(e)}")
            self.presigned_url_service = None

    def __del__(self):
        """Cleanup credentials file when service is destroyed"""
        if hasattr(self, 'temp_credentials_file') and self.temp_credentials_file:
            cleanup_credentials_file(self.temp_credentials_file)

    def _load_prompt_config(self) -> Dict[str, Any]:
        """Load prompt configuration from JSON file"""
        try:
            # Get the directory of the current service file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            prompt_config_path = os.path.join(current_dir, 'prompt_base.json')

            if os.path.exists(prompt_config_path):
                with open(prompt_config_path, 'r', encoding='utf-8') as f:
                    prompts = json.load(f)
                logger.info(f"Loaded prompt configuration from {prompt_config_path}")
                return prompts
            else:
                logger.warning(f"Prompt configuration file not found at {prompt_config_path}, using defaults")
                return self._get_default_prompt_config()
        except Exception as e:
            logger.error(f"Error loading prompt configuration: {str(e)}, using defaults")
            return self._get_default_prompt_config()

    def _load_extraction_rules(self) -> Dict[str, Any]:
        """Load image extraction rules from JSON file based on extraction mode"""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))

            # Choose file based on extraction mode
            if self.extraction_mode == 'minimal':
                extraction_rules_path = os.path.join(current_dir, 'image_extraction_min_rules.json')
                logger.info(f"Using MINIMAL extraction mode for token efficiency")
            else:
                extraction_rules_path = os.path.join(current_dir, 'image_extraction_rules.json')
                logger.info(f"Using DETAILED extraction mode for maximum accuracy")

            if os.path.exists(extraction_rules_path):
                with open(extraction_rules_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()
                    rules = json.loads(file_content)

                # Log file details for debugging
                file_size = len(file_content)
                metadata = rules.get('metadata', {})
                version = metadata.get('version', 'unknown')
                mode = metadata.get('mode', 'unknown')
                output_format = metadata.get('output_format', 'unknown')

                logger.info(f"Loaded extraction rules from {extraction_rules_path}")
                logger.info(f"  File size: {file_size} bytes")
                logger.info(f"  Version: {version}, Mode: {mode}, Output format: {output_format}")

                # Verify the prompt template
                template = rules.get('extraction_prompt_template_minimal', rules.get('extraction_prompt_template', ''))
                logger.info(f"  Template length: {len(template)} characters")
                logger.info(f"  Template contains 'file_id': {'file_id' in template}")
                logger.info(f"  Template contains 'materials': {'materials' in template}")
                logger.info(f"  Template contains 'overview': {'overview' in template}")
                logger.info(f"  Template first 200 chars: {template[:200]}")

                return rules
            else:
                logger.warning(f"Extraction rules file not found at {extraction_rules_path}")
                # Try to fall back to the other mode
                fallback_file = 'image_extraction_rules.json' if self.extraction_mode == 'minimal' else 'image_extraction_min_rules.json'
                fallback_path = os.path.join(current_dir, fallback_file)
                if os.path.exists(fallback_path):
                    logger.info(f"Falling back to {fallback_file}")
                    with open(fallback_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                return {}
        except Exception as e:
            logger.error(f"Error loading extraction rules: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {}

    def _load_judgment_prompt(self) -> Dict[str, Any]:
        """Create judgment prompt in-code (no longer using JSON file)"""
        try:
            # Simple, direct prompt structure
            judgment_template = """# ภารกิจ: ตรวจสอบขยะและรายงานเฉพาะข้อผิดพลาดที่แท้จริง

## ข้อมูลที่ได้รับ
- Transaction ID: {transaction_id}
- จำนวน Records: {record_count}
- ประเภทขยะที่แจ้ง: {material_types}

## กฎที่ต้องตรวจสอบ
{rules_json}

## Observations ที่สกัดจากรูปภาพ
{extracted_observations_json}

---

## วิธีตรวจสอบ (ทำตามลำดับ)

### ขั้นที่ 1: เข้าใจหมวดหมู่ขยะ

**การจับคู่ชื่อประเภท:**
- ชื่อที่มี "General" หรือ "Non-Specific General" → หมวด **General Waste** ✅
- ชื่อที่มี "Food" หรือ "Plant" หรือ "Non-Specific Food" → หมวด **Food/Plant** ✅
- ชื่อที่มี "Recycl" หรือ "Plastic" หรือ "Paper" หรือ "Metal" หรือ "Glass" → หมวด **Recyclables** ✅
- ชื่อที่มี "Hazard" หรือ "Batteries" หรือ "Bulbs" → หมวด **Hazardous** ✅

**หมวดหมู่ขยะ:**
1. **Hazardous (ขยะอันตราย)**: แบตเตอรี่, หลอดไฟ, กระป๋องสเปรย์, อุปกรณ์อิเล็กทรอนิกส์
2. **Recyclables (รีไซเคิล)**: กล่องกระดาษ, กระดาษสะอาด, ขวดพลาสติก, กระป๋อง, แก้ว
3. **Food/Plant (เศษอาหาร)**: เศษอาหาร + ถุงชั้นนอก เท่านั้น (อนุโลมภาชนะใสชั้นนอกที่มองเห็นภายใน)
4. **General (ขยะทั่วไป)**: ขยะปนกัน, ขยะเปื้อน, อาหารในภาชนะ

### ขั้นที่ 2: ตรวจแต่ละ Record

สำหรับแต่ละ record ใน observations:

**A) ดูว่าแจ้งประเภทอะไร (declared_material_type)**
- ตัวอย่าง: "Non-Specific Recyclables" → หมวด Recyclables
- ตัวอย่าง: "Food and Plant Waste" → หมวด Food/Plant
- ตัวอย่าง: "General Waste" → หมวด General

**B) ดู overview และ materials ใน observations**
- อ่านว่าเห็นวัสดุอะไรในรูป
- **สำคัญ**: ตัดสินจาก observation เท่านั้น ห้ามคาดเดาสิ่งที่ไม่ได้เขียนไว้
- อนุโลม: "ผง", "เศษเล็กๆ", "วัสดุสีดำ (ผงหรือเศษเล็ก)" → ไม่ต้องตรวจ
- อนุโลม: "ถุงพลาสติกใส", "ภาชนะพลาสติกใส" ชั้นนอก (มองเห็นภายใน) → ไม่ต้องตรวจ

**C) ตัดสิน: วัสดุที่เห็นตรงกับหมวดที่แจ้งหรือไม่?**

ตัวอย่างที่ **ถูกต้อง** (ห้าม flag):
- เห็น "กล่องกระดาษ" → แจ้ง "Non-Specific Recyclables" ✅ ถูก (Recyclables)
- เห็น "แบตเตอรี่" → แจ้ง "Non-Specific Hazardous Waste" ✅ ถูก (Hazardous)
- เห็น "เศษอาหาร" → แจ้ง "Food and Plant Waste" ✅ ถูก (Food/Plant)
- เห็น "กล่องพิซซ่า+ถุงขนม" → แจ้ง "General Waste" ✅ ถูก (ปนกัน = General)
- เห็น "ภาชนะพลาสติกใสใส่ก๋วยเตี๋ยว" → แจ้ง "Food and Plant Waste" ✅ ถูก (อนุโลมภาชนะนอก)

ตัวอย่างที่ **ผิด** (ต้อง flag):
- เห็น "แบตเตอรี่" → แจ้ง "Food Waste" ❌ ผิด! (Hazardous ≠ Food)
- เห็น "กล่องกระดาษ" → แจ้ง "Hazardous Waste" ❌ ผิด! (Recyclables ≠ Hazardous)
- เห็น "เศษอาหารปนหลอดพลาสติก" → แจ้ง "Food Waste" ❌ ผิด! (ปน = General)

**D) ถ้าผิด: สร้าง violation**

**รูปแบบข้อความ (บังคับ):**
```
"Record <record_id>: พบ<วัสดุ1, วัสดุ2, วัสดุ3> (ต้องเป็น <หมวดที่ถูก>) แต่ระบุเป็น <หมวดที่แจ้ง>"
```

**ห้ามใช้ข้อความทั่วไป:**
❌ "ประเภท Material ไม่ตรง"
❌ "รูปภาพไม่ตรงกับข้อมูล"
❌ "พบความผิดปกติ"
❌ "ข้อมูลไม่ถูกต้อง"

**ต้องระบุ:**
1. Record ID เสมอ
2. วัสดุที่เห็นจริงๆ (จาก observations - ระบุชื่อวัสดุเฉพาะเจาะจง)
3. หมวดที่ควรเป็น
4. หมวดที่แจ้งมา

**ตัวอย่างที่ถูกต้อง:**
- ✅ "Record 62712: พบแบตเตอรี่, หลอดไฟ (ต้องเป็น Hazardous) แต่ระบุเป็น Food and Plant Waste"
- ✅ "Record 62713: พบกล่องกระดาษ, ขวดพลาสติก (ต้องเป็น Recyclables) แต่ระบุเป็น General Waste"
- ✅ "Record 62714: พบเศษอาหารปนหลอดพลาสติก, ช้อนพลาสติก, กล่องโฟม (ต้องเป็น General) แต่ระบุเป็น Food and Plant Waste"

**กรณีกฎจำนวน/ประเภท (ไม่มี record_id, ใช้ tr: null):**
- ✅ "มี 3 records ต้องมี 4 records"
- ✅ "มี 2 ประเภทขยะ ต้องมี 4 ประเภท"

### ขั้นที่ 3: ตรวจกฎอื่นๆ

**กฎจำนวน Record:**
- ถ้ากฎบอกต้อง 4 records แต่มี {record_count} records → flag ถ้าไม่ตรง

**กฎประเภทขยะครบ:**
- ถ้ากฎบอกต้อง 4 ประเภท แต่มี {unique_types_count} ประเภท → flag ถ้าไม่ครบ

---

## Output Format

ส่งกลับ JSON เท่านั้น:

```json
{{
  "tr_id": {transaction_id},
  "violations": [
    {{"id": <rule_id>, "m": "<ข้อความ violation>", "tr": <record_id หรือ null>}}
  ]
}}
```

**หากไม่มีข้อผิดพลาด:**
```json
{{
  "tr_id": {transaction_id},
  "violations": []
}}
```

**กฎสำคัญ:**
- ส่งเฉพาะ violations ที่เป็นข้อผิดพลาดจริงๆ
- ถ้าประเภทตรงกัน (ตามการจับคู่ข้างบน) → อย่า flag
- ตัดสินจาก observation เท่านั้น ห้ามคาดเดา
- อย่าใส่ข้อความอื่นนอกจาก JSON

**การเขียนข้อความ violation (สำคัญมาก!):**
- ✅ ต้องระบุ Record ID และวัสดุเฉพาะเจาะจง: "Record 123: พบแบตเตอรี่, หลอดไฟ (ต้องเป็น Hazardous) แต่ระบุเป็น Food Waste"
- ❌ ห้ามใช้ข้อความทั่วไป: "ประเภท Material ไม่ตรง"
- ❌ ห้ามใช้: "รูปภาพไม่ตรงกับข้อมูล"
- ข้อความต้องบอกให้รู้ว่า: พบวัสดุอะไร ควรเป็นหมวดไหน แต่แจ้งเป็นหมวดไหน

เริ่มวิเคราะห์:"""

            return {
                'judgment_prompt_template': judgment_template
            }

        except Exception as e:
            logger.error(f"Error creating judgment prompt: {str(e)}")
            return {}

    def _get_default_prompt_config(self) -> Dict[str, Any]:
        """Get default prompt configuration if JSON file is not available"""
        return {
            "system_instructions": {
                "structured_content": "You are a waste management auditor. Your job is to find ACTUAL ERRORS only.",
                "text_only": "You are a professional waste management auditor with expertise in compliance and quality control."
            },
            "language_mapping": {
                "thai": "Thai (ภาษาไทย)",
                "english": "English",
                "en": "English",
                "th": "Thai (ภาษาไทย)"
            },
            "api_settings": {
                "model_name": "gemini-2.5-flash-lite",
                "temperature": 0.0,
                "thinking_budget": 512
            }
        }

    def sync_ai_audit(self, db: Session, organization_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Perform synchronous AI audit on all pending transactions

        Args:
            db: Database session
            organization_id: Optional organization ID for filtering

        Returns:
            Dict containing audit results
        """
        try:
            logger.info(f"Starting synchronous AI audit for organization: {organization_id}")

            # Get pending transactions
            pending_transactions = self._get_pending_transactions(db, organization_id)
            if not pending_transactions:
                return {
                    'success': True,
                    'message': 'No pending transactions found for audit',
                    'total_transactions': 0,
                    'audit_results': []
                }

            # Get organization-specific audit rules
            audit_rules = self._get_audit_rules(db, organization_id)
            if not audit_rules:
                return {
                    'success': False,
                    'error': 'No audit rules found for this organization. Please configure audit rules first.',
                    'total_transactions': len(pending_transactions)
                }
            # print("---====-=-=", audit_rules)

            # Prepare transaction data with records and images
            transaction_audit_data = self._prepare_transaction_data(db, pending_transactions)

            # Process transactions with AI in multiple threads
            audit_results = self._process_transactions_with_ai(
                transaction_audit_data,
                audit_rules,
                db
            )

            # Check organization's AI audit permission
            allow_ai_audit = False
            if organization_id:
                org = db.query(Organization).filter(Organization.id == organization_id).first()
                if org and hasattr(org, 'allow_ai_audit'):
                    allow_ai_audit = org.allow_ai_audit

            # Update transaction statuses based on audit results
            # Pass allow_ai_audit flag to control whether to update actual status
            updated_count = self._update_transaction_statuses(db, audit_results, allow_ai_audit)

            logger.info(f"AI audit completed. Processed {len(audit_results)} transactions, updated {updated_count}")

            # Save audit history batch
            try:
                self._save_audit_history_batch(
                    db=db,
                    organization_id=organization_id,
                    transaction_ids=[txn.id for txn in pending_transactions],
                    audit_results=audit_results,
                    total_transactions=len(pending_transactions),
                    processed_transactions=len(audit_results),
                    updated_transactions=updated_count
                )
            except Exception as hist_error:
                logger.error(f"Failed to save audit history: {str(hist_error)}")
                # Don't fail the entire audit if history saving fails

            return {
                'success': True,
                'message': f'AI audit completed successfully',
                'total_transactions': len(pending_transactions),
                'processed_transactions': len(audit_results),
                'updated_transactions': updated_count,
                'audit_results': audit_results
            }

        except SQLAlchemyError as e:
            logger.error(f"Database error during AI audit: {str(e)}")
            db.rollback()
            return {
                'success': False,
                'error': f'Database error: {str(e)}',
                'total_transactions': 0
            }
        except Exception as e:
            logger.error(f"Unexpected error during AI audit: {str(e)}")
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'total_transactions': 0
            }

    def _get_pending_transactions(self, db: Session, organization_id: Optional[int] = None) -> List[Transaction]:
        """Get all pending transactions for audit"""
        try:
            # First, let's debug what transactions exist
            debug_query = db.query(Transaction)
            if organization_id:
                debug_query = debug_query.filter(Transaction.organization_id == organization_id).filter(Transaction.is_active == True)

            all_transactions = debug_query.all()
            logger.info(f"DEBUG: Total transactions for org {organization_id}: {len(all_transactions)}")

            # Log status breakdown
            status_counts = {}
            for txn in all_transactions:
                status = txn.status.value if hasattr(txn.status, 'value') else str(txn.status)
                status_counts[status] = status_counts.get(status, 0) + 1

            logger.info(f"DEBUG: Status breakdown: {status_counts}")

            # Now get pending transactions
            query = db.query(Transaction).filter(Transaction.status == TransactionStatus.pending)
            if organization_id:
                query = query.filter(Transaction.organization_id == organization_id)

            transactions = query.all()
            logger.info(f"Found {len(transactions)} pending transactions for audit")
            return transactions

        except Exception as e:
            logger.error(f"Error fetching pending transactions: {str(e)}")
            raise

    def _get_audit_rules(self, db: Session, organization_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get organization-specific audit rules for AI processing with minimal data"""
        try:
            # Get rules for the specific organization only (not global rules)
            query = db.query(AuditRule).filter(
                AuditRule.is_global == False,
                AuditRule.is_active == True
            )

            # Filter by organization_id if provided
            if organization_id:
                query = query.filter(AuditRule.organization_id == organization_id)

            audit_rules = query.all()

            rules_data = []
            for rule in audit_rules:
                rules_data.append({
                    'id': rule.id,  # Database ID for compact reference
                    'rule_id': rule.rule_id,
                    'rule_type': rule.rule_type.value,
                    'rule_name': rule.rule_name,
                    'condition': rule.condition,
                    'thresholds': rule.thresholds,
                    'metrics': rule.metrics,
                    'actions': rule.actions
                })

            logger.info(f"Found {len(rules_data)} active audit rules")
            return rules_data

        except Exception as e:
            logger.error(f"Error fetching audit rules: {str(e)}")
            raise

    def _prepare_transaction_data(self, db: Session, transactions: List[Transaction]) -> List[Dict[str, Any]]:
        """Prepare transaction data with records and images for AI analysis"""
        try:
            transaction_audit_json = []

            for transaction in transactions:
                # Get transaction records for this transaction with main material join
                transaction_records = db.query(TransactionRecord, MainMaterial).join(
                    MainMaterial, TransactionRecord.main_material_id == MainMaterial.id
                ).filter(
                    TransactionRecord.created_transaction_id == transaction.id
                ).all()

                # Prepare transaction data (excluding transaction-level images)
                transaction_data = {
                    'transaction_id': transaction.id,
                    'organization_id': transaction.organization_id,
                    'user_id': transaction.created_by_id,
                    'transaction_method': transaction.transaction_method,
                    'status': transaction.status.value,
                    'weight_kg': float(transaction.weight_kg) if transaction.weight_kg else 0,
                    'total_amount': float(transaction.total_amount) if transaction.total_amount else 0,
                    'transaction_date': transaction.transaction_date.isoformat() if transaction.transaction_date else None,
                    'arrival_date': transaction.arrival_date.isoformat() if transaction.arrival_date else None,
                    'hazardous_level': transaction.hazardous_level,
                    'treatment_method': transaction.treatment_method,
                    'notes': transaction.notes,
                    # Remove transaction-level images - only use record-level images
                    'records': []
                }

                # Add transaction records
                for record, main_material in transaction_records:
                    record_data = {
                        'record_id': record.id,
                        'material_type': main_material.name_en,  # Use joined main_material name
                        'material_name_th': main_material.name_th,  # Also include Thai name
                        'material_code': main_material.code,  # Include material code
                        'quantity': float(record.origin_quantity) if record.origin_quantity else 0,
                        'weight_kg': float(record.origin_weight_kg) if record.origin_weight_kg else 0,
                        'unit': record.unit,
                        'unit_price': float(record.origin_price_per_unit) if record.origin_price_per_unit else 0,
                        'total_value': float(record.total_amount) if record.total_amount else 0,
                        'material_condition': getattr(record, 'material_condition', None),
                        'quality_score': getattr(record, 'quality_score', None),
                        'contamination_level': getattr(record, 'contamination_level', None),
                        'processing_notes': getattr(record, 'processing_notes', None),
                        'images': record.images or [],
                        'status': record.status,
                        'hazardous_level': record.hazardous_level
                    }
                    transaction_data['records'].append(record_data)

                transaction_audit_json.append(transaction_data)

            logger.info(f"Prepared {len(transaction_audit_json)} transactions for AI audit")
            return transaction_audit_json

        except Exception as e:
            logger.error(f"Error preparing transaction data: {str(e)}")
            raise

    def _process_transactions_with_ai(self, transactions_data: List[Dict[str, Any]], audit_rules: List[Dict[str, Any]], db: Session = None) -> List[Dict[str, Any]]:
        """
        Process transactions with Gemini API using multi-threading
        Uses two-phase approach: extraction -> judgment
        """
        try:
            audit_results = []

            logger.info(f"Starting two-phase audit for {len(transactions_data)} transactions")
            logger.info(f"Transaction IDs: {[t['transaction_id'] for t in transactions_data]}")

            # Process transactions in batches using thread pool
            with ThreadPoolExecutor(max_workers=self.max_concurrent_threads) as executor:
                # Submit all transactions for two-phase processing
                future_to_transaction = {
                    executor.submit(self._audit_single_transaction_two_phase, transaction_data, audit_rules, db): transaction_data
                    for transaction_data in transactions_data
                }

                # Collect results as they complete
                for future in as_completed(future_to_transaction):
                    transaction_data = future_to_transaction[future]
                    try:
                        audit_result = future.result()
                        audit_results.append(audit_result)
                        logger.info(f"Completed two-phase audit for transaction {transaction_data['transaction_id']}")
                    except Exception as e:
                        logger.error(f"Error in two-phase audit for transaction {transaction_data['transaction_id']}: {str(e)}")
                        # Add failed audit result with skip flag - transaction will remain pending
                        audit_results.append({
                            'transaction_id': transaction_data['transaction_id'],
                            'audit_status': 'failed',
                            'error': str(e),
                            'triggered_rules': [],
                            'reject_messages': ['Manual review required due to AI audit failure'],
                            'skip_status_update': True,  # Don't update status - leave as pending
                            'token_usage': {
                                'input_tokens': 0,
                                'output_tokens': 0,
                                'total_tokens': 0,
                                'reasoning_tokens': 0,
                                'cached_tokens': 0
                            }
                        })

            logger.info(f"Completed two-phase AI audit for {len(audit_results)} transactions")
            return audit_results

        except Exception as e:
            logger.error(f"Error in multi-threaded AI processing: {str(e)}")
            raise

    def _extract_record_observations(self, record_data: Dict[str, Any], organization_id: int, user_id: int, db: Session = None) -> Dict[str, Any]:
        """
        Phase 1: Extract factual observations from a single transaction record's images
        This reduces cognitive burden by separating observation from judgment
        """
        try:
            record_id = record_data.get('record_id')

            # Validate record_id exists
            if record_id is None:
                logger.error(f"Missing record_id in record_data: {record_data}")
                raise ValueError("Record data missing required 'record_id' field")

            record_images = record_data.get('images', [])

            # If no images, return empty observations array
            if not record_images:
                return {
                    'record_id': record_id,
                    'declared_material_type': record_data.get('material_type'),
                    'has_images': False,
                    'image_observations': []  # Empty array - no images to observe
                }

            # Generate presigned URLs for images
            presigned_urls = self._generate_presigned_urls_for_images(
                record_images,
                organization_id,
                user_id,
                db
            )

            if not presigned_urls:
                # Return per-image observations with error for each image
                error_observations = [
                    {
                        'file_id': img_id,
                        'overview': 'Failed to access image - presigned URL generation failed',
                        'image_quality_score': 0
                    }
                    for img_id in record_images
                ]
                return {
                    'record_id': record_id,
                    'declared_material_type': record_data.get('material_type'),
                    'has_images': True,
                    'image_observations': error_observations
                }

            # Load extraction rules
            # extraction_rules = self._load_extraction_rules()
            # extraction_prompt_template = extraction_rules.get('extraction_prompt_template_minimal', '')

            # if not extraction_prompt_template:
            #     logger.error(f"Record {record_id}: Extraction prompt template not found!")
            #     error_observations = [
            #         {
            #             'file_id': img_id,
            #             'overview': 'Extraction prompt template not configured',
            #             'image_quality_score': 0
            #         }
            #         for img_id in record_images
            #     ]
            #     return {
            #         'record_id': record_id,
            #         'declared_material_type': record_data.get('material_type'),
            #         'has_images': True,
            #         'image_observations': error_observations
            #     }

            json_extract = json.dumps({
                "overview": "<brief overview of transaction materials details of the waste>",
                "image_quality_score": "<image_quality_score between 0 and 10 evaluate for resolution, see clearly, clarity, and overall quality>"
            })

            extraction_prompt_template = f"""extract the following information from the image:
            {json_extract}
            """

            # Process each image individually with threading
            import time
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def extract_single_image(img_file_id, img_url):
                """Extract observation from a single image"""
                try:
                    content_parts = []

                    # Add extraction prompt
                    content_parts.append({
                        "type": "text",
                        "text": extraction_prompt_template
                    })

                    # Add the single image
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": img_url, "detail": "high"}
                    })

                    # Call AI for this single image
                    img_start = time.time()
                    api_response = self._call_gemini_api_structured(content_parts)
                    img_duration = time.time() - img_start

                    # Parse response
                    response_content = api_response.get('content', '') or ''
                    token_usage = api_response.get('usage', {}) or {}

                    # Parse extraction (should return array with one element)
                    parsed = self._parse_extraction_response(response_content, record_id, [img_file_id])

                    # Get the observation for this image
                    if 'image_observations' in parsed and len(parsed['image_observations']) > 0:
                        observation = parsed['image_observations'][0]
                    else:
                        observation = {
                            'file_id': img_file_id,
                            'overview': 'Failed to parse extraction response',
                            'image_quality_score': 0
                        }

                    # Ensure file_id is set correctly
                    observation['file_id'] = img_file_id

                    return {
                        'observation': observation,
                        'token_usage': token_usage,
                        'duration': img_duration
                    }

                except Exception as e:
                    import traceback
                    logger.error(f"Error in extract_single_image for image {img_file_id}: {str(e)}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    return {
                        'observation': {
                            'file_id': img_file_id,
                            'overview': f'Extraction error: {str(e)[:100]}',
                            'image_quality_score': 0
                        },
                        'token_usage': {},
                        'duration': 0
                    }

            # Process all images in parallel
            logger.info(f"Extracting observations from record {record_id} with {len(presigned_urls)} images (parallel processing)")
            extraction_start = time.time()

            image_observations = []
            total_tokens = {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'reasoning_tokens': 0, 'cached_tokens': 0}

            with ThreadPoolExecutor(max_workers=min(len(presigned_urls), 5)) as executor:
                future_to_image = {
                    executor.submit(extract_single_image, img_id, img_url): img_id
                    for img_id, img_url in zip(record_images, presigned_urls)
                }

                for future in as_completed(future_to_image):
                    img_id = future_to_image[future]
                    try:
                        result = future.result()
                        image_observations.append(result['observation'])

                        # Accumulate token usage (handle None values)
                        for key in total_tokens:
                            token_value = result['token_usage'].get(key, 0)
                            if token_value is not None:
                                total_tokens[key] += token_value

                        logger.info(f"Image {img_id}: Extracted in {result['duration']:.2f}s, quality score: {result['observation'].get('image_quality_score', 'N/A')}")
                    except Exception as e:
                        import traceback
                        logger.error(f"Failed to process image {img_id} in extract_single_image: {str(e)}")
                        logger.error(f"Traceback: {traceback.format_exc()}")
                        image_observations.append({
                            'file_id': img_id,
                            'overview': f'Processing error: {str(e)[:100]}',
                            'image_quality_score': 0
                        })

            extraction_duration = time.time() - extraction_start
            logger.info(f"Record {record_id} extraction completed in {extraction_duration:.2f} seconds ({len(image_observations)} images)")

            # Return extracted data
            return {
                'record_id': record_id,
                'declared_material_type': record_data.get('material_type'),
                'has_images': True,
                'image_observations': image_observations,
                'token_usage': total_tokens,
                'extraction_duration_secs': round(extraction_duration, 2)
            }

        except Exception as e:
            logger.error(f"Error extracting observations for record {record_data.get('record_id')}: {str(e)}")
            # Return per-image error observations
            record_images = record_data.get('images', [])
            error_observations = [
                {
                    'file_id': img_id,
                    'overview': f'Extraction error: {str(e)[:100]}',
                    'image_quality_score': 0
                }
                for img_id in record_images
            ] if record_images else []

            return {
                'record_id': record_data.get('record_id'),
                'declared_material_type': record_data.get('material_type'),
                'has_images': bool(record_images),
                'image_observations': error_observations,
                'error': str(e)
            }

    def _parse_extraction_response(self, response_content: str, record_id: int, images: List = None) -> Dict[str, Any]:
        """Parse the AI extraction response into structured data

        New format expects an array of per-image observations:
        [
          {file_id: 123, materials: {...}, overview: "..."},
          {file_id: 124, materials: {...}, overview: "..."}
        ]
        """
        try:
            # Handle None or empty response
            if not response_content:
                # Return error dict without image_observations
                # The caller will create error observations for all images
                return {
                    'record_id': record_id,
                    'error': 'Empty or null response from AI',
                    'raw_text_overview': ''
                }

            # Clean markdown code blocks
            cleaned_response = response_content.strip()
            if cleaned_response.startswith('```'):
                first_newline = cleaned_response.find('\n')
                if first_newline != -1:
                    cleaned_response = cleaned_response[first_newline + 1:]
                if cleaned_response.endswith('```'):
                    cleaned_response = cleaned_response[:-3]
                cleaned_response = cleaned_response.strip()

            # Try to parse JSON
            extraction_data = json.loads(cleaned_response)

            # Check if it's the new array format (array of image observations)
            if isinstance(extraction_data, list):
                # New format: array of per-image observations
                return {
                    'record_id': record_id,
                    'image_observations': extraction_data  # Array of {file_id, materials, overview}
                }
            elif isinstance(extraction_data, dict):
                # Check if it's a single image observation (dict with file_id, materials, overview)
                if 'file_id' in extraction_data and 'materials' in extraction_data:
                    return {
                        'record_id': record_id,
                        'image_observations': [extraction_data]  # Wrap in array
                    }
                else:
                    # Legacy format - return as is
                    extraction_data['record_id'] = record_id
                    return extraction_data
            else:
                # Unknown format
                return {
                    'record_id': record_id,
                    'extraction_summary': str(extraction_data),
                    'parse_warning': 'Unknown format type'
                }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse extraction JSON for record {record_id}: {str(e)}")
            logger.error(f"Response content (first 1000 chars): {response_content[:1000]}")
            # Return error with raw text as overview
            # The AI returned text but it wasn't valid JSON - save the text anyway
            return {
                'record_id': record_id,
                'error': f'JSON parsing failed: {str(e)}',
                'raw_text_overview': response_content.strip(),  # Save full raw response as text
                'extraction_summary': response_content[:500]  # First 500 chars for debugging
            }
        except Exception as e:
            logger.error(f"Unexpected error parsing extraction for record {record_id}: {str(e)}")
            return {
                'record_id': record_id,
                'error': f'Parse error: {str(e)}'
            }

    def _extract_all_records_observations(self, transaction_data: Dict[str, Any], db: Session = None) -> List[Dict[str, Any]]:
        """
        Extract observations from all records in a transaction using nested threading
        Phase 1 of the two-phase audit process
        """
        try:
            records = transaction_data.get('records', [])
            organization_id = transaction_data.get('organization_id')
            user_id = transaction_data.get('user_id')

            if not records:
                logger.warning(f"No records found for transaction {transaction_data.get('transaction_id')}")
                return []

            extracted_observations = []

            # Use ThreadPoolExecutor for parallel record processing
            with ThreadPoolExecutor(max_workers=min(len(records), 10)) as executor:
                future_to_record = {
                    executor.submit(self._extract_record_observations, record, organization_id, user_id, db): record
                    for record in records
                }

                for future in as_completed(future_to_record):
                    record = future_to_record[future]
                    try:
                        observation = future.result()
                        extracted_observations.append(observation)
                        logger.info(f"Extracted observations for record {record.get('record_id')}")
                    except Exception as e:
                        logger.error(f"Failed to extract observations for record {record.get('record_id')}: {str(e)}")
                        # Add error observation with new format
                        record_images = record.get('images', [])
                        error_observations = [
                            {
                                'file_id': img_id,
                                'materials': {},
                                'overview': f'Extraction exception: {str(e)[:100]}'
                            }
                            for img_id in record_images
                        ] if record_images else []

                        extracted_observations.append(error_observations)

                        # extracted_observations.append({
                        #     'record_id': record.get('record_id'),
                        #     'declared_material_type': record.get('material_type'),
                        #     'has_images': bool(record_images),
                        #     'image_observations': error_observations,
                        #     'error': str(e)
                        # })

            logger.info(f"Completed extraction for {len(extracted_observations)} records in transaction {transaction_data.get('transaction_id')}")
            return extracted_observations

        except Exception as e:
            logger.error(f"Error in batch record extraction: {str(e)}")
            return []

    def _judge_transaction_with_observations(
        self,
        transaction_data: Dict[str, Any],
        extracted_observations: List[Dict[str, Any]],
        audit_rules: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Phase 2: Make audit judgment based on extracted observations
        This is lighter weight than processing images directly
        """
        try:
            transaction_id = transaction_data.get('transaction_id')

            # Validate that all observations have record_id (defensive check)
            for i, obs in enumerate(extracted_observations):
                if 'record_id' not in obs or obs['record_id'] is None:
                    logger.error(f"Observation {i} missing record_id: {obs}")
                    raise ValueError(f"Extracted observation at index {i} missing required 'record_id' field")

            # Load judgment prompt
            judgment_config = self._load_judgment_prompt()
            judgment_template = judgment_config.get('judgment_prompt_template', '')

            # Get language name
            language_name = self.language_names.get(self.response_language, 'Thai (ภาษาไทย)')

            # Prepare judgment prompt
            material_types = [r.get('material_type') for r in transaction_data.get('records', [])]
            unique_types = list(set(material_types))

            # judgment_prompt = judgment_template.format(
            #     transaction_id=transaction_id,
            #     record_count=len(transaction_data.get('records', [])),
            #     material_types=material_types,
            #     unique_types_count=len(unique_types),
            #     rules_json=json.dumps(audit_rules, ensure_ascii=False),
            #     extracted_observations_json=json.dumps(extracted_observations, ensure_ascii=False),
            #     language_name=language_name
            # )

#             ```json
# {{
#   "tr_id": {transaction_id},
#   "violations": [
#     {{"id": <rule_id>, "m": "<ข้อความ violation>", "tr": <record_id หรือ null>}}
#   ]
# }}
# ```

# **หากไม่มีข้อผิดพลาด:**
# ```json
# {{
#   "tr_id": {transaction_id},
#   "violations": []
# }}
# ```

# **กฎสำคัญ:**
# - ส่งเฉพาะ violations ที่เป็นข้อผิดพลาดจริงๆ
# - ถ้าประเภทตรงกัน (ตามการจับคู่ข้างบน) → อย่า flag
# - ตัดสินจาก observation เท่านั้น ห้ามคาดเดา
# - อย่าใส่ข้อความอื่นนอกจาก JSON

            rules_json = json.dumps(audit_rules, ensure_ascii=False)
            # return_json_format = json.dumps({
            #     "status": "approved"
            # })

            print(extracted_observations)

            judgment_prompt = f"""
            from the following rules:
            {rules_json}

            and the following observations:
            {json.dumps(extracted_observations, ensure_ascii=False)}

            make a judgment based on the rules and observations.
            return the result in json format.

            if the observations of each transaction_record is not follow 
            the rule, that means has violations so return the list 
            of transaction_id with rule_id and violation message.
            
            if the violation is transaction level such as:
                the transaction must has k images then
                do not add the 'tr' in the violation.

            ```json
            {{
              "violations": [
                {{"id": <rule_id>, "m": "<violation message>"}}
              ]
            }}
            ```
            
            if the violation is record level such as:
                the transaction record say the material type is A but 
                the observation say the material type is B then add the 'tr'.
            
            ```json
            {{
              "violations": [
                {{"id": <rule_id>, "m": "<specific violation message>", "tr": <record_id>}}
              ]
            }}
            ```

            the violation message must be specific to the observation situation.
            ex: จากภาพมีกล่องกระดาษและหลอดอยู่ด้วยจึงไม่ตรงกับประเภทที่ระบุเป็น Food/Plant Waste
            

            **กฎสำคัญ:**
            - ส่งเฉพาะ violations ที่เป็นข้อผิดพลาดจริงๆ
            - ถ้าประเภทตรงกัน (ตามการจับคู่ข้างบน) → อย่า flag
            - ห้ามระบุแบบกว้างๆ เช่น ประเภท Material ไม่ตรงกับรูปภาพ
            - ตัดสินจาก observation เท่านั้น ห้ามคาดเดา
            - ห้ามใช้ข้อความจาก Rule ในการตอบ violations อย่างเดียวต้องเป็นข้อความที่สอดคล้องกับ observation material ด้วย
            - "Non-Specific {{material_type}}" หมายถึง ชนิด material นั้นๆแบบทั่วไป สามารถใช้แทน material_type นั้นๆได้

            **หลักการจำแนกประเภท**
            - ขยะทั่วไป General – ขยะที่รีไซเคิลไม่ได้ เช่น ถุงพลาสติก ฟิล์มอาหาร
            - ขยะรีไซเคิล (Non-Specific) Recyclable – วัสดุที่นำกลับมาใช้ใหม่ได้ เช่น ขวดพลาสติก กระดาษ โลหะ
            - ขยะอันตราย (Non-Specific) Hazardous – ของเสียมีสารพิษหรืออันตราย เช่น ถ่านไฟฉาย หลอดไฟ สเปรย์
            - ขยะเศษอาหาร Food/Plant Waste – ของเหลือจากการกินหรือย่อยสลายได้ เช่น เศษอาหาร เปลือกผลไม้
            - หากขยะรีไซเคิลรวมอยู่กับเศษอาหารหรือขยะทั่วไปให้จัดอยู่ในหมวดขยะทั่วไป
            - ขยะอันตรายไม่สามารถรวมกับขยะรีไซเคิล,เศษอาหารหรือขยะทั่วไปได้

            """

            print(judgment_prompt)

            # Call AI for judgment with timing
            import time
            logger.info(f"Making judgment for transaction {transaction_id} based on {len(extracted_observations)} observations")
            judgment_start = time.time()
            api_response = self._call_gemini_api(judgment_prompt)
            judgment_duration = time.time() - judgment_start

            # Parse judgment response
            response_content = api_response.get('content', '')
            token_usage = api_response.get('usage', {})

            logger.info(f"Transaction {transaction_id} judgment took {judgment_duration:.2f} seconds")

            audit_result = self._parse_ai_response(response_content, transaction_id, audit_rules)

            # Sum up token usage from judgment phase + all extraction phases
            judgment_tokens = {
                'input_tokens': token_usage.get('input_tokens', 0) or 0,
                'output_tokens': token_usage.get('output_tokens', 0) or 0,
                'total_tokens': token_usage.get('total_tokens', 0) or 0,
                'reasoning_tokens': token_usage.get('reasoning_tokens', 0) or 0,
                'cached_tokens': token_usage.get('cached_tokens', 0) or 0
            }

            # Sum tokens and durations from all extraction phases
            extraction_tokens = {
                'input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': 0,
                'reasoning_tokens': 0,
                'cached_tokens': 0
            }

            # Collect per-record durations for observations
            # Structure: {record_id: duration_secs}
            observation_durations = {}

            for obs in extracted_observations:
                obs_tokens = obs.get('token_usage', {})
                if obs_tokens:  # Only add if token_usage exists and is not None
                    extraction_tokens['input_tokens'] += obs_tokens.get('input_tokens', 0) or 0
                    extraction_tokens['output_tokens'] += obs_tokens.get('output_tokens', 0) or 0
                    extraction_tokens['total_tokens'] += obs_tokens.get('total_tokens', 0) or 0
                    extraction_tokens['reasoning_tokens'] += obs_tokens.get('reasoning_tokens', 0) or 0
                    extraction_tokens['cached_tokens'] += obs_tokens.get('cached_tokens', 0) or 0

                # Collect duration for this record's observation
                record_id = obs.get('record_id')
                duration = obs.get('extraction_duration_secs', 0)
                if record_id and duration:
                    observation_durations[record_id] = duration

            # Total tokens = extraction + judgment
            audit_result['token_usage'] = {
                'input_tokens': judgment_tokens['input_tokens'] + extraction_tokens['input_tokens'],
                'output_tokens': judgment_tokens['output_tokens'] + extraction_tokens['output_tokens'],
                'total_tokens': judgment_tokens['total_tokens'] + extraction_tokens['total_tokens'],
                'reasoning_tokens': judgment_tokens['reasoning_tokens'] + extraction_tokens['reasoning_tokens'],
                'cached_tokens': judgment_tokens['cached_tokens'] + extraction_tokens['cached_tokens']
            }

            # Store breakdown with durations
            audit_result['token_breakdown'] = {
                'judgment': judgment_tokens,
                'extraction': extraction_tokens
            }

            # Store duration breakdown
            audit_result['duration_breakdown'] = {
                'judgment_secs': round(judgment_duration, 2),
                'observations': observation_durations  # {record_id: secs}
            }

            logger.info(f"Token usage for transaction {transaction_id}: "
                       f"Extraction={extraction_tokens['total_tokens']}, "
                       f"Judgment={judgment_tokens['total_tokens']}, "
                       f"Total={audit_result['token_usage']['total_tokens']}")

            # Save judgment prompt for debugging
            audit_result['judgment_prompt'] = judgment_prompt
            audit_result['extracted_observations'] = extracted_observations

            logger.info(f"Completed judgment for transaction {transaction_id}")
            return audit_result

        except Exception as e:
            logger.error(f"Error judging transaction {transaction_data.get('transaction_id')}: {str(e)}")
            raise

    def _audit_single_transaction_two_phase(
        self,
        transaction_data: Dict[str, Any],
        audit_rules: List[Dict[str, Any]],
        db: Session = None
    ) -> Dict[str, Any]:
        """
        Two-phase audit process:
        Phase 1: Extract observations from each record (parallel, nested threading)
        Phase 2: Judge transaction based on aggregated observations (single call)
        """
        try:
            transaction_id = transaction_data.get('transaction_id')
            logger.info(f"Starting two-phase audit for transaction {transaction_id}")

            # Phase 1: Extract observations from all records (with nested threading)
            extracted_observations = self._extract_all_records_observations(transaction_data, db)

            # Log extracted observations structure for debugging
            logger.info(f"Transaction {transaction_id}: Extracted {len(extracted_observations)} observations")
            for obs in extracted_observations:
                record_id = obs.get('record_id')
                has_image_obs = 'image_observations' in obs
                logger.info(f"  Record {record_id}: has_image_observations={has_image_obs}, keys={list(obs.keys())}")

            if not extracted_observations:
                logger.warning(f"No observations extracted for transaction {transaction_id}")
                return self._create_default_audit_result(transaction_id, error="No observations could be extracted")

            # Phase 2: Make judgment based on observations
            audit_result = self._judge_transaction_with_observations(
                transaction_data,
                extracted_observations,
                audit_rules
            )

            logger.info(f"Completed two-phase audit for transaction {transaction_id}")
            return audit_result

        except Exception as e:
            logger.error(f"Error in two-phase audit for transaction {transaction_data.get('transaction_id')}: {str(e)}")
            return self._create_default_audit_result(
                transaction_data.get('transaction_id'),
                error=f"Two-phase audit failed: {str(e)}"
            )

    def _audit_single_transaction(self, transaction_data: Dict[str, Any], audit_rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Audit a single transaction using Gemini API with structured record-image grouping"""
        try:
            # Prepare base prompt for Gemini
            # print(transaction_data)
            prompt = self._create_audit_prompt(transaction_data, audit_rules)

            # Structure: Group images with their corresponding transaction records
            records = transaction_data.get('records', [])
            has_images = False

            # Prepare structured content for API call
            content_parts = []

            # Add main prompt
            content_parts.append({
                "type": "text",
                "text": prompt
            })

            # Add transaction-level images first (if any)
            transaction_images = transaction_data.get('images', [])
            if transaction_images:
                presigned_txn_images = self._generate_presigned_urls_for_images(
                    transaction_images,
                    transaction_data.get('organization_id', 1),
                    transaction_data.get('user_id', 1)
                )

                if presigned_txn_images:
                    content_parts.append({
                        "type": "text",
                        "text": "TRANSACTION-LEVEL IMAGES:"
                    })
                    for img_url in presigned_txn_images:
                        content_parts.append({
                            "type": "image_url",
                            "image_url": {"url": img_url, "detail": "high"}
                        })
                    has_images = True

            # Add each record with its images
            for idx, record in enumerate(records):
                record_images = record.get('images', [])
                if record_images:
                    # Generate presigned URLs for this record's images
                    presigned_record_images = self._generate_presigned_urls_for_images(
                        record_images,
                        transaction_data.get('organization_id', 1),
                        transaction_data.get('user_id', 1)
                    )

                    if presigned_record_images:
                        # Add record context
                        content_parts.append({
                            "type": "text",
                            "text": f"RECORD #{idx+1} (ID:{record.get('record_id')}) - {record.get('material_type')} - {record.get('weight_kg')}kg:"
                        })

                        # Add record's images
                        for img_url in presigned_record_images:
                            content_parts.append({
                                "type": "image_url",
                                "image_url": {"url": img_url, "detail": "high"}
                            })
                        has_images = True
                        logger.info(f"Added {len(presigned_record_images)} images for record {record.get('record_id')}")

            # Call API with structured content
            if has_images:
                logger.info(f"Processing transaction {transaction_data['transaction_id']} with {len([p for p in content_parts if p['type'] == 'image_url'])} images")
                api_response = self._call_gemini_api_structured(content_parts)
            else:
                logger.info(f"Processing transaction {transaction_data['transaction_id']} with text-only analysis")
                api_response = self._call_gemini_api(prompt)

            # Extract content and usage from API response
            response_content = api_response.get('content', '')
            token_usage = api_response.get('usage', {})

            # print(response_content)
            # Parse AI response
            audit_result = self._parse_ai_response(response_content, transaction_data['transaction_id'], audit_rules)

            # Add token usage information including reasoning tokens
            audit_result['token_usage'] = {
                'input_tokens': token_usage.get('input_tokens', 0),
                'output_tokens': token_usage.get('output_tokens', 0),
                'total_tokens': token_usage.get('total_tokens', 0),
                'reasoning_tokens': token_usage.get('reasoning_tokens', 0),
                'cached_tokens': token_usage.get('cached_tokens', 0)
            }

            # Save the audit prompt for debugging
            audit_result['audit_prompt'] = prompt

            logger.info(f"Transaction {transaction_data['transaction_id']} used {token_usage.get('total_tokens', 0)} tokens "
                       f"(input: {token_usage.get('input_tokens', 0)}, output: {token_usage.get('output_tokens', 0)}, "
                       f"reasoning: {token_usage.get('reasoning_tokens', 0)})")

            return audit_result

        except Exception as e:
            logger.error(f"Error auditing transaction {transaction_data['transaction_id']}: {str(e)}")
            raise

    def _generate_presigned_urls_for_images(self, image_identifiers: List, organization_id: int, user_id: int, db: Session = None) -> List[str]:
        """
        Generate presigned URLs for images to allow Gemini API access

        Args:
            image_identifiers: List of file IDs (int) or URLs (str) - auto-detects type
            organization_id: Organization ID for access control
            user_id: User ID for audit trail
            db: Database session (required if using file IDs)

        Returns:
            List of presigned URLs for viewing
        """
        try:
            if not self.presigned_url_service:
                logger.warning("Presigned URL service not available")
                return []

            if not image_identifiers:
                return []

            # Detect if we're working with file IDs or URLs
            first_item = image_identifiers[0]
            using_file_ids = isinstance(first_item, int)

            if using_file_ids:
                # New approach: Use file IDs
                if not db:
                    logger.error("Database session required when using file IDs")
                    return []

                logger.info(f"Generating presigned URLs for {len(image_identifiers)} file IDs")
                result = self.presigned_url_service.get_transaction_file_view_presigned_urls_by_ids(
                    file_ids=image_identifiers,
                    db=db,
                    organization_id=organization_id,
                    user_id=user_id,
                    expiration_seconds=7200  # 2 hours expiration for audit processing
                )

                if result.get('success'):
                    presigned_urls = []
                    presigned_by_id = result.get('presigned_urls', {})
                    for file_id in image_identifiers:
                        if file_id in presigned_by_id:
                            presigned_url = presigned_by_id[file_id].get('view_url')
                            if presigned_url:
                                presigned_urls.append(presigned_url)
                                logger.info(f"Generated presigned URL for file ID {file_id}")

                    logger.info(f"Successfully generated {len(presigned_urls)} presigned URLs from file IDs")
                    return presigned_urls
                else:
                    logger.error(f"Failed to generate presigned URLs from file IDs: {result.get('message')}")
                    return []

            else:
                # Legacy approach: Use file URLs
                logger.info(f"Generating presigned URLs for {len(image_identifiers)} file URLs (legacy)")
                result = self.presigned_url_service.get_transaction_file_view_presigned_urls(
                    file_urls=image_identifiers,
                    organization_id=organization_id,
                    user_id=user_id,
                    expiration_seconds=7200,  # 2 hours expiration for audit processing
                    db=db  # Pass db session to check file sources
                )

                if result.get('success'):
                    presigned_urls = []
                    for url_data in result.get('presigned_urls', []):
                        presigned_url = url_data.get('view_url')
                        if presigned_url:
                            presigned_urls.append(presigned_url)
                            logger.info(f"Generated presigned URL for {url_data.get('original_url')}")

                    logger.info(f"Successfully generated {len(presigned_urls)} presigned URLs from URLs")
                    return presigned_urls
                else:
                    logger.error(f"Failed to generate presigned URLs from URLs: {result.get('message')}")
                    return []

        except Exception as e:
            logger.error(f"Error generating presigned URLs: {str(e)}")
            return []

    def _get_example_messages(self, language_name: str) -> str:
        """Get example rejection messages in the specified language"""
        example_messages = self.prompts.get('example_messages', {})
        
        if 'Thai' in language_name or 'ไทย' in language_name:
            return example_messages.get('thai', example_messages.get('english', ''))
        else:  # English
            return example_messages.get('english', '')

    def _create_audit_prompt(self, transaction_data: Dict[str, Any], audit_rules: List[Dict[str, Any]]) -> str:
        """Create an optimized prompt using the JSON configuration template"""

        # Get language name for prompt
        language_name = self.language_names.get(self.response_language, 'Thai (ภาษาไทย)')

        # Create compact rules reference with ID-based lookup
        rules_compact = []
        for rule in audit_rules:
            rules_compact.append({
                'id': rule.get('id'),
                'rule_id': rule.get('rule_id'),
                'name': rule.get('rule_name'),
                'type': rule.get('rule_type'),
                'condition': rule.get('condition'),
                'thresholds': rule.get('thresholds'),
                'metrics': rule.get('metrics')
            })

        # Get unique material types count
        unique_types_count = len(set([r.get('material_type') for r in transaction_data.get('records', [])]))
        record_count = len(transaction_data.get('records', []))
        material_types = [r.get('material_type') for r in transaction_data.get('records', [])]

        # Get prompt template from JSON configuration
        prompt_template = self.prompts.get('audit_prompt', {}).get('template', '')
        
        # Format the template with variables
        prompt = prompt_template.format(
            record_count=record_count,
            unique_types_count=unique_types_count,
            material_types=material_types,
            rules_json=json.dumps(rules_compact, ensure_ascii=False),
            transaction_json=json.dumps(transaction_data, ensure_ascii=False),
            language_name=language_name,
            transaction_id=transaction_data.get('transaction_id', 0)
        )
        
        return prompt

    def _enhance_prompt_for_images(self, base_prompt: str, images: List[str], transaction_data: Dict[str, Any]) -> str:
        """Enhance the audit prompt with image analysis instructions from JSON configuration"""
        
        # Get image analysis instructions from JSON configuration
        image_config = self.prompts.get('image_analysis_instructions', {})
        image_instructions = image_config.get('template', '')
        
        # Check if image analysis is enabled
        if not image_config.get('enabled', True):
            return base_prompt

        enhanced_prompt = base_prompt + image_instructions
        return enhanced_prompt

    def _call_gemini_api_structured(self, content_parts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Call Vertex AI API with structured content parts (text + images)

        Returns:
            Dict containing 'content' (response text) and 'usage' (token information)
        """
        try:
            if not GENAI_AVAILABLE or not self.client:
                raise ImportError("Google GenAI package not installed or Vertex AI client not initialized. "
                                "Install with: pip install google-genai. "
                                "Ensure VERTEX_AI_PROJECT_ID and VERTEX_AI_LOCATION are configured.")

            # Convert content_parts to Gemini format
            gemini_content = []
            system_instruction = self.prompts.get('system_instructions', {}).get('structured_content', 
                'You are a waste management auditor. Your job is to find ACTUAL ERRORS only.')

            for part in content_parts:
                if part['type'] == 'text':
                    gemini_content.append(part['text'])
                elif part['type'] == 'image_url':
                    # Gemini expects image data directly or PIL Image
                    # For presigned URLs, download the image
                    import requests
                    from PIL import Image
                    from io import BytesIO

                    try:
                        response = requests.get(part['image_url']['url'], timeout=10)
                        img = Image.open(BytesIO(response.content))
                        gemini_content.append(img)
                    except Exception as img_error:
                        logger.warning(f"Failed to load image: {str(img_error)}")
                        gemini_content.append(f"[Image unavailable: {str(img_error)}]")

            # Generate response using the new SDK
            # print(gemini_content)
            api_settings = self.prompts.get('api_settings', {})
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=gemini_content,
                config={
                    "system_instruction": system_instruction,
                    "temperature": api_settings.get('temperature', 0.0),
                    "thinkingConfig": {
                        # "thinkingBudget": api_settings.get('thinking_budget', 512)
                        "thinkingBudget": 0
                    },
                    "max_output_tokens": 2048  # Limit output to prevent hallucination
                }
            )

            # Extract token usage information including reasoning tokens
            usage_metadata = response.usage_metadata if hasattr(response, 'usage_metadata') else None
            usage_info = {
                'input_tokens': usage_metadata.prompt_token_count if usage_metadata else 0,
                'output_tokens': usage_metadata.candidates_token_count if usage_metadata else 0,
                'total_tokens': usage_metadata.total_token_count if usage_metadata else 0,
                'reasoning_tokens': getattr(usage_metadata, 'thoughts_token_count', 0) if usage_metadata else 0,
                'cached_tokens': getattr(usage_metadata, 'cached_content_token_count', 0) if usage_metadata else 0
            }

            logger.info(f"Vertex AI API response - Tokens: {usage_info['total_tokens']} (reasoning: {usage_info['reasoning_tokens']})")

            return {
                'content': response.text,
                'usage': usage_info
            }

        except Exception as e:
            logger.error(f"Vertex AI API call failed: {str(e)}")
            raise

    def _call_gemini_api(self, prompt: str, images: List[str] = None) -> Dict[str, Any]:
        """
        Call Vertex AI API for audit analysis (text-only fallback)

        Returns:
            Dict containing 'content' (response text) and 'usage' (token information)
        """
        try:
            if not GENAI_AVAILABLE or not self.client:
                raise ImportError("Google GenAI package not installed or Vertex AI client not initialized. "
                                "Install with: pip install google-genai. "
                                "Ensure VERTEX_AI_PROJECT_ID and VERTEX_AI_LOCATION are configured.")

            # Prepare content
            api_settings = self.prompts.get('api_settings', {})
            full_prompt = f"{prompt}\n\n{api_settings.get('response_suffix', 'Respond only with valid JSON format as specified above.')}"
            system_instruction = self.prompts.get('system_instructions', {}).get('text_only', 
                'You are a professional waste management auditor with expertise in compliance and quality control.')

            # logger.info(full_prompt)
            # Generate response using the new SDK
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt,
                config={
                    "system_instruction": system_instruction,
                    "temperature": api_settings.get('temperature', 0.0),
                    "thinkingConfig": {
                        "thinkingBudget": api_settings.get('thinking_budget', 512)
                    },
                    "max_output_tokens": 2048  # Increased from 1024 to prevent truncation
                }
            )

            # Extract token usage information including reasoning tokens
            usage_metadata = response.usage_metadata if hasattr(response, 'usage_metadata') else None
            usage_info = {
                'input_tokens': usage_metadata.prompt_token_count if usage_metadata else 0,
                'output_tokens': usage_metadata.candidates_token_count if usage_metadata else 0,
                'total_tokens': usage_metadata.total_token_count if usage_metadata else 0,
                'reasoning_tokens': getattr(usage_metadata, 'thoughts_token_count', 0) if usage_metadata else 0,
                'cached_tokens': getattr(usage_metadata, 'cached_content_token_count', 0) if usage_metadata else 0
            }

            # logger.info(f"Vertex AI API text-only response - Tokens: {usage_info['total_tokens']} (reasoning: {usage_info['reasoning_tokens']})")

            return {
                'content': response.text,
                'usage': usage_info
            }

        except Exception as e:
            logger.error(f"Vertex AI API call failed: {str(e)}")
            raise

    def _parse_ai_response(self, ai_response: str, transaction_id: int, audit_rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse optimized AI response with ID-based violations"""
        try:
            # Strip markdown code blocks if present (Gemini often wraps JSON in ```json ... ```)
            cleaned_response = ai_response.strip()

            # Remove markdown code block markers
            if cleaned_response.startswith('```'):
                # Find the first newline after the opening ```
                first_newline = cleaned_response.find('\n')
                if first_newline != -1:
                    cleaned_response = cleaned_response[first_newline + 1:]

                # Remove closing ```
                if cleaned_response.endswith('```'):
                    cleaned_response = cleaned_response[:-3]

                cleaned_response = cleaned_response.strip()

            # Try to parse JSON response
            try:
                ai_data = json.loads(cleaned_response)
            except json.JSONDecodeError as parse_err:
                # Try to fix common JSON issues
                logger.warning(f"Initial JSON parse failed: {str(parse_err)}, attempting to fix")

                # If response is truncated mid-string, try to close it
                if "Unterminated string" in str(parse_err):
                    # Try adding closing quotes and brackets
                    fixed_response = cleaned_response

                    # Count open brackets/braces
                    open_braces = fixed_response.count('{') - fixed_response.count('}')
                    open_brackets = fixed_response.count('[') - fixed_response.count(']')

                    # If there's an unterminated string, add quote
                    if not fixed_response.rstrip().endswith(('"', '}', ']')):
                        fixed_response += '"'

                    # Close any open arrays/objects
                    fixed_response += ']' * open_brackets
                    fixed_response += '}' * open_braces

                    try:
                        ai_data = json.loads(fixed_response)
                        logger.info(f"Successfully fixed truncated JSON for transaction {transaction_id}")
                    except:
                        # If fix didn't work, raise original error
                        raise parse_err
                else:
                    raise parse_err

            print("<<<<<<<", ai_data)
            violations = ai_data.get('violations', [])

            # Build audit rules map by database ID for lookup
            audit_rules_map_by_id = {rule.get('id'): rule for rule in audit_rules}

            # Process violations
            reject_messages = []
            triggered_rules = []

            for violation in violations:
                rule_db_id = violation.get('id')
                msg = violation.get('m', violation.get('msg', ''))  # Try 'm' first, fallback to 'msg'
                transaction_record_id = violation.get('tr')  # Get transaction_record_id from violation

                # Validate that message is not empty
                if not msg or msg.strip() == '':
                    logger.warning(f"Empty message in violation for rule {rule_db_id}, transaction_record {transaction_record_id}")
                    msg = f"Rule {rule_db_id} triggered (no message provided)"

                # Lookup rule to get actions
                rule = audit_rules_map_by_id.get(rule_db_id)
                if not rule:
                    logger.warning(f"Rule with ID {rule_db_id} not found in audit rules")
                    continue

                rule_id = rule.get('rule_id')
                rule_actions = rule.get('actions', [])

                # Determine action type from rule
                has_reject = any(
                    action.get('type') == 'system_action' and action.get('action', '').lower() == 'reject'
                    for action in rule_actions
                )

                triggered_rules.append({
                    'rule_id': rule_id,
                    'rule_db_id': rule_db_id,
                    'triggered': True,
                    'message': msg,
                    'has_reject': has_reject,
                    'transaction_record_id': transaction_record_id  # Add transaction_record_id to triggered rules
                })

                # Add to reject messages if it has reject action
                if has_reject:
                    reject_messages.append(f"[{rule_id}] {msg}")

            # Determine final status
            final_status = 'rejected' if reject_messages else 'approved'

            # Structure the final audit result
            audit_result = {
                'transaction_id': transaction_id,
                'audit_status': final_status,
                'triggered_rules': triggered_rules,
                'reject_messages': reject_messages,
                'audited_at': datetime.now(timezone.utc).isoformat(),
                'total_rules_evaluated': len(audit_rules),
                'rules_triggered': len(triggered_rules)
            }

            return audit_result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response for transaction {transaction_id}: {str(e)}")
            logger.error(f"Response content: {ai_response}")
            return self._create_default_audit_result(transaction_id, error=f'JSON parsing error: {str(e)}')
        except Exception as e:
            logger.error(f"Unexpected error processing AI response for transaction {transaction_id}: {str(e)}")
            return self._create_default_audit_result(transaction_id, error=f'Processing error: {str(e)}')

    def _update_transaction_statuses(self, db: Session, audit_results: List[Dict[str, Any]], allow_ai_audit: bool = False) -> int:
        """
        Update transaction statuses based on audit results

        Args:
            db: Database session
            audit_results: List of audit results
            allow_ai_audit: If True, update transaction status; if False, only update ai_audit_status
        """
        try:
            updated_count = 0

            for result in audit_results:
                # Skip transactions that failed to audit (should remain pending)
                if result.get('skip_status_update', False):
                    logger.warning(f"Skipping status update for transaction {result['transaction_id']} due to audit failure: {result.get('error')}")
                    continue

                transaction_id = result['transaction_id']
                audit_status = result['audit_status']

                transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
                if transaction:
                    # ALWAYS set ai_audit_status regardless of allow_ai_audit
                    if audit_status == 'approved':
                        transaction.ai_audit_status = AIAuditStatus.approved
                    elif audit_status == 'rejected':
                        transaction.ai_audit_status = AIAuditStatus.rejected

                    # ONLY update transaction status if allow_ai_audit is True
                    if allow_ai_audit:
                        if audit_status == 'approved':
                            transaction.status = TransactionStatus.approved
                        elif audit_status == 'rejected':
                            transaction.status = TransactionStatus.rejected

                    # Set ai_audit_date to mark when AI audit was performed
                    transaction.ai_audit_date = datetime.now(timezone.utc)

                    # Extract triggered rule IDs
                    reject_triggers = []

                    triggered_rules = result.get('triggered_rules', [])
                    for triggered_rule in triggered_rules:
                        rule_id = triggered_rule.get('rule_id')
                        has_reject = triggered_rule.get('has_reject', False)

                        if has_reject and rule_id:
                            reject_triggers.append(rule_id)

                    # Save reject triggers to transaction
                    transaction.reject_triggers = reject_triggers
                    transaction.warning_triggers = []  # Reset warnings since we now only track rejections

                    # Extract observations and build audits structure
                    extracted_observations = result.get('extracted_observations', [])

                    # Debug logging
                    logger.info(f"Transaction {transaction_id}: Found {len(extracted_observations)} extracted observations in result")
                    if not extracted_observations:
                        logger.warning(f"Transaction {transaction_id}: No extracted_observations in audit result! Keys: {list(result.keys())}")

                    audits_by_record = {}

                    # Get transaction records from database to access image file IDs
                    transaction_records = db.query(TransactionRecord).filter(
                        TransactionRecord.created_transaction_id == transaction_id,
                        TransactionRecord.is_active == True
                    ).all()

                    # Create a map of record_id to image file IDs
                    record_images_map = {
                        record.id: record.images or []
                        for record in transaction_records
                    }

                    for obs in extracted_observations:
                        record_id = obs.get('record_id')
                        if record_id:
                            # Get image file IDs for this record
                            image_file_ids = record_images_map.get(record_id, [])
                            record_images = []

                            # Check if we have new per-image observations format
                            if 'image_observations' in obs:
                                # New format: array of {file_id, materials, overview}
                                image_observations = obs['image_observations']

                                # Create a map of file_id to observation for quick lookup
                                obs_by_file_id = {img_obs['file_id']: img_obs for img_obs in image_observations if 'file_id' in img_obs}

                                # Process each file_id in the record
                                for file_id in image_file_ids:
                                    if file_id in obs_by_file_id:
                                        img_obs = obs_by_file_id[file_id]
                                        # Store full structured observation
                                        record_images.append({
                                            'id': file_id,
                                            'obs': img_obs  # Full dict with file_id, materials, overview
                                        })

                                        # Also save to file.observation in database
                                        try:
                                            from ....models.cores.files import File
                                            file_record = db.query(File).filter(File.id == file_id).first()
                                            if file_record:
                                                file_record.observation = img_obs  # Save {file_id, materials, overview}
                                                # logger.info(f"Saved observation to file {file_id}: {len(img_obs.get('materials', {}))} materials")
                                        except Exception as file_err:
                                            logger.error(f"Failed to save observation to file {file_id}: {str(file_err)}")
                                    else:
                                        # File ID not in observations (shouldn't happen)
                                        logger.warning(f"No observation found for file {file_id} in record {record_id}")
                                        record_images.append({
                                            'id': file_id,
                                            'obs': {'error': 'No observation extracted for this image'}
                                        })

                                logger.info(f"Transaction {transaction_id}, Record {record_id}: Processed {len(image_observations)} image observations")

                            else:
                                # Legacy format or error case - handle gracefully
                                logger.warning(f"Transaction {transaction_id}, Record {record_id}: No image_observations in extraction result. Keys: {list(obs.keys())}")

                                # Check if there's an error field
                                if 'error' in obs:
                                    error_msg = obs.get('error', 'Unknown extraction error')
                                    # Check if we have raw text from failed JSON parsing
                                    raw_text = obs.get('raw_text_overview', '')

                                    logger.error(f"Transaction {transaction_id}, Record {record_id}: Extraction error: {error_msg}")

                                    # If we have raw text, use it as overview; otherwise use error message
                                    if raw_text:
                                        logger.info(f"Transaction {transaction_id}, Record {record_id}: Using raw text response ({len(raw_text)} chars)")
                                        overview_text = raw_text
                                    else:
                                        overview_text = f'Extraction failed: {error_msg}'

                                    # Create observations for each image with error flag
                                    for file_id in image_file_ids:
                                        observation_data = {
                                            'file_id': file_id,
                                            'materials': {},
                                            'overview': overview_text,
                                            'error': error_msg  # Add error key
                                        }
                                        record_images.append({
                                            'id': file_id,
                                            'obs': observation_data
                                        })

                                        # Store in database
                                        try:
                                            from ....models.cores.files import File
                                            file_record = db.query(File).filter(File.id == file_id).first()
                                            if file_record:
                                                file_record.observation = observation_data
                                        except Exception as file_err:
                                            logger.error(f"Failed to save observation to file {file_id}: {str(file_err)}")
                                else:
                                    # Try to build observation from legacy fields
                                    observation_text = None

                                    if 'extraction_summary' in obs:
                                        observation_text = obs.get('extraction_summary', '')
                                    elif any(key in obs for key in ['items', 'hazardous', 'contamination', 'container', 'visibility']):
                                        obs_parts = []
                                        if obs.get('items'):
                                            obs_parts.append(f"Items: {obs['items']}")
                                        if obs.get('hazardous') and obs['hazardous'] != 'None':
                                            obs_parts.append(f"Hazardous: {obs['hazardous']}")
                                        if obs.get('contamination'):
                                            obs_parts.append(f"Contamination: {obs['contamination']}")
                                        if obs.get('container'):
                                            obs_parts.append(f"Container: {obs['container']}")
                                        if obs.get('visibility'):
                                            obs_parts.append(f"Visibility: {obs['visibility']}")
                                        if obs.get('red_flags') and len(obs['red_flags']) > 0:
                                            obs_parts.append(f"Red Flags: {', '.join(obs['red_flags'])}")
                                        observation_text = '; '.join(obs_parts) if obs_parts else None

                                    if not observation_text:
                                        skip_keys = {'record_id', 'declared_material_type', 'has_images', 'error', 'violations', 'token_usage'}
                                        text_parts = []
                                        for key, value in obs.items():
                                            if key not in skip_keys and value:
                                                if isinstance(value, str):
                                                    text_parts.append(f"{key}: {value}")
                                                elif isinstance(value, list) and len(value) > 0:
                                                    text_parts.append(f"{key}: {', '.join(str(v) for v in value)}")
                                                elif isinstance(value, dict) and len(value) > 0:
                                                    text_parts.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
                                        observation_text = '; '.join(text_parts) if text_parts else 'Extraction returned empty response - no data extracted'

                                    logger.info(f"Transaction {transaction_id}, Record {record_id}: Created legacy observation text ({len(observation_text)} chars)")

                                    # Apply same observation to all images in record (legacy behavior)
                                    for file_id in image_file_ids:
                                        record_images.append({
                                            'id': file_id,
                                            'obs': observation_text
                                        })

                            audits_by_record[record_id] = {
                                'images': record_images
                            }

                    # Build violations list with transaction_record_id
                    # Format: {"tr": <record_id>, "id": <rule_id>, "m": <message>}
                    # "tr" is optional - only included for transaction_record level violations
                    violations = []
                    for tr in triggered_rules:
                        if tr.get('has_reject'):
                            violation = {
                                'id': tr.get('rule_db_id'),  # triggered rule ID
                                'm': tr.get('message')  # message
                            }
                            # Only add 'tr' if it's a transaction_record level violation
                            if tr.get('transaction_record_id'):
                                violation['tr'] = tr.get('transaction_record_id')
                            violations.append(violation)

                    # Separate token usage from audit notes
                    # Format for ai_audit_note: {status, audits: {record_id: {images: [{id, obs}]}}, v: [violations]}
                    # Format for audit_tokens: {t: {input, output, thinking}, tr: {input, output, thinking}}
                    token_usage = result.get('token_usage', {})

                    # Create audit notes WITHOUT token data (moved to separate column)
                    audit_notes = {
                        'status': audit_status,  # approved | rejected | pending
                        'audits': audits_by_record,  # {record_id: {images: [{id, obs}]}}
                        'v': violations  # [{tr?, id, m}] - violations with optional tr for record-level
                    }

                    # Create token data for separate column with breakdown
                    # Extract token breakdown if available
                    token_breakdown = result.get('token_breakdown', {})
                    judgment_tokens = token_breakdown.get('judgment', {})
                    extraction_tokens = token_breakdown.get('extraction', {})

                    # Extract duration breakdown if available
                    duration_breakdown = result.get('duration_breakdown', {})

                    token_data = {
                        't': {  # Transaction judgment tokens
                            'input': judgment_tokens.get('input_tokens', 0),
                            'output': judgment_tokens.get('output_tokens', 0),
                            'thinking': judgment_tokens.get('reasoning_tokens', 0)
                        },
                        'tr': {  # Transaction record observation tokens (sum of all extractions)
                            'input': extraction_tokens.get('input_tokens', 0),
                            'output': extraction_tokens.get('output_tokens', 0),
                            'thinking': extraction_tokens.get('reasoning_tokens', 0)
                        },
                        'durations': {  # Time spent in seconds
                            'jud': duration_breakdown.get('judgment_secs', 0),  # Judgment phase
                            'obs': duration_breakdown.get('observations', {})  # Observation phase per record {record_id: secs}
                        }
                    }

                    # Note: violations are stored in THREE places:
                    # 1. transaction.ai_audit_note['v'] - detailed format with optional 'tr'
                    # 2. transaction.reject_triggers - array of rule_db_ids
                    # 3. transaction_audit.audit_notes['v'] - same as ai_audit_note['v']

                    # TransactionAudit table format (matches transaction.ai_audit_note format)
                    legacy_audit_notes = {
                        'status': audit_status,  # status (full word for clarity)
                        'audits': audits_by_record,  # {record_id: {images: [{id, obs}]}}
                        'v': violations  # [{tr?, id, m}] - same format as ai_audit_note
                    }

                    print("-=-=-=-==-=--=-=", audit_notes)

                    # Save to THREE places:
                    # 1. Save to transaction.ai_audit_note (audit observations and status)
                    transaction.ai_audit_note = audit_notes

                    # 2. Save to transaction.audit_tokens (token usage data)
                    transaction.audit_tokens = token_data

                    # Mark the JSONB fields as modified for SQLAlchemy to detect changes
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(transaction, 'ai_audit_note')
                    flag_modified(transaction, 'audit_tokens')

                    logger.info(f"Setting ai_audit_note for transaction {transaction_id}: {len(extracted_observations)} observations, {len(violations)} violations")
                    logger.info(f"Setting audit_tokens for transaction {transaction_id}: "
                               f"t(judgment)={{input={token_data['t']['input']}, output={token_data['t']['output']}, thinking={token_data['t']['thinking']}}}, "
                               f"tr(observation)={{input={token_data['tr']['input']}, output={token_data['tr']['output']}, thinking={token_data['tr']['thinking']}}}")

                    # 3. Create TransactionAudit record (legacy format for audit history table)
                    transaction_audit = TransactionAudit(
                        transaction_id=transaction_id,
                        audit_notes=legacy_audit_notes,  # Use legacy format here
                        by_human=False,  # AI audit
                        auditor_id=None,  # AI has no user ID
                        organization_id=transaction.organization_id,
                        audit_type='ai_sync',
                        processing_time_ms=result.get('processing_time_ms'),
                        token_usage=result.get('token_usage', {}),
                        model_version=result.get('model_version', 'gemini-2.5-flash-lite'),
                        created_date=int(datetime.now(timezone.utc).timestamp() * 1000),
                        created_by_id=None  # System-generated
                    )
                    db.add(transaction_audit)

                    # Save audit prompt to notes for debugging
                    audit_prompt = result.get('audit_prompt', '')
                    # print("--------------AAAAAAAA--------------", audit_prompt)
                    # if audit_prompt:
                    #     audit_note = f"\n\n--- AI Audit Debug Info (สำหรับ debug) ---\nAudited at: {result.get('audited_at')}\nStatus: {audit_status}\nTokens: {result.get('token_usage', {}).get('total_tokens', 0)}\n\n=== Audit Prompt ===\n{audit_prompt[:2000]}..."  # Limit to first 2000 chars

                    #     if transaction.notes:
                    #         transaction.notes += audit_note
                    #     else:
                    #         transaction.notes = audit_note

                    updated_count += 1

            db.commit()
            logger.info(f"Updated {updated_count} transactions. AI audit enabled: {allow_ai_audit}")

            # Verify the data was saved by re-querying
            for result in audit_results:
                if not result.get('skip_status_update', False):
                    transaction_id = result['transaction_id']
                    verification_txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
                    if verification_txn:
                        if verification_txn.ai_audit_note:
                            logger.info(f"✓ Transaction {transaction_id}: ai_audit_note saved successfully with keys: {list(verification_txn.ai_audit_note.keys())}")
                        else:
                            logger.error(f"✗ Transaction {transaction_id}: ai_audit_note is NULL after commit!")

            return updated_count

        except Exception as e:
            logger.error(f"Error updating transaction statuses: {str(e)}")
            db.rollback()
            raise

    def _get_audit_rules_map(self, audit_rules: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
        """Get a map of audit rules by their database ID for quick lookup"""
        try:
            rules_map = {}

            for rule in audit_rules:
                rule_id = rule.get('rule_id')
                if rule_id:
                    rules_map[rule_id] = rule

            logger.info(f"Created audit rules map with {len(rules_map)} rules")
            return rules_map
        except Exception as e:
            logger.error(f"Error creating audit rules map: {str(e)}")
            return {}

    def _create_default_audit_result(self, transaction_id: int, error: str = None) -> Dict[str, Any]:
        """Create a default audit result for error cases - marks as failed to skip status update"""
        return {
            'transaction_id': transaction_id,
            'audit_status': 'failed',  # Mark as failed - transaction will stay pending
            'triggered_rules': [],
            'reject_messages': [],
            'error': error,
            'audited_at': datetime.now(timezone.utc).isoformat(),
            'total_rules_evaluated': 0,
            'rules_triggered': 0,
            'skip_status_update': True,  # Flag to skip updating transaction status
            'token_usage': {
                'input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': 0,
                'reasoning_tokens': 0,
                'cached_tokens': 0
            }
        }

    def add_transaction_to_ai_audit_queue(
        self,
        db: Session,
        organization_id: int,
        user_id: Optional[int] = None,
        transaction_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Add transactions to AI audit queue by changing ai_audit_status from 'null' to 'queued'

        Args:
            db: Database session
            organization_id: Organization ID to filter transactions
            user_id: User ID who triggered the queueing
            transaction_ids: Optional list of specific transaction IDs to queue

        Returns:
            Dict containing queued count and audit history ID
        """
        try:
            logger.info(f"Adding transactions to AI audit queue for organization {organization_id}")

            # First, get the transaction IDs that will be queued (for audit history)
            id_query = db.query(Transaction.id).filter(
                Transaction.organization_id == organization_id,
                Transaction.ai_audit_status == AIAuditStatus.null,
                Transaction.deleted_date.is_(None)
            )

            # Apply transaction IDs filter if provided
            if transaction_ids:
                id_query = id_query.filter(Transaction.id.in_(transaction_ids))

            queued_transaction_ids = [txn_id for (txn_id,) in id_query.all()]

            # Build update query for transactions with 'null' ai_audit_status
            update_query = db.query(Transaction).filter(
                Transaction.organization_id == organization_id,
                Transaction.ai_audit_status == AIAuditStatus.null,
                Transaction.deleted_date.is_(None)
            )

            # Apply transaction IDs filter if provided
            if transaction_ids:
                update_query = update_query.filter(Transaction.id.in_(transaction_ids))

            # Use bulk update SQL query for better performance
            queued_count = update_query.update(
                {Transaction.ai_audit_status: AIAuditStatus.queued},
                synchronize_session=False
            )

            # Create audit history record with 'in_progress' status
            # This will be picked up and processed by cron job later
            audit_history = TransactionAuditHistory(
                organization_id=organization_id,
                triggered_by_user_id=user_id,
                transactions=queued_transaction_ids,
                audit_info={
                    'status': 'queued',
                    'message': 'Audit batch queued for processing'
                },
                total_transactions=queued_count,
                processed_transactions=0,
                approved_count=0,
                rejected_count=0,
                status='in_progress',
                started_at=datetime.now(timezone.utc),
                completed_at=None
            )

            db.add(audit_history)
            db.commit()

            logger.info(f"Queued {queued_count} transactions for AI audit with audit history ID {audit_history.id}")

            return {
                'success': True,
                'message': f'Successfully queued {queued_count} transactions for AI audit',
                'queued_count': queued_count,
                'organization_id': organization_id,
                'audit_history_id': audit_history.id,
                'transaction_ids': queued_transaction_ids if transaction_ids else None
            }

        except SQLAlchemyError as e:
            logger.error(f"Database error queueing transactions for AI audit: {str(e)}")
            db.rollback()
            return {
                'success': False,
                'error': f'Database error: {str(e)}',
                'queued_count': 0
            }
        except Exception as e:
            logger.error(f"Unexpected error queueing transactions for AI audit: {str(e)}")
            db.rollback()
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'queued_count': 0
            }

    def _save_audit_history_batch(
        self,
        db: Session,
        organization_id: int,
        transaction_ids: List[int],
        audit_results: List[Dict[str, Any]],
        total_transactions: int,
        processed_transactions: int,
        updated_transactions: int
    ) -> None:
        """Save audit history batch with compact transaction-level results"""
        try:
            # Calculate statistics
            approved_count = sum(1 for result in audit_results if result.get('audit_status') == 'approved')
            rejected_count = sum(1 for result in audit_results if result.get('audit_status') == 'rejected')

            # Calculate total token usage and prepare compact results
            total_input_tokens = 0
            total_output_tokens = 0
            total_tokens = 0

            # Create compact audit results grouped by transaction
            compact_results = {}

            for result in audit_results:
                transaction_id = result.get('transaction_id')
                token_usage = result.get('token_usage', {})

                # Sum up tokens including reasoning tokens
                input_tokens = token_usage.get('input_tokens', 0)
                output_tokens = token_usage.get('output_tokens', 0)
                trans_tokens = token_usage.get('total_tokens', 0)
                reasoning_tokens = token_usage.get('reasoning_tokens', 0)
                cached_tokens = token_usage.get('cached_tokens', 0)

                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                total_tokens += trans_tokens

                # Store ultra-compact result per transaction
                compact_results[transaction_id] = {
                    's': result.get('audit_status'),  # status
                    'v': [  # violations (rule_db_id, message, and transaction_record_id)
                        {
                            'id': tr.get('rule_db_id'),
                            'm': tr.get('message'),
                            'tr': tr.get('transaction_record_id')  # transaction_record_id
                        }
                        for tr in result.get('triggered_rules', []) if tr.get('has_reject')
                    ],
                    't': {  # tokens
                        'i': input_tokens,
                        'o': output_tokens,
                        'tot': trans_tokens,
                        'r': reasoning_tokens,  # reasoning tokens
                        'c': cached_tokens  # cached tokens
                    }
                }

            logger.info(f"Audit batch token usage - Input: {total_input_tokens}, Output: {total_output_tokens}, Total: {total_tokens}")

            # Create audit history record with compact data
            audit_history = TransactionAuditHistory(
                organization_id=organization_id,
                transactions=transaction_ids,
                audit_info={
                    'transaction_results': compact_results,
                    'summary': {
                        'total_transactions': total_transactions,
                        'processed_transactions': processed_transactions,
                        'approved_count': approved_count,
                        'rejected_count': rejected_count,
                        'token_usage': {
                            'total_input_tokens': total_input_tokens,
                            'total_output_tokens': total_output_tokens,
                            'total_tokens': total_tokens
                        }
                    }
                },
                total_transactions=total_transactions,
                processed_transactions=processed_transactions,
                approved_count=approved_count,
                rejected_count=rejected_count,
                status='completed',
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc)
            )

            db.add(audit_history)
            db.commit()

            logger.info(f"Saved audit history batch {audit_history.id} for organization {organization_id}")

        except Exception as e:
            logger.error(f"Error saving audit history batch: {str(e)}")
            db.rollback()
            raise