"""
Transaction Audit Service - AI-powered transaction auditing
Handles synchronous AI audit processing with multi-threading support
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None


from ....models.transactions.transactions import Transaction, TransactionStatus, AIAuditStatus
from ....models.transactions.transaction_records import TransactionRecord
from ....models.audit_rules import AuditRule
from ....models.cores.references import MainMaterial
from ....models.subscriptions.organizations import Organization
from ....models.logs.transaction_audit_history import TransactionAuditHistory
from ..transactions.presigned_url_service import TransactionPresignedUrlService

logger = logging.getLogger(__name__)

class TransactionAuditService:
    """
    Service for AI-powered transaction auditing using ChatGPT API
    Supports multi-threaded processing for efficient bulk analysis
    """

    def __init__(self, openai_api_key: str = None):
        """
        Initialize the TransactionAuditService

        Args:
            openai_api_key: OpenAI API key for ChatGPT integration
        """
        self.openai_api_key = openai_api_key or "your-openai-api-key"
        self.openai_api_url = "https://api.openai.com/v1/chat/completions"
        self.max_concurrent_threads = 50

        # Initialize presigned URL service for image access
        try:
            self.presigned_url_service = TransactionPresignedUrlService()
            logger.info("Presigned URL service initialized for image access")
        except Exception as e:
            logger.warning(f"Failed to initialize presigned URL service: {str(e)}")
            self.presigned_url_service = None

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

            print(";;;=====")
            # Process transactions with AI in multiple threads
            audit_results = self._process_transactions_with_ai(
                transaction_audit_data,
                audit_rules
            )

            print("---====-=-=", audit_results)

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

                # Prepare transaction data
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
                    'images': transaction.images or [],
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
        """Process transactions with ChatGPT API using multi-threading"""
        try:
            audit_results = []

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
                                'total_tokens': 0
                            }
                        })

            logger.info(f"Completed AI audit for {len(audit_results)} transactions")
            return audit_results

        except Exception as e:
            logger.error(f"Error in multi-threaded AI processing: {str(e)}")
            raise

    def _audit_single_transaction(self, transaction_data: Dict[str, Any], audit_rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Audit a single transaction using ChatGPT API with structured record-image grouping"""
        try:
            # Prepare base prompt for ChatGPT
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
                api_response = self._call_chatgpt_api_structured(content_parts)
            else:
                logger.info(f"Processing transaction {transaction_data['transaction_id']} with text-only analysis")
                api_response = self._call_chatgpt_api(prompt)

            # Extract content and usage from API response
            response_content = api_response.get('content', '')
            token_usage = api_response.get('usage', {})

            print(response_content)
            # Parse AI response
            audit_result = self._parse_ai_response(response_content, transaction_data['transaction_id'], audit_rules)

            # Add token usage information
            audit_result['token_usage'] = {
                'input_tokens': token_usage.get('input_tokens', 0),
                'output_tokens': token_usage.get('output_tokens', 0),
                'total_tokens': token_usage.get('total_tokens', 0)
            }

            logger.info(f"Transaction {transaction_data['transaction_id']} used {token_usage.get('total_tokens', 0)} tokens "
                       f"(input: {token_usage.get('input_tokens', 0)}, output: {token_usage.get('output_tokens', 0)})")

            return audit_result

        except Exception as e:
            logger.error(f"Error auditing transaction {transaction_data['transaction_id']}: {str(e)}")
            raise

    def _generate_presigned_urls_for_images(self, image_urls: List[str], organization_id: int, user_id: int) -> List[str]:
        """Generate presigned URLs for images to allow ChatGPT access"""
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

    def _create_audit_prompt(self, transaction_data: Dict[str, Any], audit_rules: List[Dict[str, Any]]) -> str:
        """Create an optimized prompt with ID-based rule references"""

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

        prompt = f"""
Audit waste transaction against rules. Evaluate each rule and return triggered violations only.

RULES (ref by id):
{json.dumps(rules_compact, ensure_ascii=False)}

TRANSACTION:
{json.dumps(transaction_data, ensure_ascii=False)}

CRITICAL: Images for each transaction_record apply ONLY to that specific record. Do NOT process images across different records unless explicitly instructed by rules.

Respond ONLY rejected items in this JSON format:
{{
    "tr_id": {transaction_data.get('transaction_id', 0)},
    "violations": [
        {{
            "id": <rule_db_id>,
            "msg": "<short specific rejection reason (max 30 words)>"
        }}
    ]
}}

If NO violations: {{"tr_id": {transaction_data.get('transaction_id', 0)}, "violations": []}}
Only include triggered rules. Keep messages concise.
"""
        return prompt

    def _enhance_prompt_for_images(self, base_prompt: str, images: List[str], transaction_data: Dict[str, Any]) -> str:
        """Enhance the audit prompt with compact image analysis instructions"""

        image_instructions = """

IMAGE ANALYSIS:
- Extract text/numbers from documents (OCR)
- Verify weights, quantities, dates, prices match reported data
- Check material type consistency with images
- Identify discrepancies or missing docs
- CRITICAL: Each record's images apply ONLY to that record

If images contradict data, flag violation with specific reason.
"""

        enhanced_prompt = base_prompt + image_instructions
        return enhanced_prompt

    def _call_chatgpt_api_structured(self, content_parts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Call ChatGPT API with structured content parts (text + images)

        Returns:
            Dict containing 'content' (response text) and 'usage' (token information)
        """
        try:
            if not OPENAI_AVAILABLE:
                raise ImportError("OpenAI package not installed. Install with: pip install openai")

            client = OpenAI(api_key=self.openai_api_key)

            # Prepare messages for vision API
            messages = [
                # {"role": "developer", "content": "# Juice: 0 !important"},
                {
                    "role": "system",
                    "content": "You are a waste management auditor. Analyze transactions and flag only violations. Be concise."
                },
                {
                    "role": "user",
                    "content": content_parts
                }
            ]

            # Use chat completions for image analysis (vision API)
            response = client.chat.completions.create(
                model="gpt-5-nano",  # Use vision model for image analysis
                messages=messages,
                # reasoning_effort="minimal"
            )

            print(response)

            # Extract token usage information
            usage_info = {
                'input_tokens': response.usage.prompt_tokens if hasattr(response, 'usage') and response.usage else 0,
                'output_tokens': response.usage.completion_tokens if hasattr(response, 'usage') and response.usage else 0,
                'total_tokens': response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
            }

            return {
                'content': response.choices[0].message.content,
                'usage': usage_info
            }

        except Exception as e:
            logger.error(f"ChatGPT API call failed: {str(e)}")
            raise

    def _call_chatgpt_api(self, prompt: str, images: List[str] = None) -> Dict[str, Any]:
        """
        Call ChatGPT API for audit analysis with optional image processing

        Returns:
            Dict containing 'content' (response text) and 'usage' (token information)
        """
        try:
            if not OPENAI_AVAILABLE:
                raise ImportError("OpenAI package not installed. Install with: pip install openai")

            client = OpenAI(api_key=self.openai_api_key)

            # Prepare messages for vision API
            messages = [
                {
                    "role": "system",
                    "content": "You are a professional waste management auditor with expertise in compliance and quality control. You can analyze documents, receipts, and waste material images to verify transaction details."
                }
            ]

            # Create user message with text
            user_message = {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"{prompt}\n\nRespond only with valid JSON format as specified above."
                    }
                ]
            }

            # Add images if provided
            if images and len(images) > 0:
                for image_url in images[:10]:  # Limit to 10 images per API call
                    if image_url and image_url.strip():
                        try:
                            # Add image to the message
                            user_message["content"].append({
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url,
                                    "detail": "high"  # Use high detail for better OCR
                                }
                            })
                            logger.info(f"Added image to audit analysis: {image_url}")
                        except Exception as img_error:
                            logger.warning(f"Failed to add image {image_url}: {str(img_error)}")

            messages.append(user_message)

            # Use chat completions for image analysis (vision API)
            if images and len(images) > 0:
                response = client.chat.completions.create(
                    model="gpt-5-nano",  # Use vision model for image analysis
                    messages=messages,
                    # max_tokens=4000,
                    # temperature=0.1  # Low temperature for consistent auditing
                )

                # Extract token usage information
                usage_info = {
                    'input_tokens': response.usage.prompt_tokens if hasattr(response, 'usage') and response.usage else 0,
                    'output_tokens': response.usage.completion_tokens if hasattr(response, 'usage') and response.usage else 0,
                    'total_tokens': response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
                }

                return {
                    'content': response.choices[0].message.content,
                    'usage': usage_info
                }
            else:
                # Use responses API for text-only analysis
                full_input = f"""You are a professional waste management auditor with expertise in compliance and quality control.

{prompt}

Respond only with valid JSON format as specified above."""

                result = client.responses.create(
                    model="gpt-5-nano",
                    input=full_input,
                    reasoning={"effort": "low"},
                    text={"verbosity": "low"}
                )

                # Extract token usage information from responses API
                usage_info = {
                    'input_tokens': result.usage.input_tokens if hasattr(result, 'usage') and result.usage else 0,
                    'output_tokens': result.usage.output_tokens if hasattr(result, 'usage') and result.usage else 0,
                    'total_tokens': (result.usage.input_tokens + result.usage.output_tokens) if hasattr(result, 'usage') and result.usage else 0
                }

                return {
                    'content': result.output_text,
                    'usage': usage_info
                }

        except Exception as e:
            logger.error(f"ChatGPT API call failed: {str(e)}")
            raise

    def _parse_ai_response(self, ai_response: str, transaction_id: int, audit_rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse optimized AI response with ID-based violations"""
        try:
            # Try to parse JSON response
            ai_data = json.loads(ai_response.strip())

            violations = ai_data.get('violations', [])

            # Build audit rules map by database ID for lookup
            audit_rules_map_by_id = {rule.get('id'): rule for rule in audit_rules}

            # Process violations
            reject_messages = []
            triggered_rules = []

            for violation in violations:
                rule_db_id = violation.get('id')
                msg = violation.get('msg', '')

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
                    'has_reject': has_reject
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
                        'v': [  # violations (only rule_db_id and message)
                            {
                                'id': tr.get('rule_db_id'),
                                'm': tr.get('message')
                            }
                            for tr in triggered_rules if tr.get('has_reject')
                        ],
                        't': result.get('token_usage', {}),  # token_usage
                        'at': result.get('audited_at')  # audited_at
                    }

                    transaction.ai_audit_note = json.dumps(compact_audit, ensure_ascii=False)

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
                'total_tokens': 0
            }
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

                # Sum up tokens
                input_tokens = token_usage.get('input_tokens', 0)
                output_tokens = token_usage.get('output_tokens', 0)
                trans_tokens = token_usage.get('total_tokens', 0)

                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                total_tokens += trans_tokens

                # Store ultra-compact result per transaction
                compact_results[transaction_id] = {
                    's': result.get('audit_status'),  # status
                    'v': [  # violations (only rule_db_id and message)
                        {
                            'id': tr.get('rule_db_id'),
                            'm': tr.get('message')
                        }
                        for tr in result.get('triggered_rules', []) if tr.get('has_reject')
                    ],
                    't': {  # tokens
                        'i': input_tokens,
                        'o': output_tokens,
                        'tot': trans_tokens
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