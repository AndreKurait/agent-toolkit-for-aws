# Pricing Data — Estimator Fixture and Freshness Policy

> **Live data first.** Current AWS list prices are read live via MCP — do
> not trust the embedded JSON for "what does this cost today?":
>
> ```jsonc
> // Full pricing page (TOC + 9 worked examples + RI table)
> { "tool": "aws___read_documentation",
>   "args": { "url": "https://aws.amazon.com/opensearch-service/pricing/",
>             "max_length": 8000 } }
> ```

This file documents the **estimator's snapshot fixture** at
[`scripts/pricing_data.json`](../scripts/pricing_data.json) — what's in
it, why it exists, and how to refresh it.

## Why a snapshot exists at all

The cost estimator runs deterministic unit tests against fixed prices.
Pulling live prices into tests would make assertions flaky. So the
fixture exists **only for `tests/test_pricing_estimator.py` reproducibility**
— never for "this is what AWS charges today."

The estimator output **always** includes:

1. The `as_of` date from the JSON, surfaced verbatim.
2. A `WARN: pricing data is stale` line if `as_of` is older than 90 days.
3. A "verify with the AWS Pricing Calculator and AWS Knowledge MCP"
   disclaimer in the footer.

When the user runs the estimator interactively, MCP-fetched prices should
**override** the snapshot for the report; the snapshot is the test
backstop, not the production source of truth.

## What the JSON covers (six regions)

`us-east-1`, `us-west-2`, `eu-west-1`, `ap-southeast-1`, `ap-south-1`,
`us-gov-west-1`.

For each region:

- **Managed instance hours**: t3, m6g/m7g, r6g/r7g, c6g, **OR1** family,
  ultrawarm1.
- **EBS gp3**: per-GB-month at AOS-managed rate (the AOS rate is
  ~52% above raw EC2 EBS gp3; the JSON reflects the AOS rate).
- **Tier storage**: `ultrawarm_managed_storage_per_gb_month`,
  `cold_managed_storage_per_gb_month`.
- **Serverless**: `ocu_per_hour`, `managed_storage_per_gb_month`,
  `minimum_ocu_redundant`, `minimum_ocu_non_redundant`.
- **RI discount table**: 1-yr / 3-yr × No-Upfront / Partial / All.
- **GovCloud uplift table**: per-family multiplier vs us-east-1.
- **OSI**, **EMR**, **S3**, **data transfer** lines.

The estimator falls back to `us-east-1` with a warning if the requested
region is missing — never silently substitute.

## Refresh procedure

1. **Read live prices via MCP** for each instance class and region in
   `scripts/pricing_data.json` (use the recipe at the top of this file).
2. Update the `usd_per_hour` field for any line that drifted.
3. Update the `as_of` date.
4. Run `python3 -m unittest discover tests` to confirm the test fixtures
   still pass (the deterministic assertions are tolerant of small price
   changes; large changes will fail and surface a refresh of expected
   values).
5. Commit with `chore(pricing): refresh OpenSearch list prices to YYYY-MM-DD`.

## When to flag a divergence in the report

The estimator emits a divergence note when the live MCP-fetched dominant
cost line differs from the snapshot by **>5%**. This is the operator's
signal that the snapshot is stale enough to risk customer-trust impact —
refresh before quoting.

## What this file does NOT contain

- The current dollar prices themselves — they live in MCP and in
  `scripts/pricing_data.json`. Quoting them here would be a third place
  to keep in sync, which is the bug we're avoiding.
- The full RI discount narrative or GovCloud uplift table — those live
  in `references/real-world-tco.md` because they're the result of an
  empirical analysis (sampling AWS Price List API across families), not
  a direct lookup.

## Mandatory disclaimer in every report (verbatim)

Every assessment report — and every estimator output — must include this
text verbatim. The estimator emits it; the human-authored report sections
must echo it. The phrase "not a quote" is the audit-trail anchor:

> **Pricing disclaimer.** Estimates use AWS list prices snapshot as of
> `<as_of>`. Actual cost depends on Reserved Instances, Savings Plans,
> EDP discounts, free-tier credits, AWS Marketplace add-ons, and your
> AWS account's billing region. Validate with the
> [AWS Pricing Calculator](https://calculator.aws) and, if available,
> the AWS Knowledge MCP Server before commitment. This estimate is
> **not a quote**.
