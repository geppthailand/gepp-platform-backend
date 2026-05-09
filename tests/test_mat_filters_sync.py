"""
Guard test: mat_filters YAMLs in the backend bundle must stay byte-equal
to the frontend tree.

The frontend (React) loads from
  v3/frontend/gepp-esg/src/mat_filters/*.yaml
The backend Lambda has no access to the frontend dir at runtime, so
materiality_config._load_yaml() reads from
  v3/backend/GEPPPlatform/assets/mat_filters/*.yaml
which must be a verbatim copy.

If this test fails after editing a frontend YAML, copy the file into
the backend assets dir and re-run.
"""

from __future__ import annotations

from pathlib import Path

import pytest


_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[3]  # …/platforms
_FE = _REPO_ROOT / 'v3' / 'frontend' / 'gepp-esg' / 'src' / 'mat_filters'
_BE = _REPO_ROOT / 'v3' / 'backend' / 'GEPPPlatform' / 'assets' / 'mat_filters'


@pytest.mark.parametrize('name', ['questions', 'industries', 'categories', 'scoring'])
def test_mat_filters_yaml_byte_equal(name: str) -> None:
    fe = _FE / f'{name}.yaml'
    be = _BE / f'{name}.yaml'
    assert fe.exists(), f'frontend YAML missing: {fe}'
    assert be.exists(), (
        f'backend bundled YAML missing: {be}. '
        f'Copy {fe} → {be} so the Lambda artifact has it.'
    )
    fe_bytes = fe.read_bytes()
    be_bytes = be.read_bytes()
    assert fe_bytes == be_bytes, (
        f'{name}.yaml drift between frontend and backend bundle. '
        f'Run: cp {fe} {be}'
    )
