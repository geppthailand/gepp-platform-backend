"""
Audit Note Composing Prompt Builder
Loads prompt from YAML and fills in matching results data
"""

import json
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional

PROMPT_PATH = Path(__file__).parent.parent / 'templates' / 'audit_note_composing.yaml'


def _load_template() -> str:
    with open(PROMPT_PATH, 'r') as f:
        data = yaml.safe_load(f)
    return data['template']


def build_audit_note_prompt(
    transaction_id: int,
    transaction_matching_result: Optional[Dict[str, Any]],
    record_matching_results: List[Dict[str, Any]],
    missing_doc_types: Dict[str, Any],
    evidence_summary: List[Dict[str, Any]]
) -> str:
    """
    Build a prompt for LLM to compose a final audit note summary.

    Args:
        transaction_id: Transaction ID being audited
        transaction_matching_result: Result from transaction-level matching, or None
        record_matching_results: List of {record_id, material_name, matching_result} per record
        missing_doc_types: {
            'all_present': bool,
            'missing_transaction_docs': [doc_type_name, ...],
            'missing_record_docs': {record_id: [doc_type_name, ...]},
        }
        evidence_summary: List of {file_id, document_type_name, confidence} for context

    Returns:
        Prompt string for LLM
    """
    template = _load_template()

    return template.format(
        transaction_id=transaction_id,
        evidence_summary=json.dumps(evidence_summary, ensure_ascii=False, indent=2),
        missing_docs=json.dumps(missing_doc_types, ensure_ascii=False, indent=2),
        transaction_matching_result=json.dumps(transaction_matching_result, ensure_ascii=False, indent=2) if transaction_matching_result else "No transaction-level checks configured",
        record_matching_results=json.dumps(record_matching_results, ensure_ascii=False, indent=2) if record_matching_results else "No record-level checks configured",
    )
