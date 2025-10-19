from datetime import datetime, timedelta
from time import time
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from dateutil.parser import parse
import threading
import boto3
import zipfile

# import pandas as pd
import numpy as np
import zlib
import base64

import json
import os
from glob import glob
import math
import gzip
import pickle
import re
from boto3.dynamodb.conditions import Key, Attr
import bcrypt


from pgvector.psycopg2 import register_vector
import psycopg2 as pg
import jwt

from GEPPPlatform.services.auth import handle_auth_routes
from GEPPPlatform.services.auth.auth_handlers import AuthHandlers
from GEPPPlatform.libs import authGuard
from GEPPPlatform.exceptions import APIException
from GEPPPlatform.database import get_session

import random
import string

def cron_process_audits(event, context):
    """
    Cron job to process queued AI audits every 30 seconds

    Process flow:
    1. Loop while elapsed time < 20 seconds
    2. Get up to 50 transactions with ai_audit_status = 'queued' (sorted by transaction.id)
    3. Group transactions by organization
    4. Get audit rules for each organization
    5. Process transactions with AI using organization-specific rules
    6. Update ai_audit_status (not transaction.status)
    7. Check elapsed time and continue if < 20 seconds
    """
    import logging
    import time
    from collections import defaultdict
    from GEPPPlatform.models.transactions.transactions import Transaction, AIAuditStatus
    from GEPPPlatform.services.cores.transaction_audit.transaction_audit_service import TransactionAuditService

    logger = logging.getLogger(__name__)
    logger.info("Starting cron_process_audits")

    # Record start time
    start_time = time.time()
    TIME_LIMIT_SECONDS = 50

    # Get Gemini API key from environment
    gemini_api_key = os.getenv('GEMINI_API_KEY')
    if not gemini_api_key:
        logger.error("Gemini API key not configured")
        return {
            'success': False,
            'error': 'Gemini API key not configured'
        }

    # Initialize audit service
    audit_service = TransactionAuditService(gemini_api_key)

    # Track overall statistics
    overall_total_processed = 0
    overall_total_updated = 0
    overall_organizations_count = 0
    batch_count = 0

    try:
        # Get database session using context manager
        with get_session() as db:
            # Check if there are any queued transactions before starting
            initial_count = db.query(Transaction).filter(
                Transaction.ai_audit_status == AIAuditStatus.queued,
                Transaction.deleted_date.is_(None)
            ).count()

            if initial_count == 0:
                logger.info("No queued transactions found at start. Exiting immediately.")
                return {
                    'success': True,
                    'message': 'No queued transactions to process',
                    'processed_count': 0,
                    'updated_count': 0,
                    'batches': 0,
                    'elapsed_seconds': 0
                }

            logger.info(f"Found {initial_count} queued transactions in total at start")

            # Loop while we have time remaining
            while True:
                # Check elapsed time
                elapsed_time = time.time() - start_time
                if elapsed_time >= TIME_LIMIT_SECONDS:
                    logger.info(f"Time limit reached ({elapsed_time:.2f}s >= {TIME_LIMIT_SECONDS}s). Stopping.")
                    break

                batch_count += 1
                logger.info(f"Starting batch {batch_count} (elapsed: {elapsed_time:.2f}s)")

                # Step 1: Get up to 50 queued transactions (sorted by transaction.id)
                queued_transactions = db.query(Transaction).filter(
                    Transaction.ai_audit_status == AIAuditStatus.queued,
                    Transaction.deleted_date.is_(None)
                ).order_by(Transaction.id).limit(200).all()

                if not queued_transactions:
                    logger.info("No more queued transactions found. Stopping.")
                    break

                logger.info(f"Found {len(queued_transactions)} queued transactions to process in batch {batch_count}")

                # Step 2: Group transactions by organization
                transactions_by_org = defaultdict(list)
                for transaction in queued_transactions:
                    transactions_by_org[transaction.organization_id].append(transaction)

                logger.info(f"Batch {batch_count}: Transactions grouped into {len(transactions_by_org)} organizations")

                # Step 3 & 4: Process each organization's transactions
                batch_processed = 0
                batch_updated = 0

                for org_id, org_transactions in transactions_by_org.items():
                    try:
                        logger.info(f"Batch {batch_count}: Processing {len(org_transactions)} transactions for organization {org_id}")

                        # Get audit rules for this organization
                        audit_rules = audit_service._get_audit_rules(db, org_id)

                        if not audit_rules:
                            logger.warning(f"No audit rules found for organization {org_id}, skipping")
                            continue

                        # Prepare transaction data
                        transaction_audit_data = audit_service._prepare_transaction_data(db, org_transactions)

                        # Process with AI using threading
                        audit_results = audit_service._process_transactions_with_ai(
                            transaction_audit_data,
                            audit_rules
                        )

                        # Update ai_audit_status (NOT transaction.status)
                        # Check organization's AI audit permission
                        from GEPPPlatform.models.subscriptions.organizations import Organization
                        allow_ai_audit = False
                        org = db.query(Organization).filter(Organization.id == org_id).first()
                        if org and hasattr(org, 'allow_ai_audit'):
                            allow_ai_audit = org.allow_ai_audit

                        # Update transaction statuses (only ai_audit_status, not the main status)
                        updated_count = audit_service._update_transaction_statuses(
                            db,
                            audit_results,
                            allow_ai_audit
                        )

                        batch_processed += len(audit_results)
                        batch_updated += updated_count

                        logger.info(f"Batch {batch_count}: Processed {len(audit_results)} transactions, updated {updated_count} for organization {org_id}")

                    except Exception as org_error:
                        logger.error(f"Batch {batch_count}: Error processing organization {org_id}: {str(org_error)}")
                        # Continue with next organization
                        continue

                # Update overall statistics
                overall_total_processed += batch_processed
                overall_total_updated += batch_updated
                overall_organizations_count += len(transactions_by_org)

                logger.info(f"Batch {batch_count} completed. Processed: {batch_processed}, Updated: {batch_updated}")

                # Check time again before next iteration
                elapsed_time = time.time() - start_time
                if elapsed_time >= TIME_LIMIT_SECONDS:
                    logger.info(f"Time limit reached after batch {batch_count} ({elapsed_time:.2f}s >= {TIME_LIMIT_SECONDS}s). Stopping.")
                    break

            # Final summary
            total_elapsed = time.time() - start_time
            logger.info(f"Cron job completed. Batches: {batch_count}, Total processed: {overall_total_processed}, Total updated: {overall_total_updated}, Elapsed: {total_elapsed:.2f}s")

            return {
                'success': True,
                'message': f'Processed {overall_total_processed} transactions in {batch_count} batches',
                'processed_count': overall_total_processed,
                'updated_count': overall_total_updated,
                'batches': batch_count,
                'elapsed_seconds': round(total_elapsed, 2)
            }

    except Exception as e:
        logger.error(f"Error in cron_process_audits: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

        return {
            'success': False,
            'error': str(e)
        }