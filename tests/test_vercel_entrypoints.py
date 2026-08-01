"""Regression checks for source-layout imports in Vercel functions."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("entrypoint", ["api/quotes.py", "api/analyze.py", "api/v1.py"])
def test_vercel_entrypoint_imports_without_repo_pythonpath(
    entrypoint: str, tmp_path: Path
) -> None:
    """Vercel executes function files without installing the local package."""
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, str(ROOT / entrypoint)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
