"""Shared helpers for the migration-assessment scripts.

Stdlib-only. Anything that's used by more than one CLI lives here.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SUPPORTED_SOURCE_ENGINES = ("solr", "elasticsearch", "opensearch")
SUPPORTED_TARGETS = (
    "service-general",
    "service-large-scale",
    "service-ultrawarm",
    "aoss-search",
    "aoss-time-series",
    "aoss-vector",
)
SUPPORTED_PATHS = (
    "migration-assistant",
    "snapshot-and-restore",
    "osi",
    "direct-from-source",
)


# --- IO helpers --------------------------------------------------------------


def load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        die(f"file not found: {p}")
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        die(f"invalid JSON in {p}: {exc}")
    return {}  # unreachable; keeps mypy happy


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def die(msg: str, code: int = 2) -> "_NoReturn":  # type: ignore[name-defined]
    sys.stderr.write(f"error: {msg}\n")
    raise SystemExit(code)


# --- Profile types -----------------------------------------------------------


@dataclass
class Profile:
    """Validated source profile.

    ``raw`` holds the user-provided JSON; the rest are convenience accessors
    with defaults applied. Anything genuinely unknown stays ``None`` so the
    decision engine can flag it instead of silently substituting.
    """

    raw: dict[str, Any]

    @property
    def source_engine(self) -> str:
        v = (self.raw.get("intake", {}) or {}).get("source_engine", "")
        v = str(v).lower().strip()
        if v not in SUPPORTED_SOURCE_ENGINES:
            die(
                f"intake.source_engine must be one of {SUPPORTED_SOURCE_ENGINES}, got {v!r}"
            )
        return v

    @property
    def source_version(self) -> str:
        return str((self.raw.get("intake", {}) or {}).get("source_version") or "")

    @property
    def primary_goal(self) -> str:
        return str((self.raw.get("intake", {}) or {}).get("primary_goal") or "")

    @property
    def total_data_size_gb(self) -> float:
        return _f(self.raw.get("source", {}).get("total_data_size_gb"), 0.0)

    @property
    def total_doc_count(self) -> int:
        return int(_f(self.raw.get("source", {}).get("total_doc_count"), 0.0))

    @property
    def peak_indexing_rate(self) -> float:
        return _f(self.raw.get("source", {}).get("peak_indexing_rate_docs_s"), 0.0)

    @property
    def peak_query_rate(self) -> float:
        return _f(self.raw.get("source", {}).get("peak_query_rate_qps"), 0.0)

    @property
    def update_pattern(self) -> str:
        return str(self.raw.get("source", {}).get("update_pattern") or "")

    @property
    def retention_pattern(self) -> str:
        return str(self.raw.get("source", {}).get("retention_pattern") or "")

    @property
    def plugins(self) -> list[str]:
        v = self.raw.get("source", {}).get("plugins_in_use") or []
        return [str(p).lower() for p in v]

    @property
    def has_ccr(self) -> bool:
        return bool(self.raw.get("source", {}).get("uses_cross_cluster_replication"))

    @property
    def vector_workload(self) -> bool:
        return bool(self.raw.get("source", {}).get("vector_workload"))

    @property
    def region(self) -> str:
        return str(
            (self.raw.get("account_context", {}) or {}).get("region") or "us-east-1"
        )

    @property
    def govcloud_or_fedramp(self) -> bool:
        ac = self.raw.get("account_context", {}) or {}
        return bool(ac.get("govcloud") or ac.get("fedramp_high"))

    # Deterministic ranges -------------------------------------------------

    @property
    def is_steady_load(self) -> bool:
        # Heuristic: if the user explicitly says steady, trust them; else use
        # peak vs steady ratio when both are provided.
        src = self.raw.get("source", {})
        if "load_pattern" in src:
            return str(src["load_pattern"]).lower() == "steady"
        peak = self.peak_query_rate
        steady = _f(src.get("steady_query_rate_qps"), 0.0)
        if peak == 0.0 or steady == 0.0:
            return False
        return (peak / max(steady, 1e-9)) <= 1.5


def _f(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# --- Output helpers ----------------------------------------------------------


def emit(obj: dict[str, Any]) -> None:
    """Print a JSON result to stdout (stable key order)."""
    sys.stdout.write(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def usd(value: float) -> str:
    return f"${value:,.2f}"


# --- Sizing primitives -------------------------------------------------------


def primary_shards(total_data_size_gb: float, target_shard_size_gb: float) -> int:
    if target_shard_size_gb <= 0:
        return 0
    return max(1, math.ceil(total_data_size_gb / target_shard_size_gb))


def total_storage_gb(
    primary_data_gb: float,
    replicas: int,
    overhead_factor: float = 1.3,
    headroom_factor: float = 1.25,
) -> float:
    return primary_data_gb * (1 + replicas) * overhead_factor * headroom_factor


def data_node_count(
    primary_shards_count: int,
    total_storage_gb_value: float,
    shards_per_node_target: int = 25,
    per_node_storage_target_gb: float = 1500.0,
    azs: int = 3,
) -> int:
    by_shards = math.ceil(primary_shards_count / max(1, shards_per_node_target))
    by_storage = math.ceil(total_storage_gb_value / max(1.0, per_node_storage_target_gb))
    return max(by_shards, by_storage, azs)
