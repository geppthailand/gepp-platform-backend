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


from ....models.transactions.transactions import Transaction, TransactionStatus
from ....models.transactions.transaction_records import TransactionRecord
from ....models.audit_rules import AuditRule
from ....models.cores.references import MainMaterial
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

            # Get global audit rules
            audit_rules = self._get_audit_rules(db)
            if not audit_rules:
                return {
                    'success': False,
                    'error': 'No audit rules found. Please configure audit rules first.',
                    'total_transactions': len(pending_transactions)
                }
            # print("---====-=-=", audit_rules)

            # Prepare transaction data with records and images
            transaction_audit_data = self._prepare_transaction_data(db, pending_transactions)

            # Process transactions with AI in multiple threads
            audit_results = self._process_transactions_with_ai(
                transaction_audit_data,
                audit_rules
            )

            print("---====-=-=", audit_results)

            # Update transaction statuses based on audit results
            updated_count = self._update_transaction_statuses(db, audit_results)

            logger.info(f"AI audit completed. Processed {len(audit_results)} transactions, updated {updated_count}")

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
                debug_query = debug_query.filter(Transaction.organization_id == organization_id)

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

    def _get_audit_rules(self, db: Session) -> List[Dict[str, Any]]:
        """Get global audit rules for AI processing"""
        try:
            audit_rules = db.query(AuditRule).filter(
                AuditRule.is_global == True,
                AuditRule.organization_id.is_(None),
                AuditRule.is_active == True
            ).all()

            rules_data = []
            for rule in audit_rules:
                rules_data.append({
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
                            'compliance_score': 0,
                            'violations': [],
                            'recommendations': ['Manual review required due to AI audit failure']
                        })

            logger.info(f"Completed AI audit for {len(audit_results)} transactions")
            return audit_results

        except Exception as e:
            logger.error(f"Error in multi-threaded AI processing: {str(e)}")
            raise

    def _audit_single_transaction(self, transaction_data: Dict[str, Any], audit_rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Audit a single transaction using ChatGPT API with image analysis"""
        try:
            # Prepare prompt for ChatGPT
            prompt = self._create_audit_prompt(transaction_data, audit_rules)

            # Collect all images from transaction and records
            all_images = []

            # Add transaction-level images
            transaction_images = transaction_data.get('images', [])
            if transaction_images:
                all_images.extend(transaction_images)
                logger.info(f"Added {len(transaction_images)} transaction images for audit")

            # Add images from all transaction records
            records = transaction_data.get('records', [])
            for record in records:
                record_images = record.get('images', [])
                if record_images:
                    all_images.extend(record_images)
                    logger.info(f"Added {len(record_images)} record images from record {record.get('record_id')}")

            # Remove duplicates and filter valid URLs
            unique_images = list(set([img for img in all_images if img and isinstance(img, str) and img.strip()]))

            if unique_images:
                logger.info(f"Processing transaction {transaction_data['transaction_id']} with {len(unique_images)} images for OCR/analysis")

                # Generate presigned URLs for the images
                presigned_images = self._generate_presigned_urls_for_images(
                    unique_images,
                    transaction_data.get('organization_id', 1),
                    transaction_data.get('user_id', 1)
                )

                if presigned_images:
                    logger.info(f"Generated {len(presigned_images)} presigned URLs for ChatGPT access")
                    # Enhance prompt for image analysis
                    enhanced_prompt = self._enhance_prompt_for_images(prompt, presigned_images, transaction_data)
                    response = self._call_chatgpt_api(enhanced_prompt, presigned_images)
                else:
                    logger.warning(f"Failed to generate presigned URLs, falling back to text-only analysis")
                    response = self._call_chatgpt_api(prompt)
            else:
                logger.info(f"Processing transaction {transaction_data['transaction_id']} with text-only analysis")
                response = self._call_chatgpt_api(prompt)

            # Parse AI response
            audit_result = self._parse_ai_response(response, transaction_data['transaction_id'], audit_rules)

            # Add image analysis metadata
            audit_result['images_analyzed'] = len(unique_images)
            audit_result['has_image_analysis'] = len(unique_images) > 0

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
        """Create a comprehensive prompt for ChatGPT audit with rule-by-rule evaluation"""

        # Format audit rules for better prompt understanding
        rules_summary = []
        for rule in audit_rules:
            rule_summary = f"""
Rule ID: {rule.get('rule_id', 'N/A')}
DB ID: {rule.get('id', 'N/A')}
Name: {rule.get('rule_name', 'N/A')}
Type: {rule.get('rule_type', 'N/A')}
Condition: {rule.get('condition', 'N/A')}
Thresholds: {rule.get('thresholds', 'N/A')}
Metrics: {rule.get('metrics', 'N/A')}
Actions: {json.dumps(rule.get('actions', []), ensure_ascii=False)}
"""
            rules_summary.append(rule_summary)

        prompt = f"""
You are an expert AI auditor for waste management transactions. Evaluate the following transaction against EACH provided audit rule individually.

TRANSACTION DATA:
{json.dumps(transaction_data, indent=2, ensure_ascii=False)}

AUDIT RULES TO EVALUATE:
{chr(10).join(rules_summary)}

CRITICAL INSTRUCTIONS:
1. Evaluate the transaction against EVERY audit rule provided
2. For each rule, determine if it is triggered (true/false) based on the rule conditions and transaction data
3. If a rule is triggered, provide a brief, specific message explaining why
4. If a rule is not triggered, set trigger to false and provide a brief confirmation message

YOU MUST respond with a valid JSON object in this EXACT format:
{{
    "transaction_id": {transaction_data.get('transaction_id', 0)},
    "audits": [
        {{
            "rule_id": "<rule_id from rule>",
            "id": <database_id_of_rule>,
            "trigger": true or false,
            "message": "<brief specific message about this rule evaluation>"
        }}
    ]
}}

IMPORTANT REQUIREMENTS:
- Include ALL rules in the audits array, even if not triggered
- Keep messages brief (max 50 words)
- Use exact rule_id and id values from the provided rules
- Respond with ONLY valid JSON, no additional text
- Focus on factual evaluation based on rule conditions and transaction data
"""
        return prompt

    def _enhance_prompt_for_images(self, base_prompt: str, images: List[str], transaction_data: Dict[str, Any]) -> str:
        """Enhance the audit prompt to include image analysis instructions"""

        image_analysis_instructions = f"""

ADDITIONAL IMAGE ANALYSIS INSTRUCTIONS:
You have been provided with {len(images)} presigned image URLs related to this transaction. These images may include:
- Waste material photos showing actual materials, quantities, and conditions
- Receipts, invoices, or transaction documents
- Weight scale readings or measurement documentation
- Quality certification documents
- Processing or transport documentation

When analyzing these images:
1. **OCR Analysis**: Extract any text, numbers, weights, quantities, dates, or prices from the images
2. **Visual Verification**: Compare visual evidence with the reported transaction data
3. **Discrepancy Detection**: Look for inconsistencies between images and reported data
4. **Document Verification**: Verify authenticity and completeness of any documents shown
5. **Material Assessment**: Evaluate actual material condition, contamination level, and type consistency

Pay special attention to:
- Weight/quantity discrepancies between images and reported data
- Material type mismatches (e.g., reported plastic but image shows metal)
- Date inconsistencies between documents and transaction dates
- Quality condition differences (reported "good" but image shows contaminated material)
- Price variations between receipts/invoices and reported amounts
- Missing required documentation or certifications

For each audit rule evaluation, consider both the transaction data AND the visual evidence from images.
If images contradict the reported data, prioritize the visual evidence and flag appropriate violations.

RECORDS DATA FOR IMAGE CROSS-REFERENCE:
"""

        # Add detailed record information for image cross-reference
        records = transaction_data.get('records', [])
        for i, record in enumerate(records):
            record_info = f"""
Record #{i+1} (ID: {record.get('record_id')}):
- Material: {record.get('material_type')} ({record.get('material_name_th')})
- Quantity: {record.get('quantity')} {record.get('unit')}
- Weight: {record.get('weight_kg')} kg
- Unit Price: {record.get('unit_price')} per {record.get('unit')}
- Total Value: {record.get('total_value')}
- Condition: {record.get('material_condition', 'Not specified')}
- Quality Score: {record.get('quality_score', 'Not specified')}
- Contamination Level: {record.get('contamination_level', 'Not specified')}
- Images Count: {len(record.get('images', []))}
"""
            image_analysis_instructions += record_info

        enhanced_prompt = base_prompt + image_analysis_instructions
        return enhanced_prompt

    def _call_chatgpt_api(self, prompt: str, images: List[str] = None) -> str:
        """Call ChatGPT API for audit analysis with optional image processing"""
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
                return response.choices[0].message.content
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
                return result.output_text

        except Exception as e:
            logger.error(f"ChatGPT API call failed: {str(e)}")
            raise

    def _parse_ai_response(self, ai_response: str, transaction_id: int, audit_rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse AI response and process rule actions with priority logic"""
        try:
            # Try to parse JSON response
            ai_data = json.loads(ai_response.strip())

            audits = ai_data.get('audits', [])
            if not audits:
                logger.warning(f"No audit results found in AI response for transaction {transaction_id}")
                return self._create_default_audit_result(transaction_id)

            # Process each rule audit and apply actions
            processed_audits = []
            reject_messages = []
            approve_messages = []
            warn_messages = []

            # Get audit rules for action lookup
            audit_rules_map = self._get_audit_rules_map(audit_rules)

            final_status = 'pending'  # Default to approved unless rejected
            has_rejections = False

            for audit in audits:
                rule_id = audit.get('rule_id')
                rule_db_id = audit.get('id')
                triggered = audit.get('trigger', False)
                message = audit.get('message', '')

                # Find the rule in our rules map to get actions
                rule_actions = audit_rules_map.get(rule_id, {}).get('actions', [])

                processed_audit = {
                    'rule_id': rule_id,
                    'rule_db_id': rule_db_id,
                    'triggered': triggered,
                    'message': message,
                    'actions_applied': []
                }

                # Process actions if rule is triggered
                if triggered and rule_actions:
                    for action in rule_actions:
                        if action.get('type') == 'system_action':
                            action_type = action.get('action', '').lower()
                            action_message = action.get('message', message)

                            processed_audit['actions_applied'].append({
                                'type': action_type,
                                'message': action_message
                            })

                            # Apply priority logic: reject > approve > warn
                            if action_type == 'reject':
                                final_status = 'rejected'
                                has_rejections = True
                                reject_messages.append(f"[{rule_id}] {action_message}")
                            elif action_type == 'approve' and not has_rejections:
                                # Only set to approved if no rejections found
                                final_status = 'approved'
                                approve_messages.append(f"[{rule_id}] {action_message}")
                            elif action_type == 'warn':
                                warn_messages.append(f"[{rule_id}] {action_message}")

                processed_audits.append(processed_audit)

            # Calculate compliance score based on triggered rules
            triggered_count = sum(1 for audit in processed_audits if audit['triggered'])
            total_rules = len(processed_audits)
            compliance_score = max(0, 100 - (triggered_count * 20)) if total_rules > 0 else 100

            # Final verification: if any reject messages exist, force status to rejected
            if reject_messages:
                final_status = 'rejected'

            # Create summary based on final status
            if final_status == 'rejected':
                summary = f"Transaction rejected. Issues: {len(reject_messages)}"
                all_messages = reject_messages + warn_messages
            else:
                if final_status == 'pending': 
                    summary = f"Transaction warning. {triggered_count} rules triggered."
                    all_messages = warn_messages
                else:
                    summary = f"Transaction approved. {triggered_count} rules triggered."
                    all_messages = approve_messages + warn_messages

            # Structure the final audit result
            audit_result = {
                'transaction_id': transaction_id,
                'audit_status': final_status,
                'compliance_score': compliance_score,
                'rule_results': processed_audits,
                'reject_messages': reject_messages,
                'approve_messages': approve_messages,
                'warn_messages': warn_messages,
                'all_messages': all_messages,
                'summary': summary,
                'audited_at': datetime.now(timezone.utc).isoformat(),
                'total_rules_evaluated': total_rules,
                'rules_triggered': triggered_count
            }

            return audit_result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response for transaction {transaction_id}: {str(e)}")
            return self._create_default_audit_result(transaction_id, error=f'JSON parsing error: {str(e)}')
        except Exception as e:
            logger.error(f"Unexpected error processing AI response for transaction {transaction_id}: {str(e)}")
            return self._create_default_audit_result(transaction_id, error=f'Processing error: {str(e)}')

    def _update_transaction_statuses(self, db: Session, audit_results: List[Dict[str, Any]]) -> int:
        """Update transaction statuses based on audit results"""
        try:
            updated_count = 0

            for result in audit_results:
                transaction_id = result['transaction_id']
                audit_status = result['audit_status']

                transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
                if transaction:
                    # Update status based on audit result
                    if audit_status == 'approved':
                        transaction.status = TransactionStatus.approved
                    elif audit_status == 'rejected':
                        transaction.status = TransactionStatus.rejected
                    else:  # requires_review
                        transaction.status = TransactionStatus.pending

                    # Clear existing notes and replace with audit messages
                    audit_header = f"AI Audit - Score: {result['compliance_score']}/100. {result.get('summary', '')}"
                    all_messages = result.get('all_messages', [])

                    if all_messages:
                        # Create formatted audit notes with all messages
                        formatted_messages = "\n".join([f"• {msg}" for msg in all_messages])
                        transaction.notes = f"{audit_header}\n\nAudit Details:\n{formatted_messages}"
                    else:
                        transaction.notes = audit_header

                    updated_count += 1

            db.commit()
            logger.info(f"Updated {updated_count} transaction statuses based on audit results")
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
            'audit_status': 'requires_review',
            'compliance_score': 0,
            'rule_results': [],
            'reject_messages': [],
            'approve_messages': [],
            'warn_messages': ['Manual review required - AI audit failed'],
            'all_messages': ['Manual review required - AI audit failed'],
            'summary': 'AI audit failed - manual review required',
            'error': error,
            'audited_at': datetime.now(timezone.utc).isoformat(),
            'total_rules_evaluated': 0,
            'rules_triggered': 0
        }