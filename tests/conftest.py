"""Shared pytest configuration for FinSentinelAI.

IMPORTANT: this module sets hermetic environment variables at *import time*,
before any application module is imported. ``config.get_settings()`` is
``lru_cache``-wrapped and several API modules bind database connections at
module import (e.g. ``api/routes/auth.py``), so the data directory must be
redirected before the first import of anything under ``api/``, ``core/``,
``database/`` or ``security/``.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Hermetic environment (must run before app imports -- see docstring).
# ---------------------------------------------------------------------------
_TEST_ROOT = Path(tempfile.mkdtemp(prefix="finsentinel-tests-"))
_DATA_DIR = _TEST_ROOT / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

os.environ["FINSENTINEL_DATA_DIR"] = str(_DATA_DIR)
os.environ["FINSENTINEL_DB_PATH"] = str(_DATA_DIR / "test-finsentinel.db")
# Keep JWT lifetimes predictable across the session; expiry behaviour is
# exercised explicitly in test_security.py.
os.environ.setdefault("FINSENTINEL_TOKEN_EXPIRY_MINUTES", "60")

from tests.harness_support import REPORT  # noqa: E402

_REPORT_PATH = Path(__file__).resolve().parent / "_isolation_report.json"


def pytest_sessionfinish(session: Any, exitstatus: Any) -> None:
    """Persist the isolation-harness measurements collected during the run.

    The resulting JSON file is the raw material for the paper's before/after
    results table (see tests/test_isolation.py RUNBOOK).
    """
    payload = {
        "data_dir": str(_DATA_DIR),
        "measurements": REPORT["measurements"],
        "prompt_audit": REPORT["prompt_audit"],
    }
    try:
        _REPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        # Never fail the suite because reporting failed.
        pass
