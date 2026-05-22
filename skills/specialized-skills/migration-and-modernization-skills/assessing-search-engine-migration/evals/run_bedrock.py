#!/usr/bin/env python3
"""Bedrock-native eval harness for the assessing-search-engine-migration skill.

Reads the same promptfoo-style YAML test cases (under evals/tests/), calls
Amazon Bedrock's Converse API with a Claude inference profile, and runs the
same `contains` / `icontains` / `not-contains` / `regex` assertions against
the model's output. Prints a pass/fail table and exits non-zero on any
failure.

Why a second harness?
- promptfoo is portable but requires Node.js + a configured provider.
- Bedrock-native lets you validate inside an AWS account with `ada` /
  Isengard credentials (no Node, no third-party provider).
- Same fixtures, same rubric — different runtime.

Usage:
    # source AWS creds (e.g. via ada credentials update ...) then:
    python3 evals/run_bedrock.py
    python3 evals/run_bedrock.py --model us.anthropic.claude-haiku-4-5-20251001-v1:0
    python3 evals/run_bedrock.py --tests evals/tests/citations-required.yaml
    python3 evals/run_bedrock.py --json /tmp/results.json
    python3 evals/run_bedrock.py --dry-run     # no Bedrock call; exercise harness

Exit codes:
    0  all assertions passed
    1  one or more assertions failed
    2  config / credential / environment error
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# Vendored tiny YAML reader: stdlib-only, supports the strict subset our
# fixtures use. Falls back to PyYAML if available.
def _load_yaml(text: str) -> dict:
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ImportError:
        return _load_yaml_minimal(text)


def _load_yaml_minimal(text: str) -> dict:
    """Minimal YAML loader for the subset our fixtures use:

    - top-level mapping
    - scalar strings (single-quoted on one line)
    - nested 'vars:' mapping (one level deep)
    - 'assert:' list of mappings each with 'type:' and 'value:'

    This is intentionally narrow; richer YAML would need PyYAML.
    """
    out: dict = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line or line.lstrip().startswith("#"):
            i += 1
            continue
        if not line.startswith(" "):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if not val:
                if key == "assert":
                    items: list[dict] = []
                    i += 1
                    cur: dict | None = None
                    while i < len(lines):
                        ln = lines[i].rstrip()
                        if ln.startswith("  - "):
                            if cur is not None:
                                items.append(cur)
                            cur = {}
                            kv = ln[4:].strip()
                            k, _, v = kv.partition(":")
                            cur[k.strip()] = _strip_quotes(v.strip())
                        elif ln.startswith("    "):
                            kv = ln.strip()
                            k, _, v = kv.partition(":")
                            if cur is not None:
                                cur[k.strip()] = _strip_quotes(v.strip())
                        elif not ln.strip() or ln.startswith("  #"):
                            pass
                        else:
                            break
                        i += 1
                    if cur is not None:
                        items.append(cur)
                    out["assert"] = items
                    continue
                elif key == "vars":
                    sub: dict = {}
                    i += 1
                    while i < len(lines):
                        ln = lines[i].rstrip()
                        if ln.startswith("  ") and not ln.startswith("    "):
                            kv = ln.strip()
                            k, _, v = kv.partition(":")
                            sub[k.strip()] = _strip_quotes(v.strip())
                            i += 1
                        elif not ln.strip():
                            i += 1
                        else:
                            break
                    out["vars"] = sub
                    continue
                else:
                    out[key] = ""
            else:
                out[key] = _strip_quotes(val)
        i += 1
    return out


def _strip_quotes(s: str) -> str:
    if len(s) >= 2 and ((s[0] == s[-1] == "'") or (s[0] == s[-1] == '"')):
        return s[1:-1]
    return s


# ---------------------------------------------------------------------------
# Bedrock client wrapper
# ---------------------------------------------------------------------------

def make_bedrock_client(region: str):
    try:
        import boto3  # type: ignore
    except ImportError:
        print("ERROR: boto3 is required. Install with: pip install boto3",
              file=sys.stderr)
        sys.exit(2)
    return boto3.client("bedrock-runtime", region_name=region)


def call_bedrock(client, model_id: str, system: str, user: str,
                 max_tokens: int = 4096, temperature: float = 0.0) -> str:
    """Call Bedrock Converse API and return the raw text response."""
    resp = client.converse(
        modelId=model_id,
        system=[{"text": system}] if system else [],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
    )
    return resp["output"]["message"]["content"][0]["text"]


# ---------------------------------------------------------------------------
# Assertions (mirror the promptfoo subset our fixtures use)
# ---------------------------------------------------------------------------

def run_assertion(assertion: dict, output: str) -> tuple[bool, str]:
    atype = assertion.get("type", "")
    value = assertion.get("value", "")
    if atype == "contains":
        ok = value in output
        return ok, f"output {'contains' if ok else 'is missing'}: {value!r}"
    if atype == "icontains":
        ok = value.lower() in output.lower()
        return ok, f"output {'contains' if ok else 'is missing (case-insensitive)'}: {value!r}"
    if atype == "not-contains":
        ok = value not in output
        return ok, f"output {'is clean of' if ok else 'unexpectedly contains'}: {value!r}"
    if atype == "regex":
        ok = re.search(value, output) is not None
        return ok, f"regex {value!r} {'matched' if ok else 'did not match'}"
    return False, f"unsupported assertion type: {atype!r}"


# ---------------------------------------------------------------------------
# Test discovery and execution
# ---------------------------------------------------------------------------

def discover_tests(test_dir: Path) -> list[Path]:
    return sorted(test_dir.glob("*.yaml"))


def render_prompt(prompt_template: str, vars_dict: dict,
                  skill_content: str = "", pricing_as_of: str = "") -> str:
    out = prompt_template
    out = out.replace("{{skill_content}}", skill_content)
    out = out.replace("{{pricing_as_of}}", pricing_as_of)
    for k, v in vars_dict.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out


def load_skill_content(here: Path) -> str:
    """Load SKILL.md plus the key rubric references so the model sees
    canonical tokens like `snapshot-and-restore`, `service-` flavors,
    `direct-from-source`, and the path-decision rubric.
    """
    parts: list[str] = []
    skill_md = here.parent / "SKILL.md"
    if skill_md.exists():
        parts.append("# SKILL.md\n\n" + skill_md.read_text(encoding="utf-8"))

    # The two references that encode the rubric language used in evals.
    for relpath in ("references/migration-paths.md",
                    "references/target-decision-matrix.md"):
        p = here.parent / relpath
        if p.exists():
            parts.append(f"\n\n# {relpath}\n\n" + p.read_text(encoding="utf-8"))

    return "\n".join(parts)


def load_pricing_as_of(here: Path) -> str:
    """Return as_of date from pricing_data.json (empty string if missing)."""
    pd = here.parent / "scripts" / "pricing_data.json"
    if pd.exists():
        try:
            data = json.loads(pd.read_text(encoding="utf-8"))
            return str(data.get("as_of", ""))
        except (json.JSONDecodeError, OSError):
            return ""
    return ""


def run_one(test_path: Path, prompt_template: str, system: str, client,
            model_id: str, dry_run: bool, skill_content: str = "",
            pricing_as_of: str = "") -> dict:
    raw = test_path.read_text(encoding="utf-8")
    spec = _load_yaml(raw)
    desc = spec.get("description", test_path.stem)
    vars_dict = spec.get("vars", {}) or {}
    assertions = spec.get("assert", []) or []

    user_prompt = render_prompt(prompt_template, vars_dict,
                                skill_content=skill_content,
                                pricing_as_of=pricing_as_of)

    if dry_run:
        output = f"[dry-run mode] vars={vars_dict}"
    else:
        t0 = time.time()
        try:
            output = call_bedrock(client, model_id, system, user_prompt)
        except Exception as e:
            return {
                "test": desc,
                "path": str(test_path),
                "status": "ERROR",
                "error": str(e),
                "assertion_results": [],
                "duration_s": round(time.time() - t0, 2),
            }
        duration = round(time.time() - t0, 2)

    a_results = []
    for a in assertions:
        ok, msg = run_assertion(a, output)
        a_results.append({"type": a.get("type"), "value": a.get("value"),
                          "ok": ok, "message": msg})
    overall = all(r["ok"] for r in a_results) if a_results else True

    return {
        "test": desc,
        "path": str(test_path),
        "status": "PASS" if overall else "FAIL",
        "assertion_results": a_results,
        "duration_s": locals().get("duration", 0.0),
        "output_preview": output[:200] + ("..." if len(output) > 200 else ""),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    here = Path(__file__).resolve().parent
    default_test_dir = here / "tests"
    default_prompt = here / "prompts" / "migration-assessor.txt"

    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", default=os.environ.get(
        "BEDROCK_MODEL_ID",
        "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
        help="Bedrock model ID or inference profile (default: claude-haiku-4-5).")
    p.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"),
                   help="AWS region (default us-west-2).")
    p.add_argument("--tests", action="append", default=None,
                   help="Specific test YAML file(s); repeat for multiple. Default: all under evals/tests/")
    p.add_argument("--prompt", default=str(default_prompt),
                   help="Prompt template path (default: evals/prompts/migration-assessor.txt)")
    p.add_argument("--system", default=(
        "You are a senior AWS solutions architect specialising in search-engine "
        "migrations to Amazon OpenSearch Service / Serverless. Be precise, cite "
        "the AWS Knowledge MCP Server URL knowledge-mcp.global.api.aws for any "
        "non-obvious claim about Amazon OpenSearch, OSI, or Migration Assistant. "
        "Always quote price ranges with an as-of date and the standard "
        "estimate disclaimer."),
                   help="System prompt.")
    p.add_argument("--dry-run", action="store_true",
                   help="Skip Bedrock call; useful in CI without creds.")
    p.add_argument("--json", dest="json_out", default=None,
                   help="Write structured results to this path.")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()

    prompt_path = Path(args.prompt)
    if not prompt_path.exists():
        print(f"ERROR: prompt template not found: {prompt_path}", file=sys.stderr)
        return 2
    prompt_template = prompt_path.read_text(encoding="utf-8")

    if args.tests:
        test_files = [Path(t) for t in args.tests]
    else:
        test_files = discover_tests(default_test_dir)
    if not test_files:
        print(f"ERROR: no tests found under {default_test_dir}", file=sys.stderr)
        return 2

    client = None if args.dry_run else make_bedrock_client(args.region)
    skill_content = load_skill_content(here)
    pricing_as_of = load_pricing_as_of(here)

    print(f"Bedrock eval harness")
    print(f"  region:  {args.region}")
    print(f"  model:   {args.model}")
    print(f"  tests:   {len(test_files)}")
    print(f"  dry_run: {args.dry_run}")
    print(f"  skill_md_chars: {len(skill_content)}")
    print(f"  pricing_as_of:  {pricing_as_of or '(missing)'}")
    print()

    results = []
    pass_count = 0
    for tf in test_files:
        r = run_one(tf, prompt_template, args.system, client, args.model,
                    args.dry_run, skill_content=skill_content,
                    pricing_as_of=pricing_as_of)
        results.append(r)
        flag = {"PASS": "PASS", "FAIL": "FAIL", "ERROR": "ERR "}[r["status"]]
        print(f"  [{flag}] {r['test']}  ({r['duration_s']}s)")
        if args.verbose or r["status"] != "PASS":
            for a in r["assertion_results"]:
                mark = "OK" if a["ok"] else "X "
                print(f"        {mark}  {a['message']}")
            if r.get("error"):
                print(f"        error: {r['error']}")
            if args.verbose and r.get("output_preview"):
                print(f"        preview: {r['output_preview']}")
        if r["status"] == "PASS":
            pass_count += 1

    print()
    total = len(results)
    print(f"Results: {pass_count}/{total} passed")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"results": results,
                        "summary": {"total": total, "passed": pass_count,
                                    "model": args.model, "region": args.region}},
                       indent=2),
            encoding="utf-8")
        print(f"Wrote JSON report to {args.json_out}")

    return 0 if pass_count == total else 1


if __name__ == "__main__":
    sys.exit(main())
