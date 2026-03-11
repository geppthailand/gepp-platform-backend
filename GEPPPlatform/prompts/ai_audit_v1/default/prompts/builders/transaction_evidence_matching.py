"""
Transaction-level Evidence Matching Prompt Builder
Loads prompt from YAML and fills in transaction/evidence data
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


def build_transaction_matching_prompt(
    transaction_data: Dict[str, Any],
    extracted_evidence: List[Dict[str, Any]],
    check_columns: Dict[str, bool]
) -> str:
    """
    Build a prompt for LLM to match extracted evidence against transaction-level fields.

    Args:
        transaction_data: {
            'transaction_id': int,
            'origin_name': str,
            'destination_names': list[str],
            'weight_kg': float,
            'total_amount': float,
            'transaction_date': str (YYYY-MM-DD),
        }
        extracted_evidence: list of {
            'file_id': int,
            'document_type_id': int,
            'document_type_name': str,
            'extracted_data': dict,
        }
        check_columns: dict of column_name -> bool (which columns to check)

    Returns:
        Prompt string for LLM
    """
    template = _load_template()
    columns_to_check = [k for k, v in check_columns.items() if v]

    return template.format(
        transaction_data=json.dumps(transaction_data, ensure_ascii=False, indent=2),
        extracted_evidence=json.dumps(extracted_evidence, ensure_ascii=False, indent=2),
        columns_to_check=json.dumps(columns_to_check),
    )
