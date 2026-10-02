"""
Route dispatch for the back-office Data Policy endpoints (unit = organization).

  GET    /admin/data-policy/catalog            categories, actions, unit meta
  GET    /admin/data-policy/rules              rule set + rule-set warnings
  POST   /admin/data-policy/rules              create rule
  PUT    /admin/data-policy/rules/{id}         update rule (partial)
  DELETE /admin/data-policy/rules/{id}         soft-delete rule
  GET    /admin/data-policy/units              organizations + last diagnosis
  GET    /admin/data-policy/units/{id}         one organization's inventory + issues
  POST   /admin/data-policy/diagnose           start ({unitIds?}) or advance ({runId}) a run
  GET    /admin/data-policy/diagnose/{runId}   run state

Contract (shared with the v2 EPR engine): gepp-new-webapp/src/pages/data-policy/types.ts
"""

from typing import Any, Dict, List, Optional

from ....exceptions import NotFoundException
from .engine import DataPolicyService


def _int(v: str) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        raise NotFoundException('Data policy endpoint not found')


def handle_data_policy_route(
    method: str,
    path_parts: List[str],
    data: Dict[str, Any],
    query_params: Dict[str, Any],
    db_session,
    current_user: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """`path_parts` is the /api/admin-stripped segments, e.g. ['data-policy', 'units', '12']."""
    svc = DataPolicyService(db_session, current_user)
    sub = path_parts[1] if len(path_parts) > 1 else ''
    rest = path_parts[2:]

    if method == 'GET':
        if sub == 'catalog' and not rest:
            return svc.catalog()
        if sub == 'rules' and not rest:
            return svc.list_rules()
        if sub == 'units' and not rest:
            return svc.list_units(query_params or {})
        if sub == 'units' and len(rest) == 1:
            return svc.get_unit(_int(rest[0]))
        if sub == 'diagnose' and len(rest) == 1:
            return svc.get_run(_int(rest[0]))
    elif method == 'POST':
        if sub == 'rules' and not rest:
            return svc.create_rule(data or {})
        if sub == 'diagnose' and not rest:
            return svc.diagnose_step(data or {})
    elif method == 'PUT':
        if sub == 'rules' and len(rest) == 1:
            return svc.update_rule(_int(rest[0]), data or {})
    elif method == 'DELETE':
        if sub == 'rules' and len(rest) == 1:
            return svc.delete_rule(_int(rest[0]))

    raise NotFoundException(f"Data policy endpoint not found: {method} /{'/'.join(path_parts)}")
