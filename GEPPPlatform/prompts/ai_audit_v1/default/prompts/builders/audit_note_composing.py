"""
Audit Note Composing Prompt Builder
Loads prompt from YAML and fills in checklist results + errors
"""

import json
import yaml
from pathlib import Path
from typing import Dict, Any, List

PROMPT_PATH = Path(__file__).parent.parent / 'templates' / 'audit_note_composing.yaml'


def _load_template() -> str:
    with open(PROMPT_PATH, 'r') as f:
        data = yaml.safe_load(f)
    return data['template']


def build_audit_note_prompt(
    transaction_id: int,
    final_checklist: Dict[str, Dict],
    per_record_results: List[Dict[str, Any]],
    missing_doc_types: Dict[str, Any],
    evidence_summary: List[Dict[str, Any]],
    rejection_errors: List[str],
) -> str:
    """
    Build a prompt for LLM to compose a final audit note summary.

    Args:
        transaction_id: Transaction ID being audited
        final_checklist: Final OR-merged checklist {col: {match, found, error}}
        per_record_results: List of per-record checklist summaries
        missing_doc_types: {all_present, missing_transaction_docs, missing_record_docs}
        evidence_summary: List of {file_id, document_type_name, confidence}
        rejection_errors: Collected error messages from all phases

    Returns:
        Prompt string for LLM
    """
    template = _load_template()

    return template.format(
        transaction_id=transaction_id,
        evidence_summary=json.dumps(evidence_summary, ensure_ascii=False, indent=2),
        missing_docs=json.dumps(missing_doc_types, ensure_ascii=False, indent=2),
        final_checklist=json.dumps(final_checklist, ensure_ascii=False, indent=2),
        per_record_results=json.dumps(per_record_results, ensure_ascii=False, indent=2),
        rejection_errors=json.dumps(rejection_errors, ensure_ascii=False, indent=2),
    )
