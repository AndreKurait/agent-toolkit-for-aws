"""Pricing & sizing estimator.

Stdlib-only. Reads ``scripts/pricing_data.json`` for list prices.

Subcommands::

    python3 pricing_estimator.py size  --profile-json profile.json --target service-general
    python3 pricing_estimator.py price --profile-json profile.json --target service-general --region us-east-1
    python3 pricing_estimator.py both  --profile-json profile.json --target service-general

``both`` is the convenience used in Phase 5 + 6 of the skill workflow.

Output is JSON. Every numeric output carries assumptions and the pricing-data
``as_of`` date. See ``references/sizing.md`` and ``references/pricing-data.md``.
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common import (
    Profile,
    SUPPORTED_TARGETS,
    data_node_count,
    die,
    emit,
    load_json,
    primary_shards,
    total_storage_gb,
    usd,
)

PRICING_PATH = Path(__file__).with_name("pricing_data.json")
HOURS_PER_MONTH = 730  # AWS billing convention.
STALE_DAYS = 90

DISCLAIMER = (
    "Pricing disclaimer. Estimates use AWS list prices snapshot as of {as_of}. "
    "Actual cost depends on Reserved Instances, Savings Plans, EDP discounts, "
    "free-tier credits, AWS Marketplace add-ons, and your AWS account's billing region. "
    "Validate with the AWS Pricing Calculator (https://calculator.aws) and, if available, "
    "the AWS MCP Server's pricing.get_products API before commitment. "
    "This estimate is not a quote."
)


# --- Sizing ------------------------------------------------------------------


@dataclass
class ServiceSizing:
    primary_shards: int
    replicas: int
    total_storage_gb: float
    data_node_count: int
    data_node_instance: str
    cluster_manager_count: int
    cluster_manager_instance: str
    coordinator_count: int
    coordinator_instance: str
    azs: int
    notes: list[str] = field(default_factory=list)


@dataclass
class ServerlessSizing:
    indexing_ocus_steady: float
    indexing_ocus_peak: float
    search_ocus_steady: float
    search_ocus_peak: float
    managed_storage_gb: float
    collection_type: str
    notes: list[str] = field(default_factory=list)


def _select_data_instance(p: Profile) -> str:
    """Heuristic: pick a Graviton instance class from the source profile."""
    if p.vector_workload:
        return "r6g.xlarge.search"
    size = p.total_data_size_gb
    if size <= 100:
        return "m6g.large.search"
    if size <= 1_000:
        return "m6g.xlarge.search"
    if size <= 5_000:
        return "m6g.2xlarge.search"
    return "m6g.4xlarge.search"


def size_service(p: Profile, target: str) -> ServiceSizing:
    target_shard_size = 30.0 if "time-series" not in target and "ultrawarm" not in target else 45.0
    replicas = 1
    azs = 3
    shards = primary_shards(p.total_data_size_gb, target_shard_size)
    storage = total_storage_gb(p.total_data_size_gb, replicas)
    data_inst = _select_data_instance(p)
    nodes = data_node_count(shards, storage, azs=azs)
    notes: list[str] = []
    if p.total_data_size_gb == 0:
        notes.append(
            "WARN total_data_size_gb=0 — sizing is the production minimum, not a tailored fit."
        )
        nodes = max(nodes, azs)
        storage = 100.0
    if "ultrawarm" in target:
        notes.append(
            "Time-series tier: hot data on m6g, warm on ultrawarm1.medium.search, cold on S3 (managed)."
        )
    return ServiceSizing(
        primary_shards=shards,
        replicas=replicas,
        total_storage_gb=round(storage, 1),
        data_node_count=nodes,
        data_node_instance=data_inst,
        cluster_manager_count=3,
        cluster_manager_instance="m6g.large.search",
        coordinator_count=2 if p.peak_query_rate > 500 else 0,
        coordinator_instance="c6g.xlarge.search",
        azs=azs,
        notes=notes,
    )


def size_serverless(p: Profile, target: str) -> ServerlessSizing:
    # Indexing OCUs: ~1 GB/min sustained per OCU.
    avg_doc_kb = 2.0  # default; report disclosure handles this.
    if p.total_doc_count > 0 and p.total_data_size_gb > 0:
        avg_doc_kb = max(0.1, (p.total_data_size_gb * 1024 * 1024) / p.total_doc_count)
    indexing_steady = max(
        2.0,  # production HA minimum
        math.ceil((p.peak_indexing_rate * avg_doc_kb / 1024) / 60),  # GB/min headroom
    )
    indexing_peak = indexing_steady * 1.5

    # Search OCUs: ~4k QPS simple per OCU baseline.
    search_steady = max(2.0, math.ceil(max(p.peak_query_rate, 1) / 4000))
    search_peak = search_steady * 1.5

    # Managed storage: assume 1.3x source data primary copy.
    storage = max(p.total_data_size_gb, 1.0) * 1.3

    collection_type = "search"
    if target == "aoss-time-series":
        collection_type = "time-series"
    elif target == "aoss-vector":
        collection_type = "vector"

    notes: list[str] = []
    if p.total_data_size_gb == 0:
        notes.append("WARN total_data_size_gb=0 — using the 1 GB / 4 OCU production minimum.")
    notes.append(
        f"Assumed average document size {avg_doc_kb:.1f} KB; restate after a pilot measurement."
    )
    notes.append(
        "Verify current AOSS OCU minimums and OCU throughput per workload type via AWS Knowledge MCP."
    )

    return ServerlessSizing(
        indexing_ocus_steady=indexing_steady,
        indexing_ocus_peak=indexing_peak,
        search_ocus_steady=search_steady,
        search_ocus_peak=search_peak,
        managed_storage_gb=round(storage, 1),
        collection_type=collection_type,
        notes=notes,
    )


# --- Pricing -----------------------------------------------------------------


def _load_pricing() -> dict[str, Any]:
    return load_json(PRICING_PATH)


def _stale_warning(pricing: dict[str, Any]) -> str | None:
    try:
        as_of = dt.date.fromisoformat(pricing["as_of"])
    except Exception:
        return "WARN pricing_data.json missing or malformed as_of date."
    age_days = (dt.date.today() - as_of).days
    if age_days > STALE_DAYS:
        return (
            f"WARN pricing data is {age_days} days old (>{STALE_DAYS}); refresh per "
            "references/pricing-data.md before relying on these numbers."
        )
    return None


def _region_table(pricing: dict[str, Any], section: str, region: str) -> dict[str, Any]:
    table = pricing.get(section, {})
    if region in table:
        return table[region]
    return table.get("us-east-1", {})


def price_service(p: Profile, sizing: ServiceSizing, region: str) -> dict[str, Any]:
    pricing = _load_pricing()
    region_table = _region_table(pricing, "service", region)
    fallback = region not in pricing.get("service", {})

    inst_rate = region_table.get(sizing.data_node_instance, {}).get("usd_per_hour")
    if inst_rate is None:
        die(f"no list price for {sizing.data_node_instance} in {region}")

    cm_rate = region_table.get(sizing.cluster_manager_instance, {}).get("usd_per_hour", 0.0)
    coord_rate = region_table.get(sizing.coordinator_instance, {}).get("usd_per_hour", 0.0)
    ebs_rate = float(region_table.get("ebs_gp3_per_gb_month", 0.122))

    compute_hours = HOURS_PER_MONTH * (
        sizing.data_node_count * inst_rate
        + sizing.cluster_manager_count * cm_rate
        + sizing.coordinator_count * coord_rate
    )
    storage = sizing.total_storage_gb * ebs_rate

    cross_az_per_gb = float(_region_table(pricing, "data_transfer", region).get("cross_az_per_gb", 0.01))
    # Assume ingest doc size ≈ 2 KB; the user can override later.
    ingest_gb_month = max(0.0, p.peak_indexing_rate) * 2.0 / 1024.0 * 60 * 60 * HOURS_PER_MONTH * 0.001
    transfer = ingest_gb_month * cross_az_per_gb

    mid = compute_hours + storage + transfer
    low = mid * 0.85   # documented variability around list price.
    high = mid * 1.20

    return {
        "target": "service",
        "monthly_low_usd": round(low, 2),
        "monthly_mid_usd": round(mid, 2),
        "monthly_high_usd": round(high, 2),
        "components": {
            "compute_usd": round(compute_hours, 2),
            "storage_usd": round(storage, 2),
            "data_transfer_usd": round(transfer, 2),
        },
        "instance_breakdown": {
            "data_nodes": f"{sizing.data_node_count} x {sizing.data_node_instance}",
            "cluster_manager": f"{sizing.cluster_manager_count} x {sizing.cluster_manager_instance}",
            "coordinators": (
                f"{sizing.coordinator_count} x {sizing.coordinator_instance}"
                if sizing.coordinator_count
                else "none"
            ),
        },
        "region": region,
        "region_fallback_used": fallback,
        "as_of": pricing.get("as_of"),
    }


def price_serverless(p: Profile, sizing: ServerlessSizing, region: str) -> dict[str, Any]:
    pricing = _load_pricing()
    region_table = _region_table(pricing, "serverless", region)
    fallback = region not in pricing.get("serverless", {})

    ocu_rate = float(region_table.get("ocu_per_hour", 0.24))
    storage_rate = float(region_table.get("managed_storage_per_gb_month", 0.024))

    steady_ocus = sizing.indexing_ocus_steady + sizing.search_ocus_steady
    peak_ocus = sizing.indexing_ocus_peak + sizing.search_ocus_peak
    # Mid: 70% of hours at steady, 30% at peak.
    avg_ocus_mid = steady_ocus * 0.7 + peak_ocus * 0.3
    avg_ocus_low = steady_ocus
    avg_ocus_high = peak_ocus

    compute_low = avg_ocus_low * ocu_rate * HOURS_PER_MONTH
    compute_mid = avg_ocus_mid * ocu_rate * HOURS_PER_MONTH
    compute_high = avg_ocus_high * ocu_rate * HOURS_PER_MONTH

    storage = sizing.managed_storage_gb * storage_rate

    return {
        "target": "serverless",
        "monthly_low_usd": round(compute_low + storage, 2),
        "monthly_mid_usd": round(compute_mid + storage, 2),
        "monthly_high_usd": round(compute_high + storage, 2),
        "components": {
            "compute_low_usd": round(compute_low, 2),
            "compute_mid_usd": round(compute_mid, 2),
            "compute_high_usd": round(compute_high, 2),
            "storage_usd": round(storage, 2),
        },
        "ocu_breakdown": {
            "indexing_steady": sizing.indexing_ocus_steady,
            "indexing_peak": sizing.indexing_ocus_peak,
            "search_steady": sizing.search_ocus_steady,
            "search_peak": sizing.search_ocus_peak,
            "collection_type": sizing.collection_type,
        },
        "region": region,
        "region_fallback_used": fallback,
        "as_of": pricing.get("as_of"),
    }


def price_migration_period(p: Profile, path: str, region: str) -> dict[str, Any]:
    """Cheap, defensible bound on migration-period costs."""
    pricing = _load_pricing()
    days = float(p.raw.get("migration", {}).get("backfill_days", 7))
    s3_table = _region_table(pricing, "s3", region)
    s3_rate = float(s3_table.get("standard_per_gb_month_first_50tb", 0.023))
    snapshot_storage = p.total_data_size_gb * s3_rate * (days / 30.0)

    if path == "snapshot-and-restore":
        compute = 0.0
        notes = "Restore happens on the target domain; migration-period compute is the existing target."
    elif path == "migration-assistant":
        # Assume 1 m6g.xlarge.search worth of EKS/ECS infra per TB-day, capped reasonable.
        m6g_rate = float(_region_table(pricing, "service", region).get("m6g.xlarge.search", {}).get("usd_per_hour", 0.334))
        ma_nodes = max(1, math.ceil(p.total_data_size_gb / 1000.0))
        compute = ma_nodes * m6g_rate * 24 * days
        notes = (
            f"MA infra approximated as {ma_nodes} x m6g.xlarge.search-equivalent for {days:.0f} days. "
            "Real MA costs depend on RFS worker count and capture-and-replay duration."
        )
    elif path == "osi":
        ocu_rate = float(_region_table(pricing, "osi", region).get("ocu_per_hour", 0.24))
        ocus = max(1, math.ceil(p.total_data_size_gb / 1000.0))
        compute = ocus * ocu_rate * 24 * days
        notes = f"OSI approximated as {ocus} OCU for {days:.0f} days; tune by source throughput."
    elif path == "direct-from-source":
        emr = _region_table(pricing, "emr", region)
        vcpu_rate = float(emr.get("emr_serverless_vcpu_hour", 0.052624))
        mem_rate = float(emr.get("emr_serverless_memory_gb_hour", 0.0057785))
        # 16 vCPU, 64 GB mem per worker; 1 worker per TB.
        workers = max(1, math.ceil(p.total_data_size_gb / 1000.0))
        compute = (workers * 16 * vcpu_rate + workers * 64 * mem_rate) * 24 * days
        notes = f"EMR Serverless approximated as {workers} workers x 16 vCPU x 64 GB for {days:.0f} days."
    else:
        compute = 0.0
        notes = "Unknown path; migration-period compute not estimated."

    total = compute + snapshot_storage
    return {
        "path": path,
        "days_assumed": days,
        "compute_usd": round(compute, 2),
        "snapshot_storage_usd": round(snapshot_storage, 2),
        "total_usd": round(total, 2),
        "notes": notes,
        "region": region,
    }


# --- CLI ---------------------------------------------------------------------


def _validate_target(target: str) -> None:
    if target not in SUPPORTED_TARGETS:
        die(f"--target must be one of {SUPPORTED_TARGETS}, got {target!r}")


def _do_size(profile: Profile, target: str) -> dict[str, Any]:
    if target.startswith("service-"):
        s = size_service(profile, target)
        return {"kind": "service", **s.__dict__}
    if target.startswith("aoss-"):
        s = size_serverless(profile, target)
        return {"kind": "serverless", **s.__dict__}
    die(f"unsupported target {target}")
    return {}


def _do_price(profile: Profile, target: str, region: str) -> dict[str, Any]:
    if target.startswith("service-"):
        sizing = size_service(profile, target)
        priced = price_service(profile, sizing, region)
    else:
        sizing = size_serverless(profile, target)
        priced = price_serverless(profile, sizing, region)

    pricing = _load_pricing()
    stale = _stale_warning(pricing)
    out: dict[str, Any] = {"steady_state": priced}
    out["disclaimer"] = DISCLAIMER.format(as_of=pricing.get("as_of", "unknown"))
    if stale:
        out["stale_warning"] = stale

    path = (profile.raw.get("migration_path") or {}).get("choice")
    if isinstance(path, str) and path:
        out["migration_period"] = price_migration_period(profile, path, region)
    return out


def _cli_size(args: argparse.Namespace) -> int:
    raw = load_json(args.profile_json)
    profile = Profile(raw)
    _validate_target(args.target)
    emit(_do_size(profile, args.target))
    return 0


def _cli_price(args: argparse.Namespace) -> int:
    raw = load_json(args.profile_json)
    profile = Profile(raw)
    _validate_target(args.target)
    region = args.region or profile.region
    emit(_do_price(profile, args.target, region))
    return 0


def _cli_both(args: argparse.Namespace) -> int:
    raw = load_json(args.profile_json)
    profile = Profile(raw)
    _validate_target(args.target)
    region = args.region or profile.region
    emit({
        "sizing": _do_size(profile, args.target),
        "pricing": _do_price(profile, args.target, region),
    })
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pricing_estimator", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_s = sub.add_parser("size", help="Compute sizing for a target.")
    p_s.add_argument("--profile-json", required=True)
    p_s.add_argument("--target", required=True, choices=SUPPORTED_TARGETS)
    p_s.set_defaults(func=_cli_size)

    p_p = sub.add_parser("price", help="Compute monthly cost estimate.")
    p_p.add_argument("--profile-json", required=True)
    p_p.add_argument("--target", required=True, choices=SUPPORTED_TARGETS)
    p_p.add_argument("--region")
    p_p.set_defaults(func=_cli_price)

    p_b = sub.add_parser("both", help="Compute sizing + cost in one call.")
    p_b.add_argument("--profile-json", required=True)
    p_b.add_argument("--target", required=True, choices=SUPPORTED_TARGETS)
    p_b.add_argument("--region")
    p_b.set_defaults(func=_cli_both)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
