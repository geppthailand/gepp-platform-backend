import json
import os
import logging
import traceback


def cron_process_audits(event, context):
    """
    Cron job to process queued AI audits via OpenRouter (Grok).

    Process flow:
    1. Check OPENROUTER_API_KEY is configured
    2. Call run_default_audit which processes from transaction_audit_history queue
    3. Uses 2-level threading: per-org → per-transaction
    4. Classifies evidence documents, extracts data, cross-verifies against transaction fields
    """
    logger = logging.getLogger(__name__)
    logger.info("Starting cron_process_audits")

    openrouter_key = os.getenv('OPENROUTER_API_KEY')
    if not openrouter_key:
        logger.error("OPENROUTER_API_KEY not configured")
        return {
            'success': False,
            'error': 'OPENROUTER_API_KEY not configured'
        }

    try:
        from GEPPPlatform.prompts.ai_audit_v1.default.scripts.audit_scripts import run_default_audit
        from GEPPPlatform.database import db_manager

        logger.info("Starting default AI audit processing from transaction_audit_history queue")
        result = run_default_audit(db_manager.get_session_factory)
        logger.info(f"Default AI audit completed: {json.dumps(result, default=str)}")

        return {
            'success': True,
            **result
        }

    except Exception as e:
        logger.error(f"Error in cron_process_audits: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")

        return {
            'success': False,
            'error': str(e)
        }
