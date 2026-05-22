"""Tests for pricing_estimator: sizing and pricing math."""
from __future__ import annotations

import sys as _sys
import unittest
from pathlib import Path as _Path

_SCRIPTS = _Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS))

from common import Profile
from pricing_estimator import (
    price_serverless,
    price_service,
    size_serverless,
    size_service,
)


def _profile(total_gb: float = 1000, qps: float = 500, ingest: float = 200) -> Profile:
    return Profile({
        "intake": {"source_engine": "elasticsearch", "primary_goal": "test"},
        "source": {
            "total_data_size_gb": total_gb,
            "total_doc_count": 50_000_000,
            "peak_query_rate_qps": qps,
            "peak_indexing_rate_docs_s": ingest,
        },
        "account_context": {"region": "us-east-1"},
    })


class TestSizeService(unittest.TestCase):
    def test_minimum_three_data_nodes(self) -> None:
        s = size_service(_profile(total_gb=10), "service-general")
        self.assertGreaterEqual(s.data_node_count, 3)

    def test_three_cluster_managers_always(self) -> None:
        s = size_service(_profile(total_gb=10), "service-general")
        self.assertEqual(s.cluster_manager_count, 3)

    def test_storage_includes_replica_and_overhead(self) -> None:
        s = size_service(_profile(total_gb=1000), "service-general")
        # 1000 * 2 * 1.3 * 1.25 = 3250
        self.assertAlmostEqual(s.total_storage_gb, 3250.0, places=1)

    def test_target_shard_size_30gb(self) -> None:
        s = size_service(_profile(total_gb=900), "service-general")
        self.assertEqual(s.primary_shards, 30)

    def test_time_series_uses_45gb_shards(self) -> None:
        s = size_service(_profile(total_gb=900), "service-ultrawarm")
        self.assertEqual(s.primary_shards, 20)


class TestSizeServerless(unittest.TestCase):
    def test_minimum_two_indexing_two_search_ocus(self) -> None:
        s = size_serverless(_profile(total_gb=10, qps=10, ingest=10), "aoss-search")
        self.assertGreaterEqual(s.indexing_ocus_steady, 2)
        self.assertGreaterEqual(s.search_ocus_steady, 2)

    def test_collection_type_propagates(self) -> None:
        self.assertEqual(size_serverless(_profile(), "aoss-search").collection_type, "search")
        self.assertEqual(size_serverless(_profile(), "aoss-time-series").collection_type, "time-series")
        self.assertEqual(size_serverless(_profile(), "aoss-vector").collection_type, "vector")


class TestPriceService(unittest.TestCase):
    def test_returns_low_mid_high(self) -> None:
        p = _profile(total_gb=1000)
        sizing = size_service(p, "service-general")
        priced = price_service(p, sizing, "us-east-1")
        self.assertIn("monthly_low_usd", priced)
        self.assertIn("monthly_mid_usd", priced)
        self.assertIn("monthly_high_usd", priced)
        self.assertLess(priced["monthly_low_usd"], priced["monthly_mid_usd"])
        self.assertLess(priced["monthly_mid_usd"], priced["monthly_high_usd"])

    def test_unknown_region_falls_back(self) -> None:
        p = _profile(total_gb=1000)
        sizing = size_service(p, "service-general")
        priced = price_service(p, sizing, "ap-mars-1")
        self.assertTrue(priced["region_fallback_used"])


class TestPriceServerless(unittest.TestCase):
    def test_returns_low_mid_high(self) -> None:
        p = _profile(total_gb=1000)
        sizing = size_serverless(p, "aoss-search")
        priced = price_serverless(p, sizing, "us-east-1")
        self.assertIn("monthly_low_usd", priced)
        self.assertIn("monthly_mid_usd", priced)
        self.assertIn("monthly_high_usd", priced)
        self.assertLessEqual(priced["monthly_low_usd"], priced["monthly_mid_usd"])
        self.assertLessEqual(priced["monthly_mid_usd"], priced["monthly_high_usd"])


if __name__ == "__main__":
    unittest.main()
