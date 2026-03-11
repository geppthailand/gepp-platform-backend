"""
Default AI Audit Script
Main entry point for the default audit system using OpenRouter LLM.
Processes transaction_audit_history records with 2-level threading.
"""

import logging
import time
import json
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import and_

logger = logging.getLogger(__name__)

# Constants
MAX_TRANSACTIONS_PER_BATCH = 25
MAX_THREAD_WORKERS = 10
ALLOWED_TRANSACTION_METHODS = ('origin', 'qr_input')
SETTINGS_PATH = Path(__file__).parent.parent / 'settings.json'

SUPPORTED_IMAGE_TYPES = {'image/jpeg', 'image/jpg', 'image/png', 'image/webp'}
SPREADSHEET_TYPES = {
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
    'application/vnd.ms-excel',  # .xls
    'text/csv',
    'application/csv',
}
PDF_TYPES = {'application/pdf'}
WORD_TYPES = {
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # .docx
    'application/msword',  # .doc
}
# All file types that are processed (for logging/tracking)
ALL_SUPPORTED_TYPES = SUPPORTED_IMAGE_TYPES | SPREADSHEET_TYPES | PDF_TYPES | WORD_TYPES


def _load_settings() -> Dict[str, Any]:
    with open(SETTINGS_PATH, 'r') as f:
        return json.load(f)


def run_default_audit(get_session_factory: Callable) -> Dict[str, Any]:
    """
    Main entry point called from audit_cron.py.
    Manages Level-1 threading (one thread per org's audit_history record).

    Args:
        get_session_factory: Callable that returns a session factory (scoped_session)

    Returns:
        Summary dict of processing results
    """
    from GEPPPlatform.models.logs.transaction_audit_history import TransactionAuditHistory

    logger.info("Starting default audit processing")
    start_time = time.time()
    session_factory = get_session_factory()

    try:
        # Get a session for the initial query
        db = session_factory()
        try:
            # Step 1: Query pending/in_progress audit history, sorted by id ASC
            histories = db.query(TransactionAuditHistory).filter(
                and_(
                    TransactionAuditHistory.status.in_(['pending', 'in_progress']),
                    TransactionAuditHistory.deleted_date.is_(None)
                )
            ).order_by(TransactionAuditHistory.id.asc()).all()

            if not histories:
                logger.info("No pending/in_progress audit history records found")
                return {'success': True, 'message': 'No audit tasks to process', 'processed': 0}

            # Deduplicate: keep only the first (lowest id) per unique organization
            seen_orgs = set()
            unique_histories = []
            for h in histories:
                if h.organization_id not in seen_orgs:
                    seen_orgs.add(h.organization_id)
                    unique_histories.append((h.id, h.organization_id))

            logger.info(f"Found {len(unique_histories)} unique org audit tasks from {len(histories)} total records")
        finally:
            db.close()

        # Level-1 threading: one thread per org's audit history
        results = []
        with ThreadPoolExecutor(max_workers=min(len(unique_histories), MAX_THREAD_WORKERS)) as executor:
            futures = {}
            for history_id, org_id in unique_histories:
                future = executor.submit(
                    _process_single_audit_history,
                    history_id, org_id, session_factory
                )
                futures[future] = (history_id, org_id)

            for future in as_completed(futures):
                history_id, org_id = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    logger.info(f"Audit history #{history_id} (org {org_id}) completed: {result.get('status')}")
                except Exception as e:
                    logger.error(f"Audit history #{history_id} (org {org_id}) failed: {str(e)}")
                    logger.error(traceback.format_exc())
                    results.append({'history_id': history_id, 'org_id': org_id, 'status': 'error', 'error': str(e)})

        elapsed = time.time() - start_time
        total_processed = sum(r.get('processed_count', 0) for r in results)
        logger.info(f"Default audit completed. {total_processed} transactions processed in {elapsed:.2f}s")

        return {
            'success': True,
            'message': f'Processed {total_processed} transactions across {len(results)} batches',
            'processed': total_processed,
            'batches': len(results),
            'elapsed_seconds': round(elapsed, 2),
            'results': results,
        }

    except Exception as e:
        logger.error(f"Error in run_default_audit: {str(e)}")
        logger.error(traceback.format_exc())
        return {'success': False, 'error': str(e)}


def _process_single_audit_history(
    history_id: int,
    organization_id: int,
    session_factory
) -> Dict[str, Any]:
    """
    Process one transaction_audit_history record.
    Steps 2-9 for a single org batch.
    """
    from GEPPPlatform.models.logs.transaction_audit_history import TransactionAuditHistory
    from GEPPPlatform.models.transactions.transactions import Transaction, AIAuditStatus
    from GEPPPlatform.models.transactions.transaction_records import TransactionRecord
    from GEPPPlatform.models.transactions.ai_audit_document_types import AiAuditDocumentType
    from GEPPPlatform.models.subscriptions.organization_audit_settings import (
        OrganizationAuditDocRequireTypes, OrganizationAuditCheckColumns
    )
    from ..clients.llm_client import get_default_audit_llm

    db = session_factory()
    try:
        # Step 2: Get history and mark as in_progress
        history = db.query(TransactionAuditHistory).filter(
            TransactionAuditHistory.id == history_id
        ).first()

        if not history:
            return {'history_id': history_id, 'status': 'not_found', 'processed_count': 0}

        if history.status == 'pending':
            history.status = 'in_progress'
            history.started_at = datetime.now(timezone.utc)
            db.commit()

        # Step 3: Get queued transactions from the history's transaction list
        tx_ids = history.transactions or []
        if not tx_ids:
            history.status = 'completed'
            history.completed_at = datetime.now(timezone.utc)
            db.commit()
            return {'history_id': history_id, 'status': 'completed', 'processed_count': 0, 'message': 'No transactions in batch'}

        transactions = db.query(Transaction).filter(
            and_(
                Transaction.id.in_(tx_ids),
                Transaction.ai_audit_status == AIAuditStatus.queued,
                Transaction.transaction_method.in_(ALLOWED_TRANSACTION_METHODS),
                Transaction.deleted_date.is_(None)
            )
        ).order_by(Transaction.id.asc()).limit(MAX_TRANSACTIONS_PER_BATCH).all()

        if not transactions:
            # Check if there are any remaining queued transactions
            remaining = db.query(Transaction).filter(
                and_(
                    Transaction.id.in_(tx_ids),
                    Transaction.ai_audit_status == AIAuditStatus.queued,
                    Transaction.deleted_date.is_(None)
                )
            ).count()

            if remaining == 0:
                history.status = 'completed'
                history.completed_at = datetime.now(timezone.utc)
                db.commit()

            return {'history_id': history_id, 'status': 'completed', 'processed_count': 0, 'message': 'No eligible queued transactions'}

        logger.info(f"Processing {len(transactions)} transactions for audit history #{history_id} (org {organization_id})")

        # Load org config
        doc_type_specs = db.query(AiAuditDocumentType).filter(
            AiAuditDocumentType.deleted_date.is_(None),
            AiAuditDocumentType.is_active.is_(True)
        ).all()
        doc_type_specs_list = [dt.to_dict() for dt in doc_type_specs]

        doc_requires = db.query(OrganizationAuditDocRequireTypes).filter(
            OrganizationAuditDocRequireTypes.organization_id == organization_id,
            OrganizationAuditDocRequireTypes.deleted_date.is_(None)
        ).first()

        check_columns = db.query(OrganizationAuditCheckColumns).filter(
            OrganizationAuditCheckColumns.organization_id == organization_id,
            OrganizationAuditCheckColumns.deleted_date.is_(None)
        ).first()

        config = {
            'doc_type_specs': doc_type_specs_list,
            'doc_requires': doc_requires.to_dict() if doc_requires else {'transaction_document_requires': [], 'record_document_requires': []},
            'check_columns': check_columns.to_dict() if check_columns else {'transaction_checks': {}, 'transaction_record_checks': {}},
        }

        # Initialize LLM
        settings = _load_settings()
        model_version = settings.get('model', 'x-ai/grok-4.1-fast')

        db.close()  # Close parent session before threading

        # Level-2 threading: one thread per transaction
        tx_results = []
        with ThreadPoolExecutor(max_workers=min(len(transactions), MAX_THREAD_WORKERS)) as executor:
            futures = {}
            for tx in transactions:
                future = executor.submit(
                    _process_single_transaction,
                    tx.id, organization_id, config, model_version, session_factory
                )
                futures[future] = tx.id

            for future in as_completed(futures):
                tx_id = futures[future]
                try:
                    result = future.result()
                    tx_results.append(result)
                except Exception as e:
                    logger.error(f"Transaction #{tx_id} audit failed: {str(e)}")
                    logger.error(traceback.format_exc())
                    tx_results.append({
                        'transaction_id': tx_id,
                        'status': 'failed',
                        'error': str(e),
                    })
                    # Mark the transaction as failed
                    _mark_transaction_failed(tx_id, str(e), session_factory)

        # Update audit history with results
        db = session_factory()
        try:
            history = db.query(TransactionAuditHistory).filter(
                TransactionAuditHistory.id == history_id
            ).first()

            if history:
                approved = sum(1 for r in tx_results if r.get('status') == 'approved')
                rejected = sum(1 for r in tx_results if r.get('status') == 'rejected')
                failed = sum(1 for r in tx_results if r.get('status') == 'failed')

                history.processed_transactions = (history.processed_transactions or 0) + len(tx_results)
                history.approved_count = (history.approved_count or 0) + approved
                history.rejected_count = (history.rejected_count or 0) + rejected

                # Check if all transactions are processed
                remaining_queued = db.query(Transaction).filter(
                    and_(
                        Transaction.id.in_(tx_ids),
                        Transaction.ai_audit_status == AIAuditStatus.queued,
                        Transaction.deleted_date.is_(None)
                    )
                ).count()

                if remaining_queued == 0:
                    history.status = 'completed'
                    history.completed_at = datetime.now(timezone.utc)

                history.audit_info = {
                    'last_batch': {
                        'processed': len(tx_results),
                        'approved': approved,
                        'rejected': rejected,
                        'failed': failed,
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                    }
                }
                flag_modified(history, 'audit_info')
                db.commit()
        finally:
            db.close()

        return {
            'history_id': history_id,
            'org_id': organization_id,
            'status': 'completed',
            'processed_count': len(tx_results),
            'approved': sum(1 for r in tx_results if r.get('status') == 'approved'),
            'rejected': sum(1 for r in tx_results if r.get('status') == 'rejected'),
            'failed': sum(1 for r in tx_results if r.get('status') == 'failed'),
        }

    except Exception as e:
        logger.error(f"Error processing audit history #{history_id}: {str(e)}")
        logger.error(traceback.format_exc())
        try:
            db = session_factory()
            history = db.query(TransactionAuditHistory).filter(
                TransactionAuditHistory.id == history_id
            ).first()
            if history:
                history.error_message = str(e)[:500]
                db.commit()
            db.close()
        except Exception:
            pass
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass


def _mark_transaction_failed(tx_id: int, error_msg: str, session_factory) -> None:
    """Mark a transaction as failed audit"""
    from GEPPPlatform.models.transactions.transactions import Transaction, AIAuditStatus

    db = session_factory()
    try:
        tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
        if tx:
            tx.ai_audit_status = AIAuditStatus.failed
            tx.ai_audit_note = {
                'status': 'failed',
                'error': error_msg[:500],
            }
            tx.ai_audit_date = datetime.now(timezone.utc)
            flag_modified(tx, 'ai_audit_note')
            db.commit()
    except Exception as e:
        logger.error(f"Failed to mark transaction #{tx_id} as failed: {str(e)}")
        db.rollback()
    finally:
        db.close()


def _process_single_transaction(
    transaction_id: int,
    organization_id: int,
    config: Dict[str, Any],
    model_version: str,
    session_factory
) -> Dict[str, Any]:
    """
    Process a single transaction through steps 4-9.
    Each call gets its own DB session.
    """
    from GEPPPlatform.models.transactions.transactions import Transaction, AIAuditStatus
    from GEPPPlatform.models.transactions.transaction_records import TransactionRecord
    from GEPPPlatform.models.transactions.transaction_audits import TransactionAudit
    from GEPPPlatform.models.cores.files import File
    from GEPPPlatform.models.users.user_location import UserLocation
    from GEPPPlatform.models.cores.references import Material
    from ..clients.llm_client import get_default_audit_llm, call_llm_with_images, call_llm_text_only, parse_json_response  # noqa: F401

    processing_start = time.time()
    total_token_usage = {'input_tokens': 0, 'output_tokens': 0}

    db = session_factory()
    try:
        # Load transaction and its records
        tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not tx:
            return {'transaction_id': transaction_id, 'status': 'failed', 'error': 'Transaction not found'}

        record_ids = tx.transaction_records or []
        records = []
        if record_ids:
            records = db.query(TransactionRecord).filter(
                TransactionRecord.id.in_(record_ids)
            ).all()

        llm = get_default_audit_llm()

        # === Step 4: Collect images ===
        t0 = time.time()
        image_data = _step4_collect_images(tx, records, db)
        logger.info(f"Tx #{transaction_id} Step 4 (collect files): {time.time()-t0:.1f}s — {len(image_data.get('all_files', {}))} files")

        # === Step 6: Classify evidence ===
        t0 = time.time()
        classified_evidence = _step6_classify_evidence(
            image_data, config['doc_type_specs'], llm, db, total_token_usage
        )
        logger.info(f"Tx #{transaction_id} Step 6 (classify): {time.time()-t0:.1f}s — {len(classified_evidence)} files classified")

        # === Step 7: Check required docs ===
        doc_check = _step7_check_required_docs(
            classified_evidence, config['doc_requires'],
            image_data.get('transaction_file_ids', []),
            image_data.get('record_file_ids', {}),
            doc_type_specs=config['doc_type_specs'],
        )

        # === Step 8: Match evidence to data ===
        t0 = time.time()
        matching_result = _step8_match_evidence_to_data(
            tx, records, classified_evidence, config['check_columns'], db, llm, total_token_usage
        )
        logger.info(f"Tx #{transaction_id} Step 8 (match): {time.time()-t0:.1f}s — {len(records)} records")

        # === Step 9: Compose & Save ===
        t0 = time.time()
        final_result = _step9_compose_and_save(
            tx, records, doc_check, matching_result, classified_evidence,
            total_token_usage, processing_start, organization_id, model_version,
            db, llm
        )
        logger.info(f"Tx #{transaction_id} Step 9 (compose): {time.time()-t0:.1f}s")

        db.commit()
        return final_result

    except Exception as e:
        db.rollback()
        logger.error(f"Error processing transaction #{transaction_id}: {str(e)}")
        logger.error(traceback.format_exc())
        raise
    finally:
        db.close()


def _step4_collect_images(
    tx: Any,
    records: List[Any],
    db: Session
) -> Dict[str, Any]:
    """
    Step 4: Collect image file IDs from transaction and records.
    Filter: skip strings (URLs not allowed in default), keep integers (file IDs).
    Query File table and generate presigned read URLs.
    """
    from GEPPPlatform.models.cores.files import File
    from GEPPPlatform.services.cores.transactions.presigned_url_service import TransactionPresignedUrlService

    result = {
        'transaction_images': [],
        'record_images': {},
        'transaction_file_ids': [],
        'record_file_ids': {},
        'all_files': {},  # file_id -> {presigned_url, mime_type, s3_key, source}
    }

    # Collect file IDs from transaction
    tx_image_ids = []
    for img in (tx.images or []):
        if isinstance(img, int):
            tx_image_ids.append(img)

    # Collect file IDs from each record
    record_image_ids = {}
    for record in records:
        rec_ids = []
        for img in (record.images or []):
            if isinstance(img, int):
                rec_ids.append(img)
        if rec_ids:
            record_image_ids[record.id] = rec_ids

    # Combine all file IDs for batch query
    all_file_ids = set(tx_image_ids)
    for ids in record_image_ids.values():
        all_file_ids.update(ids)

    if not all_file_ids:
        logger.info(f"Transaction #{tx.id}: No valid file IDs found in images")
        return result

    # Query files and generate presigned URLs
    files = db.query(File).filter(File.id.in_(all_file_ids)).all()
    file_map = {f.id: f for f in files}

    try:
        presigned_service = TransactionPresignedUrlService()
        presigned_result = presigned_service.get_transaction_file_view_presigned_urls_by_ids(
            file_ids=list(all_file_ids),
            db=db,
            organization_id=tx.organization_id,
            user_id=tx.created_by_id or 0,
            expiration_seconds=7200
        )

        presigned_urls = presigned_result.get('presigned_urls', {}) if presigned_result.get('success') else {}
    except Exception as e:
        logger.error(f"Failed to generate presigned URLs: {str(e)}")
        presigned_urls = {}

    # Build result
    for file_id in all_file_ids:
        f = file_map.get(file_id)
        url_data = presigned_urls.get(file_id, {})
        if f and url_data.get('view_url'):
            result['all_files'][file_id] = {
                'file_id': file_id,
                'presigned_url': url_data['view_url'],
                'mime_type': f.mime_type,
                's3_key': f.s3_key,
            }

    result['transaction_file_ids'] = tx_image_ids
    result['transaction_images'] = [result['all_files'][fid] for fid in tx_image_ids if fid in result['all_files']]
    result['record_file_ids'] = record_image_ids
    for rec_id, fids in record_image_ids.items():
        result['record_images'][rec_id] = [result['all_files'][fid] for fid in fids if fid in result['all_files']]

    logger.info(f"Transaction #{tx.id}: Collected {len(result['all_files'])} files ({len(result['transaction_images'])} tx-level, {sum(len(v) for v in result['record_images'].values())} record-level)")
    return result


def _download_file_bytes(presigned_url: str, timeout: int = 30) -> bytes:
    """Download file content from a presigned URL."""
    from urllib.request import urlopen
    response = urlopen(presigned_url, timeout=timeout)
    return response.read()


def _parse_spreadsheet_to_text(file_bytes: bytes, mime_type: str) -> str:
    """
    Parse spreadsheet (xlsx/xls/csv) to text.
    Uses openpyxl for xlsx, csv stdlib for csv.
    Returns formatted text representation of all sheets/data.
    """
    import io
    import csv

    if mime_type in ('text/csv', 'application/csv'):
        text_content = file_bytes.decode('utf-8', errors='replace')
        reader = csv.reader(io.StringIO(text_content))
        rows = list(reader)
        if not rows:
            return "(Empty CSV file)"
        lines = []
        for i, row in enumerate(rows):
            lines.append(f"Row {i+1}: {' | '.join(row)}")
        return f"[CSV — {len(rows)} rows]\n" + '\n'.join(lines)

    else:
        # Excel (xlsx/xls)
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        except Exception as e:
            logger.error(f"Failed to parse Excel file: {e}")
            return f"(Failed to parse Excel file: {str(e)})"

        all_sheets_text = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = []
            for row in ws.iter_rows(values_only=True):
                cell_values = [str(c) if c is not None else '' for c in row]
                if any(v.strip() for v in cell_values):
                    rows.append(cell_values)

            if not rows:
                all_sheets_text.append(f"[Sheet: {sheet_name}] (Empty)")
                continue

            lines = []
            for i, row in enumerate(rows):
                lines.append(f"Row {i+1}: {' | '.join(row)}")
            all_sheets_text.append(f"[Sheet: {sheet_name} — {len(rows)} rows]\n" + '\n'.join(lines))

        wb.close()
        return '\n\n'.join(all_sheets_text)


def _parse_pdf_to_text(file_bytes: bytes) -> str:
    """
    Parse PDF to text using pypdf (pure Python, no native deps).
    Returns all pages as text.
    """
    import io
    try:
        from pypdf import PdfReader
    except ImportError:
        # Fallback: try PyPDF2 (older name)
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            logger.error("Neither pypdf nor PyPDF2 available for PDF parsing")
            return "(PDF parsing unavailable — pypdf not installed)"

    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        pages_text = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ''
            if text.strip():
                pages_text.append(f"[Page {i+1}]\n{text.strip()}")
        if not pages_text:
            return "(PDF has no extractable text — may be scanned/image-based)"
        return '\n\n'.join(pages_text)
    except Exception as e:
        logger.error(f"Failed to parse PDF: {e}")
        return f"(Failed to parse PDF: {str(e)})"


def _parse_word_to_text(file_bytes: bytes) -> str:
    """
    Parse Word document (.docx) to text.
    Uses python-docx for .docx files.
    """
    import io
    try:
        from docx import Document
    except ImportError:
        logger.error("python-docx not available for Word parsing")
        return "(Word parsing unavailable — python-docx not installed)"

    try:
        doc = Document(io.BytesIO(file_bytes))
        paragraphs = []
        for para in doc.paragraphs:
            if para.text.strip():
                paragraphs.append(para.text.strip())

        # Also extract tables
        for i, table in enumerate(doc.tables):
            table_rows = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                table_rows.append(' | '.join(cells))
            if table_rows:
                paragraphs.append(f"[Table {i+1}]\n" + '\n'.join(table_rows))

        if not paragraphs:
            return "(Empty Word document)"
        return '\n\n'.join(paragraphs)
    except Exception as e:
        logger.error(f"Failed to parse Word document: {e}")
        return f"(Failed to parse Word document: {str(e)})"


def _step6_classify_evidence(
    image_data: Dict[str, Any],
    doc_type_specs: List[Dict],
    llm: Any,
    db: Session,
    token_usage: Dict[str, int]
) -> List[Dict[str, Any]]:
    """
    Step 6: Classify each evidence file and extract data using LLM.
    Store results in File.observation.
    """
    from GEPPPlatform.models.cores.files import File
    import yaml

    all_files = image_data.get('all_files', {})
    if not all_files:
        return []

    # Build document types spec string for the prompt
    types_for_prompt = []
    for dt in doc_type_specs:
        types_for_prompt.append({
            'id': dt['id'],
            'name_en': dt['name_en'],
            'name_th': dt['name_th'],
            'description': dt.get('description_en') or dt.get('description', ''),
            'extract_list': dt['extract_list'],
        })
    doc_types_spec_str = json.dumps(types_for_prompt, ensure_ascii=False, indent=2)

    # Load prompt template
    prompt_path = Path(__file__).parent.parent / 'prompts' / 'templates' / 'evidence_classify.yaml'
    with open(prompt_path, 'r') as f:
        prompt_data = yaml.safe_load(f)
    prompt_text = prompt_data['template'].format(document_types_spec=doc_types_spec_str)

    classified = []

    # Classify each file (threaded)
    def classify_single_file(file_id, file_info):
        from ..clients.llm_client import call_llm_with_images, call_llm_text_only, parse_json_response
        try:
            mime = (file_info.get('mime_type') or '').lower()
            presigned_url = file_info['presigned_url']

            if mime in SUPPORTED_IMAGE_TYPES:
                # Image: send as image_url to LLM
                response = call_llm_with_images(llm, prompt_text, [presigned_url])

            elif mime in SPREADSHEET_TYPES:
                # Spreadsheet: download, parse all sheets to text, send as text-only
                file_bytes = _download_file_bytes(presigned_url)
                parsed_text = _parse_spreadsheet_to_text(file_bytes, mime)
                combined_prompt = (
                    f"{prompt_text}\n\n"
                    f"--- SPREADSHEET CONTENT (from uploaded file) ---\n"
                    f"{parsed_text}\n"
                    f"--- END SPREADSHEET CONTENT ---"
                )
                response = call_llm_text_only(llm, combined_prompt)

            elif mime in PDF_TYPES:
                # PDF: download, extract text from all pages, send as text-only
                file_bytes = _download_file_bytes(presigned_url)
                parsed_text = _parse_pdf_to_text(file_bytes)
                combined_prompt = (
                    f"{prompt_text}\n\n"
                    f"--- PDF CONTENT (from uploaded file) ---\n"
                    f"{parsed_text}\n"
                    f"--- END PDF CONTENT ---"
                )
                response = call_llm_text_only(llm, combined_prompt)

            elif mime in WORD_TYPES:
                # Word document: download, extract text + tables, send as text-only
                file_bytes = _download_file_bytes(presigned_url)
                parsed_text = _parse_word_to_text(file_bytes)
                combined_prompt = (
                    f"{prompt_text}\n\n"
                    f"--- WORD DOCUMENT CONTENT (from uploaded file) ---\n"
                    f"{parsed_text}\n"
                    f"--- END WORD DOCUMENT CONTENT ---"
                )
                response = call_llm_text_only(llm, combined_prompt)

            else:
                logger.warning(f"File #{file_id} has unsupported mime type: {mime}, skipping")
                return {
                    'file_id': file_id,
                    'document_type_id': 0,
                    'document_type_name': 'skipped_unsupported',
                    'extracted_data': {},
                    'confidence': 0.0,
                    'skipped_reason': f'Unsupported mime type: {mime}',
                }

            # Parse response
            parsed = parse_json_response(response['content'])

            # Track tokens
            usage = response.get('usage', {})
            token_usage['input_tokens'] += usage.get('input_tokens', 0)
            token_usage['output_tokens'] += usage.get('output_tokens', 0)

            return {
                'file_id': file_id,
                'document_type_id': parsed.get('document_type_id', 0),
                'document_type_name': parsed.get('document_type_name', 'unknown'),
                'extracted_data': parsed.get('extracted_data', {}),
                'confidence': parsed.get('confidence', 0.0),
            }
        except Exception as e:
            logger.error(f"Failed to classify file #{file_id}: {str(e)}")
            return {
                'file_id': file_id,
                'document_type_id': 0,
                'document_type_name': 'error',
                'extracted_data': {},
                'confidence': 0.0,
                'error': str(e),
            }

    # Classify files sequentially (db session is not thread-safe)
    for fid, finfo in all_files.items():
        result = classify_single_file(fid, finfo)
        classified.append(result)

        # Store in File.observation for ALL results (classified, skipped, error)
        try:
            file_obj = db.query(File).filter(File.id == result['file_id']).first()
            if file_obj:
                observation = {
                    'document_type_id': result.get('document_type_id', 0),
                    'document_type_name': result.get('document_type_name', 'unknown'),
                    'extracted_data': result.get('extracted_data', {}),
                    'confidence': result.get('confidence', 0.0),
                    'classified_at': datetime.now(timezone.utc).isoformat(),
                }
                if result.get('skipped_reason'):
                    observation['skipped_reason'] = result['skipped_reason']
                if result.get('error'):
                    observation['error'] = result['error']
                file_obj.observation = observation
                flag_modified(file_obj, 'observation')
        except Exception as e:
            logger.error(f"Failed to update File.observation for #{result['file_id']}: {str(e)}")

    # Commit all observation updates
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Failed to commit File.observation updates: {str(e)}")

    logger.info(f"Classified {len(classified)} evidence files")
    return classified


def _step7_check_required_docs(
    classified_evidence: List[Dict],
    doc_requires: Dict[str, Any],
    transaction_file_ids: List[int],
    record_file_ids: Dict[int, List[int]],
    doc_type_specs: List[Dict] = None,
) -> Dict[str, Any]:
    """
    Step 7: Check if required document types are present.
    Transaction images are reusable for records.
    Returns missing doc info with resolved names.
    """
    tx_doc_requires = doc_requires.get('transaction_document_requires', [])
    rec_doc_requires = doc_requires.get('record_document_requires', [])

    if not tx_doc_requires and not rec_doc_requires:
        return {'all_present': True, 'missing_transaction_docs': [], 'missing_record_docs': {}}

    # Build doc type ID → name map
    dt_name_map = {}
    if doc_type_specs:
        for dt in doc_type_specs:
            dt_id = dt.get('id')
            dt_name_map[dt_id] = {
                'id': dt_id,
                'name_en': dt.get('name_en', f'Document Type #{dt_id}'),
                'name_th': dt.get('name_th', f'ประเภทเอกสาร #{dt_id}'),
            }

    def _resolve_doc_name(dt_id):
        """Return {id, name_en, name_th} for a doc type ID."""
        if dt_id in dt_name_map:
            return dt_name_map[dt_id]
        return {'id': dt_id, 'name_en': f'Document Type #{dt_id}', 'name_th': f'ประเภทเอกสาร #{dt_id}'}

    # Map file_id to its classified document_type_id
    file_to_type = {}
    for ev in classified_evidence:
        if ev.get('document_type_id') and ev['document_type_id'] != 0:
            file_to_type[ev['file_id']] = ev['document_type_id']

    # Check transaction-level requirements
    tx_present_types = set()
    for fid in transaction_file_ids:
        if fid in file_to_type:
            tx_present_types.add(file_to_type[fid])

    missing_tx = [_resolve_doc_name(dt_id) for dt_id in tx_doc_requires if dt_id not in tx_present_types]

    # Check record-level requirements (tx images are reusable)
    missing_records = {}
    for rec_id, rec_fids in record_file_ids.items():
        rec_present_types = set(tx_present_types)  # Include tx-level images
        for fid in rec_fids:
            if fid in file_to_type:
                rec_present_types.add(file_to_type[fid])

        missing_rec = [_resolve_doc_name(dt_id) for dt_id in rec_doc_requires if dt_id not in rec_present_types]
        if missing_rec:
            missing_records[rec_id] = missing_rec

    all_present = len(missing_tx) == 0 and len(missing_records) == 0

    return {
        'all_present': all_present,
        'missing_transaction_docs': missing_tx,
        'missing_record_docs': missing_records,
    }


def _step8_match_evidence_to_data(
    tx: Any,
    records: List[Any],
    classified_evidence: List[Dict],
    check_columns_config: Dict[str, Any],
    db: Session,
    llm: Any,
    token_usage: Dict[str, int]
) -> Dict[str, Any]:
    """
    Step 8: Match extracted evidence data against transaction and record columns.
    """
    from GEPPPlatform.models.users.user_location import UserLocation
    from GEPPPlatform.models.cores.references import Material
    from ..prompts.builders.transaction_evidence_matching import build_transaction_matching_prompt
    from ..prompts.builders.transaction_record_evidence_matching import build_record_matching_prompt
    from ..clients.llm_client import call_llm_text_only, parse_json_response

    tx_checks = check_columns_config.get('transaction_checks', {})
    rec_checks = check_columns_config.get('transaction_record_checks', {})

    # Prepare evidence data (all classified evidence)
    evidence_for_prompt = [
        {
            'file_id': ev['file_id'],
            'document_type_id': ev.get('document_type_id', 0),
            'document_type_name': ev.get('document_type_name', 'unknown'),
            'extracted_data': ev.get('extracted_data', {}),
        }
        for ev in classified_evidence if ev.get('extracted_data')
    ]

    result = {'transaction_match': None, 'record_matches': {}}

    # --- Transaction-level matching ---
    active_tx_checks = {k: v for k, v in tx_checks.items() if v}
    if active_tx_checks and evidence_for_prompt:
        # Resolve names for matching
        origin_name = ''
        if tx.origin_id:
            origin = db.query(UserLocation).filter(UserLocation.id == tx.origin_id).first()
            origin_name = (origin.name_en or '') if origin else ''

        destination_names = []
        dest_ids = tx.destination_ids or []
        if dest_ids:
            dests = db.query(UserLocation).filter(UserLocation.id.in_(dest_ids)).all()
            dest_map = {d.id: (d.name_en or '') for d in dests}
            destination_names = [dest_map.get(did, '') for did in dest_ids]

        tx_data = {
            'transaction_id': tx.id,
            'origin_name': origin_name,
            'destination_names': destination_names,
            'weight_kg': float(tx.weight_kg) if tx.weight_kg else 0,
            'total_amount': float(tx.total_amount) if tx.total_amount else 0,
            'transaction_date': tx.transaction_date.strftime('%Y-%m-%d') if tx.transaction_date else None,
        }

        prompt = build_transaction_matching_prompt(tx_data, evidence_for_prompt, active_tx_checks)
        try:
            response = call_llm_text_only(llm, prompt)
            token_usage['input_tokens'] += response.get('usage', {}).get('input_tokens', 0)
            token_usage['output_tokens'] += response.get('usage', {}).get('output_tokens', 0)
            result['transaction_match'] = parse_json_response(response['content'])
        except Exception as e:
            logger.error(f"Transaction matching failed for #{tx.id}: {str(e)}")
            result['transaction_match'] = {'error': str(e)}

    # --- Record-level matching (sequential — db session not thread-safe) ---
    active_rec_checks = {k: v for k, v in rec_checks.items() if v}
    if active_rec_checks and evidence_for_prompt and records:
        # Pre-resolve all material and destination names in batch
        material_ids = [r.material_id for r in records if r.material_id]
        dest_ids_rec = [r.destination_id for r in records if r.destination_id]

        mat_map = {}
        if material_ids:
            mats = db.query(Material).filter(Material.id.in_(material_ids)).all()
            mat_map = {m.id: (m.name_en or m.name_th or '') for m in mats}

        dest_map_rec = {}
        if dest_ids_rec:
            dests_rec = db.query(UserLocation).filter(UserLocation.id.in_(dest_ids_rec)).all()
            dest_map_rec = {d.id: (d.name_en or '') for d in dests_rec}

        # Also resolve origin name for records (from parent transaction)
        origin_name_for_records = ''
        if tx.origin_id:
            origin_loc = db.query(UserLocation).filter(UserLocation.id == tx.origin_id).first()
            origin_name_for_records = (origin_loc.name_en or '') if origin_loc else ''

        for record in records:
            try:
                mat_name = mat_map.get(record.material_id, '') if record.material_id else ''
                dest_name = dest_map_rec.get(record.destination_id, '') if record.destination_id else ''

                record_data = {
                    'record_id': record.id,
                    'material_name': mat_name,
                    'origin_name': origin_name_for_records,
                    'destination_name': dest_name,
                    'origin_weight_kg': float(record.origin_weight_kg) if record.origin_weight_kg else 0,
                    'origin_quantity': float(record.origin_quantity) if record.origin_quantity else 0,
                    'origin_price_per_unit': float(record.origin_price_per_unit) if record.origin_price_per_unit else 0,
                    'total_amount': float(record.total_amount) if record.total_amount else 0,
                    'transaction_date': record.transaction_date.strftime('%Y-%m-%d') if record.transaction_date else None,
                }

                prompt = build_record_matching_prompt(record_data, evidence_for_prompt, active_rec_checks)
                response = call_llm_text_only(llm, prompt)
                token_usage['input_tokens'] += response.get('usage', {}).get('input_tokens', 0)
                token_usage['output_tokens'] += response.get('usage', {}).get('output_tokens', 0)
                result['record_matches'][record.id] = parse_json_response(response['content'])
            except Exception as e:
                logger.error(f"Record matching failed for record #{record.id}: {str(e)}")
                result['record_matches'][record.id] = {'error': str(e)}

    return result


def _step9_compose_and_save(
    tx: Any,
    records: List[Any],
    doc_check: Dict[str, Any],
    matching_result: Dict[str, Any],
    classified_evidence: List[Dict],
    token_usage: Dict[str, int],
    processing_start: float,
    organization_id: int,
    model_version: str,
    db: Session,
    llm: Any
) -> Dict[str, Any]:
    """
    Step 9: Compose final audit note, update statuses, insert TransactionAudit record.
    """
    from GEPPPlatform.models.transactions.transactions import Transaction, AIAuditStatus
    from GEPPPlatform.models.transactions.transaction_records import TransactionRecord
    from GEPPPlatform.models.transactions.transaction_audits import TransactionAudit
    from ..prompts.builders.audit_note_composing import build_audit_note_prompt
    from ..clients.llm_client import call_llm_text_only, parse_json_response

    # Build evidence summary for the compose prompt
    evidence_summary = [
        {'file_id': ev['file_id'], 'document_type_name': ev.get('document_type_name', 'unknown'), 'confidence': ev.get('confidence', 0)}
        for ev in classified_evidence
    ]

    # Build record matching results with material names
    record_matches_for_prompt = []
    for rec in records:
        rec_match = matching_result.get('record_matches', {}).get(rec.id)
        record_matches_for_prompt.append({
            'record_id': rec.id,
            'material_name': getattr(rec, '_material_name', str(rec.material_id)),
            'matching_result': rec_match,
        })

    # Compose audit note via LLM
    compose_prompt = build_audit_note_prompt(
        transaction_id=tx.id,
        transaction_matching_result=matching_result.get('transaction_match'),
        record_matching_results=record_matches_for_prompt,
        missing_doc_types=doc_check,
        evidence_summary=evidence_summary,
    )

    try:
        response = call_llm_text_only(llm, compose_prompt)
        token_usage['input_tokens'] += response.get('usage', {}).get('input_tokens', 0)
        token_usage['output_tokens'] += response.get('usage', {}).get('output_tokens', 0)
        audit_note = parse_json_response(response['content'])
    except Exception as e:
        logger.error(f"Audit note composing failed for tx #{tx.id}: {str(e)}")
        # Fallback: determine status from matching results
        has_mismatch = False
        tx_match = matching_result.get('transaction_match', {})
        if isinstance(tx_match, dict) and not tx_match.get('error'):
            for _col, val in tx_match.items():
                if isinstance(val, dict) and val.get('match') is False:
                    has_mismatch = True
                    break
        for _rec_id, rec_match in matching_result.get('record_matches', {}).items():
            if isinstance(rec_match, dict) and not rec_match.get('error'):
                for _col, val in rec_match.items():
                    if isinstance(val, dict) and val.get('match') is False:
                        has_mismatch = True

        status = 'rejected' if (has_mismatch or not doc_check.get('all_present', True)) else 'approved'
        audit_note = {
            'status': status,
            'summary_th': 'ไม่สามารถสร้างสรุปอัตโนมัติได้',
            'summary_en': 'Could not generate automatic summary',
            'issues': [],
        }

    final_status = audit_note.get('status', 'rejected')
    processing_time_ms = int((time.time() - processing_start) * 1000)

    # Update transaction
    if final_status == 'approved':
        tx.ai_audit_status = AIAuditStatus.approved
    else:
        tx.ai_audit_status = AIAuditStatus.rejected

    tx.ai_audit_note = {
        'status': final_status,
        'summary_th': audit_note.get('summary_th', ''),
        'summary_en': audit_note.get('summary_en', ''),
        'issues': audit_note.get('issues', []),
        'evidence_classified': len(classified_evidence),
        'doc_check': doc_check,
        'matching': {
            'transaction': matching_result.get('transaction_match'),
            'records': {str(k): v for k, v in matching_result.get('record_matches', {}).items()},
        },
    }
    tx.ai_audit_date = datetime.now(timezone.utc)
    tx.audit_tokens = token_usage
    flag_modified(tx, 'ai_audit_note')
    flag_modified(tx, 'audit_tokens')

    # Update each record's ai_audit_status and ai_audit_note
    for record in records:
        rec_match = matching_result.get('record_matches', {}).get(record.id, {})
        rec_has_mismatch = False
        if isinstance(rec_match, dict) and not rec_match.get('error'):
            for col, val in rec_match.items():
                if isinstance(val, dict) and val.get('match') is False:
                    rec_has_mismatch = True
                    break

        # Check missing record docs
        rec_missing = doc_check.get('missing_record_docs', {}).get(record.id, [])

        if rec_has_mismatch or rec_missing:
            record.ai_audit_status = 'rejected'
        else:
            record.ai_audit_status = 'approved' if final_status == 'approved' else 'rejected'

        record.ai_audit_note = {
            'status': record.ai_audit_status,
            'matching': rec_match,
            'missing_docs': rec_missing,
        }
        flag_modified(record, 'ai_audit_note')

    # Insert TransactionAudit record
    audit_record = TransactionAudit(
        transaction_id=tx.id,
        audit_notes=tx.ai_audit_note,
        by_human=False,
        auditor_id=None,
        organization_id=organization_id,
        audit_type='ai_not_sync',
        processing_time_ms=processing_time_ms,
        token_usage=token_usage,
        model_version=model_version,
    )
    db.add(audit_record)

    logger.info(f"Transaction #{tx.id}: audit {final_status} (processing: {processing_time_ms}ms, tokens: {token_usage})")

    return {
        'transaction_id': tx.id,
        'status': final_status,
        'processing_time_ms': processing_time_ms,
        'token_usage': token_usage,
    }
