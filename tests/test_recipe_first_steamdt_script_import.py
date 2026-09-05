"""Phase 16G-R2 — Script import regression test.

The actual Phase 16G live validation script
``scripts.run_live_recipe_first_steamdt_validation`` MUST be importable
without raising. A pre-live commit shipped a wrong import path
(``PinnedSkinMetadataResolver`` was imported from the wrong module),
which caused the script to crash with ``ImportError`` before any
prepare/execute work could happen.

This test imports the actual script module via ``importlib`` and asserts
that it loads cleanly. It performs zero network I/O, does not require
``STEAMDT_API_KEY``, does not read ``.env``, and does not call
``prepare_case`` / ``execute_case``.

If this test ever fails, the script is broken at import time and the
harness cannot reach any code path.
"""

from __future__ import annotations

import importlib


def test_phase16g_script_imports_cleanly_without_network() -> None:
    """Importing the actual Phase 16G script module must succeed."""

    module = importlib.import_module(
        "scripts.run_live_recipe_first_steamdt_validation"
    )
    assert module is not None
    assert hasattr(module, "prepare_case")
    assert hasattr(module, "execute_case")
    assert hasattr(module, "_load_case")
    assert hasattr(module, "_serialize_result")


def test_phase16g_script_constants_are_pinned() -> None:
    """Phase 16G script constants must match the frozen caps."""

    from scripts import run_live_recipe_first_steamdt_validation as script

    assert script.RUN_GATE_ENV == "RECIPE_FIRST_RUN_PHASE16G_LIVE_VALIDATION"
    assert script.API_KEY_ENV == "STEAMDT_API_KEY"
    assert script.CASE_FILENAME == "phase16g_case.json"
    assert script.RESULT_FILENAME == "phase16g_result.json"
    assert script._MAX_PRESCREEN_NAMES == 10