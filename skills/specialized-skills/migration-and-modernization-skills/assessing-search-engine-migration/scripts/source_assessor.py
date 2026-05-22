"""Profile validator and assessment-report renderer.

Stdlib-only. Subcommands::

    python3 source_assessor.py validate --profile-json profile.json
    python3 source_assessor.py report   --profile-json profile.json [--region us-east-1]

``validate`` checks that the source profile has the minimum fields the rest of
the toolkit needs. ``report`` chains the decision engine and the pricing
estimator and renders a Markdown assessment with citation slots that the agent
fills in by calling the AWS Knowledge MCP Server.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any

from common import (
    Profile,
    SUPPORTED_SOURCE_ENGINES,
    die,
    emit,
    load_json,
    usd,
)
from decision_engine import decide_path, decide_target
from pricing_estimator import (
    DISCLAIMER,
    _do_price,
    _do_size,
    _load_pricing,
    _stale_warning,
    price_migration_period,
)


REQUIRED_INTAKE = ("source_engine", "primary_goal")
RECOMMENDED_SOURCE = (
    "total_data_size_gb",
    "total_doc_count",
    "peak_indexing_rate_docs_s",
    "peak_query_rate_qps",
    "update_pattern",
    "retention_pattern",
)


def _validate_profile(raw: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    intake = raw.get("intake") or {}
    for k in REQUIRED_INTAKE:
        if not intake.get(k):
            errors.append(f"intake.{k} is required")
    eng = str(intake.get("source_engine", "")).lower()
    if eng and eng not in SUPPORTED_SOURCE_ENGINES:
        errors.append(
            f"intake.source_engine must be one of {SUPPORTED_SOURCE_ENGINES}, got {eng!r}"
        )

    source = raw.get("source") or {}
    for k in RECOMMENDED_SOURCE:
        if k not in source:
            warnings.append(f"source.{k} is missing — defaults will be applied")

    account = raw.get("account_context") or {}
    if not account.get("region"):
        warnings.append(
            "account_context.region missing — defaulting to us-east-1; cost estimates will reflect that"
        )

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def _cli_validate(args: argparse.Namespace) -> int:
    raw = load_json(args.profile_json)
    result = _validate_profile(raw)
    emit(result)
    return 0 if result["ok"] else 1


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    out = ["| " + " | ".join(headers) + " |"]
    out.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out)


def _render_report(profile: Profile, region: str) -> str:
    target = decide_target(profile)
    path = decide_path(profile)

    # Pre-fill the migration_path choice so pricing can include the migration period.
    profile.raw.setdefault("migration_path", {})["choice"] = path.choice

    primary_target = target.choice
    runner_up_target = target.runner_up

    primary_priced = _do_price(profile, primary_target, region)
    primary_sized = _do_size(profile, primary_target)

    try:
        runner_priced = _do_price(profile, runner_up_target, region)
        runner_sized = _do_size(profile, runner_up_target)
    except SystemExit:
        runner_priced = {"steady_state": {"monthly_mid_usd": "n/a"}}
        runner_sized = {"kind": "n/a"}

    pricing_meta = _load_pricing()
    stale = _stale_warning(pricing_meta)
    today = dt.date.today().isoformat()

    rules_table = _md_table(
        ["rule", "matched", "evidence"],
        [
            [r.name, "yes" if r.matched else "no", r.evidence or ""]
            for r in target.rules_fired
        ],
    )
    path_rules_table = _md_table(
        ["rule", "matched", "evidence"],
        [
            [r.name, "yes" if r.matched else "no", r.evidence or ""]
            for r in path.rules_fired
        ],
    )

    primary_low = primary_priced["steady_state"]["monthly_low_usd"]
    primary_mid = primary_priced["steady_state"]["monthly_mid_usd"]
    primary_high = primary_priced["steady_state"]["monthly_high_usd"]
    runner_mid = runner_priced["steady_state"].get("monthly_mid_usd", "n/a")

    migration_period = primary_priced.get("migration_period")

    citations = sorted({*target.citations_required, *path.citations_required})

    parts: list[str] = []
    parts.append(f"# Migration Assessment — {profile.source_engine.title()} → Amazon OpenSearch")
    parts.append("")
    parts.append(f"_Generated {today} for region `{region}`._")
    parts.append("")
    if stale:
        parts.append(f"> **{stale}**")
        parts.append("")

    parts.append("## Source profile")
    parts.append("")
    parts.append(_md_table(
        ["field", "value"],
        [
            ["source_engine", profile.source_engine],
            ["source_version", profile.source_version or "(unspecified)"],
            ["primary_goal", profile.primary_goal or "(unspecified)"],
            ["total_data_size_gb", f"{profile.total_data_size_gb:.0f}"],
            ["total_doc_count", f"{profile.total_doc_count:,}"],
            ["peak_indexing_rate_docs_s", f"{profile.peak_indexing_rate:.0f}"],
            ["peak_query_rate_qps", f"{profile.peak_query_rate:.0f}"],
            ["update_pattern", profile.update_pattern or "(unspecified)"],
            ["retention_pattern", profile.retention_pattern or "(unspecified)"],
            ["plugins_in_use", ", ".join(profile.plugins) or "(none)"],
            ["uses_cross_cluster_replication", str(profile.has_ccr)],
            ["vector_workload", str(profile.vector_workload)],
            ["region", profile.region],
        ],
    ))
    parts.append("")

    parts.append("## Recommended target")
    parts.append("")
    parts.append(f"**Primary:** `{primary_target}` — runner-up `{runner_up_target}`.")
    parts.append("")
    if target.notes:
        for n in target.notes:
            parts.append(f"- {n}")
        parts.append("")
    parts.append(rules_table)
    parts.append("")

    parts.append("## Recommended migration path")
    parts.append("")
    parts.append(f"**Primary:** `{path.choice}` — runner-up `{path.runner_up}`.")
    parts.append("")
    if path.notes:
        for n in path.notes:
            parts.append(f"- {n}")
        parts.append("")
    parts.append(path_rules_table)
    parts.append("")

    parts.append("## Sizing — primary target")
    parts.append("")
    parts.append("```json")
    import json as _json

    parts.append(_json.dumps(primary_sized, indent=2, sort_keys=True))
    parts.append("```")
    parts.append("")

    parts.append("## Pricing — primary target (steady state)")
    parts.append("")
    parts.append(
        f"- Monthly low / mid / high: **{usd(primary_low)} / {usd(primary_mid)} / {usd(primary_high)}**"
    )
    parts.append(f"- Pricing as of `{primary_priced['steady_state']['as_of']}`")
    parts.append(f"- Runner-up `{runner_up_target}` mid: **{usd(runner_mid) if isinstance(runner_mid, (int, float)) else runner_mid}**")
    parts.append("")
    parts.append("```json")
    parts.append(_json.dumps(primary_priced["steady_state"], indent=2, sort_keys=True))
    parts.append("```")
    parts.append("")

    if migration_period:
        parts.append("## Pricing — migration period (one-time)")
        parts.append("")
        parts.append(f"- Path: `{migration_period['path']}`")
        parts.append(f"- Days assumed: {migration_period['days_assumed']}")
        parts.append(
            f"- Compute: {usd(migration_period['compute_usd'])}, "
            f"snapshot S3: {usd(migration_period['snapshot_storage_usd'])}, "
            f"**total: {usd(migration_period['total_usd'])}**"
        )
        parts.append(f"- Notes: {migration_period['notes']}")
        parts.append("")

    parts.append("## Citations to fetch")
    parts.append("")
    parts.append("Run each query against the AWS Knowledge MCP Server (knowledge-mcp.global.api.aws)")
    parts.append("and inline the resulting URL + retrieved-on date next to the relevant claim.")
    parts.append("")
    for q in citations:
        parts.append(f"- {q}")
    parts.append("")

    parts.append("## Open questions and risks")
    parts.append("")
    parts.append("- Confirm that all source-side plugins/features have a documented OpenSearch equivalent or a documented workaround.")
    parts.append("- Confirm cutover SLO and rollback plan (DNS swap vs. dual-write vs. capture-and-replay validation).")
    parts.append("- Confirm regional availability of the chosen target with the AWS Knowledge MCP Server.")
    parts.append("- Confirm that recently-published OCU minimums and instance prices match `pricing_data.json`.")
    parts.append("")

    parts.append("## Disclaimer")
    parts.append("")
    parts.append("> " + DISCLAIMER.format(as_of=pricing_meta.get("as_of", "unknown")))
    parts.append("")

    return "\n".join(parts)


def _cli_report(args: argparse.Namespace) -> int:
    raw = load_json(args.profile_json)
    validation = _validate_profile(raw)
    if not validation["ok"]:
        sys.stderr.write("error: profile validation failed\n")
        for err in validation["errors"]:
            sys.stderr.write(f"  - {err}\n")
        return 1
    profile = Profile(raw)
    region = args.region or profile.region
    md = _render_report(profile, region)
    if args.out:
        Path(args.out).write_text(md)
        sys.stdout.write(f"wrote {args.out} ({len(md)} bytes)\n")
    else:
        sys.stdout.write(md)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="source_assessor", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_v = sub.add_parser("validate", help="Validate a source profile JSON.")
    p_v.add_argument("--profile-json", required=True)
    p_v.set_defaults(func=_cli_validate)

    p_r = sub.add_parser("report", help="Render a full assessment report (Markdown).")
    p_r.add_argument("--profile-json", required=True)
    p_r.add_argument("--region")
    p_r.add_argument("--out", help="Write to a file instead of stdout.")
    p_r.set_defaults(func=_cli_report)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
