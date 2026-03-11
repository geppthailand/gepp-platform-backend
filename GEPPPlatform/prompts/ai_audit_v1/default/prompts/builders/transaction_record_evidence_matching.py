"""
Record-level Evidence Checklist Prompt Builder (Phase B)
Sends 1 record + ALL its record-level evidence → match/found/errors for unmatched columns only
"""

import json
import yaml
from pathlib import Path
from typing import Dict, Any, List

PROMPT_PATH = Path(__file__).parent.parent / 'templates' / 'transaction_record_evidence_matching.yaml'


def _load_template() -> str:
    with open(PROMPT_PATH, 'r') as f:
        data = yaml.safe_load(f)
    return data['template']


def build_record_checklist_prompt(
    record_data: Dict[str, Any],
    record_evidence_list: List[Dict[str, Any]],
    unmatched_columns: List[str],
) -> str:
    """
    Build a prompt for LLM to check ALL record-level evidence against 1 record,
    only for columns that were NOT matched at the transaction level.

    Args:
        record_data: Single record with resolved names, e.g.:
            {'record_id': 1, 'material_name': 'ขวด PET', 'origin_weight_kg': 12.5, ...}
        record_evidence_list: List of all evidence for this record, e.g.:
            [{'file_id': 456, 'document_type_name': '...', 'extracted_data': {...}}, ...]
        unmatched_columns: Columns still unmatched from Phase A, e.g.:
            ['origin_weight_kg', 'total_amount']

    Returns:
        Prompt string for LLM
    """
    template = _load_template()

    return template.format(
        record_data=json.dumps(record_data, ensure_ascii=False, indent=2),
        record_evidence_list=json.dumps(record_evidence_list, ensure_ascii=False, indent=2),
        unmatched_columns=json.dumps(unmatched_columns, ensure_ascii=False),
    )
