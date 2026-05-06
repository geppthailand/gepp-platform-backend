"""
Materiality scoring parity test (backend half).

Loads the shared fixture file and asserts the Python scoring engine
produces the expected derivedCategories for every row. The frontend
(scoring.ts) loads the same fixtures via its own test (mirror of this
file) — keeping them in sync prevents drift.

Run:
    cd v3/backend
    python -m pytest tests/test_materiality_scoring_parity.py -v
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]  # repo root
FIXTURES = (
    REPO
    / 'v3'
    / 'frontend'
    / 'gepp-esg'
    / 'src'
    / 'mat_filters'
    / '__tests__'
    / 'scoring_fixtures.json'
)
MC_PATH = (
    REPO
    / 'v3'
    / 'backend'
    / 'GEPPPlatform'
    / 'services'
    / 'esg'
    / 'materiality_config.py'
)


def _load_mc():
    spec = importlib.util.spec_from_file_location('materiality_config', MC_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_scoring_fixtures_parity() -> None:
    mc = _load_mc()
    data = json.loads(FIXTURES.read_text(encoding='utf-8'))
    failures: list[str] = []
    for fixture in data['fixtures']:
        result = mc.compute_scores(fixture['answers'])
        actual = result['derivedCategories']
        expected = fixture['expectedDerivedCategories']
        if actual != expected:
            failures.append(
                f"{fixture['name']}: expected={expected} actual={actual} "
                f"scores={result['scores']}"
            )
    assert not failures, '\n'.join(failures)
