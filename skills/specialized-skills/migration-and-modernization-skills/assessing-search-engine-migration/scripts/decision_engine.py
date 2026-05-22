"""Decision engine — Service-vs-Serverless and migration-path selection.

Pure-stdlib, deterministic, rule-based. Each rule is documented in
``references/target-decision-matrix.md`` and ``references/migration-paths.md``.

Usage::

    python3 decision_engine.py target --profile-json /tmp/profile.json
    python3 decision_engine.py path   --profile-json /tmp/profile.json

Both subcommands emit JSON with the chosen value, the runner-up, the rules
that fired (each with an ``evidence`` field), and a list of canonical AWS
Knowledge MCP queries the agent should run to cite the recommendation.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

from common import (
    Profile,
    emit,
    load_json,
)


@dataclass
class Rule:
    name: str
    matched: bool
    evidence: str = ""
    weight: int = 1


@dataclass
class DecisionResult:
    choice: str
    runner_up: str
    rules_fired: list[Rule] = field(default_factory=list)
    citations_required: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "choice": self.choice,
            "runner_up": self.runner_up,
            "rules_fired": [
                {"rule": r.name, "matched": r.matched, "evidence": r.evidence, "weight": r.weight}
                for r in self.rules_fired
            ],
            "citations_required": self.citations_required,
            "notes": self.notes,
        }


# --- Target decision (Service vs Serverless) ---------------------------------


def decide_target(p: Profile) -> DecisionResult:
    """Pick a target. See references/target-decision-matrix.md for the rules."""
    rules: list[Rule] = []

    blocking_plugins = {
        "opensearch-learning-to-rank",
        "ltr",
        "anomaly-detection",
        "alerting",
        "ml-commons-anomaly",
        "sigma",
    }
    user_plugins = set(p.plugins)
    plugin_blockers = sorted(user_plugins & blocking_plugins)
    rules.append(
        Rule(
            "blocker-serverless:custom-or-restricted-plugin",
            matched=bool(plugin_blockers),
            evidence=f"plugins_in_use ∩ blocked = {plugin_blockers}",
            weight=10,
        )
    )

    rules.append(
        Rule(
            "blocker-serverless:cross-cluster-replication",
            matched=p.has_ccr,
            evidence="source.uses_cross_cluster_replication is true",
            weight=10,
        )
    )

    rules.append(
        Rule(
            "blocker-serverless:govcloud-or-fedramp-high",
            matched=p.govcloud_or_fedramp,
            evidence=(
                "account_context.govcloud or fedramp_high — verify Serverless availability "
                "with AWS Knowledge MCP"
            ),
            weight=10,
        )
    )

    huge = p.total_data_size_gb >= 5_000  # 5 TB+
    rules.append(
        Rule(
            "soft-pref-service:huge-data-volume",
            matched=huge,
            evidence=f"total_data_size_gb={p.total_data_size_gb:.0f}",
            weight=3,
        )
    )

    steady = p.is_steady_load
    rules.append(
        Rule(
            "soft-pref-service:steady-load",
            matched=steady,
            evidence="load is steady (peak/steady ≤ 1.5 or load_pattern=steady)",
            weight=2,
        )
    )

    bursty = (not steady) and p.peak_query_rate > 0
    rules.append(
        Rule(
            "soft-pref-aoss:bursty-load",
            matched=bursty,
            evidence=(
                f"peak_query_rate={p.peak_query_rate}, "
                f"steady not asserted — favoring Serverless for unpredictable load"
            ),
            weight=2,
        )
    )

    is_time_series = p.update_pattern.lower() == "append_only" and p.retention_pattern.lower() in {
        "fixed",
        "sliding_window",
        "time_partitioned",
    }
    rules.append(
        Rule(
            "soft-pref-aoss:time-series-fit",
            matched=is_time_series,
            evidence=(
                f"update_pattern={p.update_pattern!r}, retention_pattern={p.retention_pattern!r}"
            ),
            weight=3,
        )
    )

    rules.append(
        Rule(
            "soft-pref-aoss:vector-workload",
            matched=p.vector_workload,
            evidence="source.vector_workload is true",
            weight=3,
        )
    )

    # Tally: any blocker rules out Serverless outright.
    blocked = any(r.matched for r in rules if r.name.startswith("blocker-serverless:"))

    service_score = sum(r.weight for r in rules if r.matched and r.name.startswith("soft-pref-service:"))
    aoss_score = sum(r.weight for r in rules if r.matched and r.name.startswith("soft-pref-aoss:"))

    if blocked:
        # Pick a Service flavor.
        if huge:
            choice = "service-large-scale"
        elif is_time_series:
            choice = "service-ultrawarm"
        else:
            choice = "service-general"
        runner_up = "aoss-search"  # documented but blocked
    else:
        if aoss_score > service_score:
            if p.vector_workload:
                choice = "aoss-vector"
            elif is_time_series:
                choice = "aoss-time-series"
            else:
                choice = "aoss-search"
            runner_up = "service-large-scale" if huge else "service-general"
        else:
            choice = "service-large-scale" if huge else ("service-ultrawarm" if is_time_series else "service-general")
            if p.vector_workload:
                runner_up = "aoss-vector"
            elif is_time_series:
                runner_up = "aoss-time-series"
            else:
                runner_up = "aoss-search"

    citations = [
        "AWS Knowledge MCP: Amazon OpenSearch Serverless supported features",
        "AWS Knowledge MCP: Amazon OpenSearch Service custom packages",
    ]
    if p.govcloud_or_fedramp:
        citations.append("AWS Knowledge MCP: Amazon OpenSearch Serverless GovCloud availability")
    if is_time_series:
        citations.append("AWS Knowledge MCP: Amazon OpenSearch Service UltraWarm cold tier")
    if p.vector_workload:
        citations.append("AWS Knowledge MCP: Amazon OpenSearch Serverless vector collection sizing")

    return DecisionResult(
        choice=choice,
        runner_up=runner_up,
        rules_fired=rules,
        citations_required=citations,
        notes=(
            ["Serverless ruled out by hard blocker — pick a Service flavor."]
            if blocked
            else []
        ),
    )


# --- Migration path decision -------------------------------------------------


def decide_path(p: Profile) -> DecisionResult:
    """Pick a migration path. See references/migration-paths.md for the rules."""
    rules: list[Rule] = []

    is_solr = p.source_engine == "solr"
    rules.append(
        Rule(
            "blocker-ma:source-is-solr",
            matched=is_solr,
            evidence="source_engine=solr — Migration Assistant does not yet apply",
            weight=10,
        )
    )

    is_es5_or_6 = p.source_engine == "elasticsearch" and p.source_version.startswith(("5.", "6."))
    rules.append(
        Rule(
            "blocker-snapshot:elasticsearch-5x-or-6x",
            matched=is_es5_or_6,
            evidence=f"source_version={p.source_version!r} not directly restorable on modern OpenSearch",
            weight=10,
        )
    )

    needs_continuous = bool(p.raw.get("migration", {}).get("continuous_replication"))
    rules.append(
        Rule(
            "soft-pref-osi:continuous-replication-required",
            matched=needs_continuous,
            evidence="migration.continuous_replication is true",
            weight=6,
        )
    )

    needs_transforms = bool(p.raw.get("migration", {}).get("requires_transformations"))
    rules.append(
        Rule(
            "soft-pref-osi:transformations-required",
            matched=needs_transforms,
            evidence="migration.requires_transformations is true",
            weight=3,
        )
    )

    very_small = p.total_data_size_gb > 0 and p.total_data_size_gb <= 500
    rules.append(
        Rule(
            "soft-pref-snapshot:small-and-simple",
            matched=very_small and not needs_transforms and not is_es5_or_6 and not is_solr,
            evidence=(
                f"total_data_size_gb={p.total_data_size_gb:.0f} ≤ 500 GB; "
                "no transforms; source supports snapshot restore"
            ),
            weight=3,
        )
    )

    big_backfill_or_strict = p.total_data_size_gb >= 1_000 or bool(
        p.raw.get("migration", {}).get("strict_cutover")
    )
    rules.append(
        Rule(
            "soft-pref-ma:big-backfill-or-strict-cutover",
            matched=big_backfill_or_strict and not is_solr,
            evidence="≥1 TB or strict cutover SLO requested",
            weight=3,
        )
    )

    # Score paths.
    score = {p_: 0 for p_ in ("migration-assistant", "snapshot-and-restore", "osi", "direct-from-source")}

    if is_solr:
        score["direct-from-source"] += 100
    else:
        # MA is the conservative default for ES/OS sources but should yield to a stronger soft-pref.
        score["migration-assistant"] += 1

    for r in rules:
        if not r.matched:
            continue
        if r.name == "blocker-snapshot:elasticsearch-5x-or-6x":
            score["snapshot-and-restore"] -= 100
        if r.name == "soft-pref-snapshot:small-and-simple":
            score["snapshot-and-restore"] += r.weight
        if r.name.startswith("soft-pref-osi:"):
            score["osi"] += r.weight
        if r.name == "soft-pref-ma:big-backfill-or-strict-cutover":
            score["migration-assistant"] += r.weight

    # Pick top two.
    ranked = sorted(score.items(), key=lambda kv: kv[1], reverse=True)
    choice = ranked[0][0]
    runner_up = ranked[1][0]

    citations = [
        "AWS Knowledge MCP: AWS Migration Assistant for OpenSearch supported source versions",
        "AWS Knowledge MCP: Amazon OpenSearch Ingestion supported sources",
        "AWS Knowledge MCP: Amazon OpenSearch Service snapshot restore",
    ]
    if is_solr:
        citations.append(
            "AWS Knowledge MCP: Amazon EMR Serverless pricing — Spark workloads"
        )

    notes: list[str] = []
    if is_solr:
        notes.append(
            "Solr sources are out of scope for Migration Assistant today. "
            "Default to direct-from-source via Spark on EMR. "
            "Pair with the upstream solr-opensearch-migration-advisor for schema/query work."
        )
    if needs_continuous and choice != "osi":
        notes.append("Continuous replication requested but not chosen as primary — pair OSI with the chosen path post-cutover.")

    return DecisionResult(
        choice=choice,
        runner_up=runner_up,
        rules_fired=rules,
        citations_required=citations,
        notes=notes,
    )


# --- CLI ---------------------------------------------------------------------


def _cli_target(args: argparse.Namespace) -> int:
    raw = load_json(args.profile_json)
    profile = Profile(raw)
    result = decide_target(profile)
    emit(result.to_dict())
    return 0


def _cli_path(args: argparse.Namespace) -> int:
    raw = load_json(args.profile_json)
    profile = Profile(raw)
    result = decide_path(profile)
    emit(result.to_dict())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="decision_engine", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_t = sub.add_parser("target", help="Decide target service (Service vs Serverless).")
    p_t.add_argument("--profile-json", required=True, help="Path to source profile JSON.")
    p_t.set_defaults(func=_cli_target)

    p_p = sub.add_parser("path", help="Decide migration path.")
    p_p.add_argument("--profile-json", required=True, help="Path to source profile JSON.")
    p_p.set_defaults(func=_cli_path)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
