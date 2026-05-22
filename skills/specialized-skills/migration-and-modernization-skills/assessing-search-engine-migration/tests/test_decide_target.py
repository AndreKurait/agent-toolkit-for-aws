"""Tests for decision_engine.decide_target."""
from __future__ import annotations

import sys as _sys
import unittest
from pathlib import Path as _Path

_SCRIPTS = _Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS))

from common import Profile
from decision_engine import decide_target


def _profile(**source: object) -> Profile:
    raw = {
        "intake": {"source_engine": "elasticsearch", "primary_goal": "test"},
        "source": dict(source),
        "account_context": {"region": "us-east-1"},
    }
    return Profile(raw)


class TestDecideTarget(unittest.TestCase):
    def test_serverless_blocked_by_ccr(self) -> None:
        p = _profile(uses_cross_cluster_replication=True)
        result = decide_target(p)
        self.assertTrue(result.choice.startswith("service-"))
        blocker_rules = [
            r for r in result.rules_fired
            if r.name == "blocker-serverless:cross-cluster-replication" and r.matched
        ]
        self.assertEqual(len(blocker_rules), 1)

    def test_serverless_blocked_by_blocked_plugin(self) -> None:
        p = _profile(plugins_in_use=["opensearch-learning-to-rank"])
        result = decide_target(p)
        self.assertTrue(result.choice.startswith("service-"))
        self.assertIn(
            "blocker-serverless:custom-or-restricted-plugin",
            [r.name for r in result.rules_fired if r.matched],
        )

    def test_serverless_blocked_by_govcloud(self) -> None:
        raw = {
            "intake": {"source_engine": "elasticsearch", "primary_goal": "test"},
            "source": {},
            "account_context": {"region": "us-gov-west-1", "govcloud": True},
        }
        result = decide_target(Profile(raw))
        self.assertTrue(result.choice.startswith("service-"))

    def test_time_series_picks_aoss_time_series(self) -> None:
        p = _profile(
            update_pattern="append_only",
            retention_pattern="sliding_window",
            total_data_size_gb=1000,
        )
        result = decide_target(p)
        self.assertEqual(result.choice, "aoss-time-series")

    def test_vector_workload_picks_vector_collection(self) -> None:
        p = _profile(
            vector_workload=True,
            total_data_size_gb=200,
            peak_query_rate_qps=200,
        )
        result = decide_target(p)
        self.assertEqual(result.choice, "aoss-vector")

    def test_huge_steady_workload_prefers_service_large_scale(self) -> None:
        p = _profile(
            total_data_size_gb=20_000,
            peak_query_rate_qps=1000,
            steady_query_rate_qps=950,
            load_pattern="steady",
        )
        result = decide_target(p)
        self.assertEqual(result.choice, "service-large-scale")

    def test_citations_always_present(self) -> None:
        p = _profile(total_data_size_gb=100)
        result = decide_target(p)
        self.assertGreater(len(result.citations_required), 0)


if __name__ == "__main__":
    unittest.main()
