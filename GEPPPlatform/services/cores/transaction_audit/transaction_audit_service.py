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
                 project_id: str = None, location: str = None):
        """
        Initialize the TransactionAuditService

        Args:
            gemini_api_key: Google Gemini API key (deprecated, kept for backward compatibility)
            response_language: Language for AI responses (default: 'thai')
            project_id: Google Cloud Project ID for Vertex AI
            location: Google Cloud region/location (e.g., 'us-central1', 'asia-southeast1')
        """
        # Setup credentials from environment variable
        self.temp_credentials_file = setup_credentials_from_env()

        # Get configuration from environment or parameters
        self.project_id = os.environ.get('VERTEX_AI_PROJECT_ID')
        self.location = 'us-central1'

        # Initialize Vertex AI client
        if self.project_id and GENAI_AVAILABLE:
            try:
                self.client = genai.Client(
                    vertexai=True,  # Force use of Vertex AI
                    project=self.project_id,
                    location=self.location
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

        self.model_name = self.prompts.get('api_settings', {}).get('model_name', 'gemini-2.5-flash')
        self.max_concurrent_threads = 50
        self.response_language = response_language.lower()  # Store language preference

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
                "model_name": "gemini-2.5-flash",
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

            # print(";;;=====")
            # Process transactions with AI in multiple threads
            audit_results = self._process_transactions_with_ai(
                transaction_audit_data,
                audit_rules
            )

            # print("---====-=-=", audit_results)

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

    def _process_transactions_with_ai(self, transactions_data: List[Dict[str, Any]], audit_rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process transactions with Gemini API using multi-threading"""
        try:
            audit_results = []

            print("ID:", [t["transaction_id"] for t in transactions_data])
            # Process transactions in batches using thread pool
            with ThreadPoolExecutor(max_workers=self.max_concurrent_threads) as executor:
                # Submit all transactions for processing
                future_to_transaction = {
                    executor.submit(self._audit_single_transaction, transaction_data, audit_rules): transaction_data
                    for transaction_data in transactions_data
                }

                # Collect results as they complete
                for future in as_completed(future_to_transaction):
                    transaction_data = future_to_transaction[future]
                    try:
                        audit_result = future.result()
                        audit_results.append(audit_result)
                        logger.info(f"Completed audit for transaction {transaction_data['transaction_id']}")
                    except Exception as e:
                        logger.error(f"Error auditing transaction {transaction_data['transaction_id']}: {str(e)}")
                        # Add failed audit result
                        audit_results.append({
                            'transaction_id': transaction_data['transaction_id'],
                            'audit_status': 'failed',
                            'error': str(e),
                            'violations': [],
                            'recommendations': ['Manual review required due to AI audit failure'],
                            'token_usage': {
                                'input_tokens': 0,
                                'output_tokens': 0,
                                'total_tokens': 0,
                                'reasoning_tokens': 0,
                                'cached_tokens': 0
                            }
                        })

            logger.info(f"Completed AI audit for {len(audit_results)} transactions")
            return audit_results

        except Exception as e:
            logger.error(f"Error in multi-threaded AI processing: {str(e)}")
            raise

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

    def _generate_presigned_urls_for_images(self, image_urls: List[str], organization_id: int, user_id: int) -> List[str]:
        """Generate presigned URLs for images to allow Gemini API access"""
        try:
            if not self.presigned_url_service:
                logger.warning("Presigned URL service not available")
                return []

            # Use the existing presigned URL service to generate view URLs
            result = self.presigned_url_service.get_transaction_file_view_presigned_urls(
                file_urls=image_urls,
                organization_id=organization_id,
                user_id=user_id,
                expiration_seconds=7200  # 2 hours expiration for audit processing
            )

            if result.get('success'):
                presigned_urls = []
                for url_data in result.get('presigned_urls', []):
                    presigned_url = url_data.get('view_url')
                    if presigned_url:
                        presigned_urls.append(presigned_url)
                        logger.info(f"Generated presigned URL for {url_data.get('original_url')}")

                logger.info(f"Successfully generated {len(presigned_urls)} presigned URLs")
                return presigned_urls
            else:
                logger.error(f"Failed to generate presigned URLs: {result.get('message')}")
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
                        "thinkingBudget": api_settings.get('thinking_budget', 512)
                    }
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
                    }
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
            ai_data = json.loads(cleaned_response)

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

                    # Save ultra-compact audit response (only essential data)
                    compact_audit = {
                        's': audit_status,  # status
                        'v': [  # violations (rule_db_id, message, and transaction_record_id)
                            {
                                'id': tr.get('rule_db_id'),
                                'm': tr.get('message'),
                                'tr': tr.get('transaction_record_id')  # transaction_record_id
                            }
                            for tr in triggered_rules if tr.get('has_reject')
                        ],
                        't': result.get('token_usage', {}),  # token_usage
                        'at': result.get('audited_at')  # audited_at
                    }

                    transaction.ai_audit_note = json.dumps(compact_audit, ensure_ascii=False)

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
        """Create a default audit result for error cases"""
        return {
            'transaction_id': transaction_id,
            'audit_status': 'approved',  # Default to approved on error to avoid blocking
            'triggered_rules': [],
            'reject_messages': [],
            'error': error,
            'audited_at': datetime.now(timezone.utc).isoformat(),
            'total_rules_evaluated': 0,
            'rules_triggered': 0,
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