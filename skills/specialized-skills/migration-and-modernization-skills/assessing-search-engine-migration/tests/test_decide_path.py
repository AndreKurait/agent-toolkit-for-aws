"""Tests for decision_engine.decide_path."""
from __future__ import annotations

import sys as _sys
import unittest
from pathlib import Path as _Path

_SCRIPTS = _Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS))

from common import Profile
from decision_engine import decide_path


def _profile(*, source_engine: str = "elasticsearch", source_version: str = "7.10", **kwargs: object) -> Profile:
    source = kwargs.pop("source", {}) or {}
    migration = kwargs.pop("migration", {}) or {}
    raw = {
        "intake": {
            "source_engine": source_engine,
            "source_version": source_version,
            "primary_goal": "test",
        },
        "source": source,
        "migration": migration,
        "account_context": {"region": "us-east-1"},
    }
    return Profile(raw)


class TestDecidePath(unittest.TestCase):
    def test_solr_routes_to_direct_from_source(self) -> None:
        p = _profile(source_engine="solr", source_version="9.5", source={"total_data_size_gb": 2000})
        result = decide_path(p)
        self.assertEqual(result.choice, "direct-from-source")

    def test_es5_blocks_snapshot_restore(self) -> None:
        p = _profile(source_version="5.6", source={"total_data_size_gb": 200})
        result = decide_path(p)
        self.assertNotEqual(result.choice, "snapshot-and-restore")

    def test_small_simple_es_chooses_snapshot(self) -> None:
        p = _profile(
            source_version="7.10",
            source={"total_data_size_gb": 200},
            migration={"requires_transformations": False, "continuous_replication": False},
        )
        result = decide_path(p)
        self.assertEqual(result.choice, "snapshot-and-restore")

    def test_continuous_replication_chooses_osi(self) -> None:
        p = _profile(
            source_version="7.10",
            source={"total_data_size_gb": 2000},
            migration={"continuous_replication": True},
        )
        result = decide_path(p)
        self.assertEqual(result.choice, "osi")

    def test_big_strict_cutover_chooses_migration_assistant(self) -> None:
        p = _profile(
            source_version="7.10",
            source={"total_data_size_gb": 5000},
            migration={"strict_cutover": True},
        )
        result = decide_path(p)
        self.assertEqual(result.choice, "migration-assistant")

    def test_runner_up_is_different_from_choice(self) -> None:
        p = _profile(
            source_version="7.10",
            source={"total_data_size_gb": 2000},
            migration={"strict_cutover": True},
        )
        result = decide_path(p)
        self.assertNotEqual(result.choice, result.runner_up)


if __name__ == "__main__":
    unittest.main()
