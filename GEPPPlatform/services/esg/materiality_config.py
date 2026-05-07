"""
Materiality Filter — Python config + scoring engine.

Mirrors the frontend implementation at:
  v3/frontend/gepp-esg/src/mat_filters/{questions,industries,scoring}.yaml
  v3/frontend/gepp-esg/src/mat_filters/scoring.ts

The two implementations share the same YAML files (loaded directly from
the frontend tree at module import time) and the same fixture set at
v3/frontend/gepp-esg/src/mat_filters/__tests__/scoring_fixtures.json,
so they can never disagree on what counts as "material".

DO NOT inline category weights or thresholds here — always read from
the YAML so a single edit propagates to both sides.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


# Resolve the frontend mat_filters/ directory relative to this file.
# Layout: <repo>/v3/backend/GEPPPlatform/services/esg/materiality_config.py
#         <repo>/v3/frontend/gepp-esg/src/mat_filters/*.yaml
# parents[4] from this file is the v3/ directory.
_THIS = Path(__file__).resolve()
_V3_DIR = _THIS.parents[4]
_FE_MAT_FILTERS = _V3_DIR / 'frontend' / 'gepp-esg' / 'src' / 'mat_filters'


def _load_yaml(name: str) -> Any:
    path = _FE_MAT_FILTERS / name
    if not path.exists():
        # Allow override via env var for production deploys that bundle the
        # YAMLs into the lambda artifact at a different path.
        override = os.environ.get('GEPP_MAT_FILTERS_DIR')
        if override:
            path = Path(override) / name
    with path.open('r', encoding='utf-8') as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=1)
def get_questions() -> dict:
    return _load_yaml('questions.yaml')


@lru_cache(maxsize=1)
def get_industries() -> dict:
    return _load_yaml('industries.yaml')


@lru_cache(maxsize=1)
def get_categories_meta() -> dict:
    return _load_yaml('categories.yaml')


@lru_cache(maxsize=1)
def get_scoring() -> dict:
    return _load_yaml('scoring.yaml')


# ─── show_when evaluator ────────────────────────────────────────────────────

def _selected_set(answer: dict | None) -> set[str]:
    if not answer:
        return set()
    if answer.get('kind') == 'single':
        sel = answer.get('selected')
        return {sel} if sel else set()
    if answer.get('kind') == 'multi':
        return set(answer.get('selected') or [])
    return set()


def _evaluate_show_when(rule: dict | None, answers: dict) -> bool:
    if not rule:
        return True
    field = rule.get('field')
    op = rule.get('op')
    value = rule.get('value')
    arr_value = value if isinstance(value, list) else [value]
    selected = _selected_set(answers.get(field))

    if op == 'any_of':
        return any(v in selected for v in arr_value)
    if op == 'all_of':
        return all(v in selected for v in arr_value)
    if op == 'equals':
        ans = answers.get(field) or {}
        return ans.get('kind') == 'single' and ans.get('selected') == value
    if op == 'not_equals':
        ans = answers.get(field) or {}
        return not (ans.get('kind') == 'single' and ans.get('selected') == value)
    if op == 'not_in':
        return not any(v in selected for v in arr_value)
    return True


# ─── scoring ────────────────────────────────────────────────────────────────

def _add_weights(target: dict[int, float], weights: dict | None) -> None:
    if not weights:
        return
    for k, v in weights.items():
        try:
            cid = int(k)
        except (TypeError, ValueError):
            continue
        target[cid] = target.get(cid, 0.0) + float(v)


def compute_scores(answers: dict) -> dict:
    """
    Returns:
      {
        'scores': { 1: 1.4, 5: 0.8, ... },
        'buckets': { 1: 'material', 5: 'consider', ... },
        'derivedCategories': [1, 5, 6, 7],
      }
    """
    questions_file = get_questions()
    industries_file = get_industries()
    scoring = get_scoring()
    questions = questions_file.get('questions') or []
    industries = industries_file.get('industries') or []

    scores: dict[int, float] = {}

    # 1. Q1 industry seed
    q1 = answers.get('q1_industry')
    if q1 and q1.get('kind') == 'single':
        sel = q1.get('selected')
        industry = next((i for i in industries if i.get('id') == sel), None)
        if industry:
            _add_weights(scores, industry.get('default_category_seeds'))

    # 2. per-option weights for visible answered questions
    for q in questions:
        qid = q.get('id')
        if qid == 'q1_industry':
            continue
        if not _evaluate_show_when(q.get('show_when'), answers):
            continue
        ans = answers.get(qid)
        if not ans:
            continue
        selected_ids = (
            [ans.get('selected')]
            if ans.get('kind') == 'single'
            else list(ans.get('selected') or [])
        )
        for opt in q.get('options') or []:
            if opt.get('id') in selected_ids:
                _add_weights(scores, opt.get('category_weights'))

    # 3. cap each
    cap = float(scoring.get('score_cap') or 2.5)
    for k in list(scores.keys()):
        if scores[k] > cap:
            scores[k] = cap

    # 4 + 5 + 6: bucket
    total = sum(scores.values())
    promote_all = total < float(
        scoring.get('min_total_score_for_normal_bucketing') or 0
    )
    thresholds = scoring.get('thresholds') or {}
    th_material = float(thresholds.get('material') or 0.8)
    th_consider = float(thresholds.get('consider') or 0.4)
    universal_floor = set(scoring.get('universal_floor') or [])

    buckets: dict[int, str] = {}
    for cid in range(1, 16):
        score = scores.get(cid, 0.0)
        if score >= th_material:
            bucket = 'material'
        elif score >= th_consider:
            bucket = 'consider'
        else:
            bucket = 'skip'
        if promote_all and score > 0 and bucket == 'skip':
            bucket = 'consider'
        if cid in universal_floor and bucket == 'skip':
            bucket = 'consider'
        buckets[cid] = bucket

    derived = sorted(cid for cid, b in buckets.items() if b == 'material')

    return {
        'scores': scores,
        'buckets': buckets,
        'derivedCategories': derived,
    }


def default_categories_pre_materiality() -> list[int]:
    """Fallback whitelist for orgs that haven't yet completed materiality."""
    sc = get_scoring()
    return list(sc.get('default_categories_pre_materiality') or [1, 5, 6, 7])


def questions_version() -> int:
    return int(get_questions().get('version') or 1)
