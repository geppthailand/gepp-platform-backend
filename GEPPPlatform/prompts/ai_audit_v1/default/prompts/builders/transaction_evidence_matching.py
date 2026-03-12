"""
Transaction-level Evidence Checklist Prompt Builder (Phase A)
Sends 1 evidence's extracted_data + ALL records → column-level match/found/errors
"""

import json
import yaml
from pathlib import Path
from typing import Dict, Any, List

PROMPT_PATH = Path(__file__).parent.parent / 'templates' / 'transaction_evidence_matching.yaml'


def _load_template() -> str:
    with open(PROMPT_PATH, 'r') as f:
        data = yaml.safe_load(f)
    return data['template']


def build_transaction_checklist_prompt(
    single_evidence_data: Dict[str, Any],
    all_records_data: List[Dict[str, Any]],
    checklist_columns: List[str],
) -> str:
    """
    Build a prompt for LLM to check 1 evidence against ALL records at column level.

    Args:
        single_evidence_data: Extracted data from 1 evidence file, e.g.:
            {'file_id': 123, 'document_type_name': '...', 'extracted_data': {...}}
        all_records_data: List of all records with resolved names, e.g.:
            [{'record_id': 1, 'material_name': '...', 'origin_weight_kg': 12.5, ...}, ...]
        checklist_columns: List of column names to verify, e.g.:
            ['material_id', 'origin_weight_kg', 'transaction_date']

    Returns:
        Prompt string for LLM
    """
    template = _load_template()

    return template.format(
        evidence_data=json.dumps(single_evidence_data, ensure_ascii=False, indent=2),
        all_records_data=json.dumps(all_records_data, ensure_ascii=False, indent=2),
        checklist_columns=json.dumps(checklist_columns, ensure_ascii=False),
    )
