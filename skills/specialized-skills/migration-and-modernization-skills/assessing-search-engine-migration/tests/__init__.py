"""Unit tests for the migration-assessment scripts.

Stdlib-only (unittest). Run from the skill root::

    python3 -m unittest discover tests

This package bootstrap adds ``../scripts`` to ``sys.path`` so test modules can
``import common`` etc. without packaging gymnastics.
"""
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
