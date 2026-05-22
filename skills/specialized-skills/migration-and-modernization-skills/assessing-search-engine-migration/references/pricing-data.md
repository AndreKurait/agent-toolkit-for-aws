# Pricing Data — List Prices and Freshness Policy

The estimator at [`scripts/pricing_estimator.py`](../scripts/pricing_estimator.py) reads the JSON
table at [`scripts/pricing_data.json`](../scripts/pricing_data.json). This document explains where
the numbers come from and how to keep them current.

## Freshness policy

- Numbers in the JSON are **list prices** snapshot from the public AWS pricing pages on a known date.
- The estimator ALWAYS surfaces the `as_of` date and a "verify with the AWS Pricing Calculator and
  AWS Knowledge MCP" disclaimer in its output.
- When the AWS MCP Server's `pricing.get_products` API is available in the user's runtime, prefer
  it for canonical figures and override the embedded values for the report.
- If the snapshot is older than 90 days, the estimator emits a `WARN: pricing data is stale`
  message and recommends a refresh.

## How to refresh

1. Visit the canonical pricing pages:

   - <https://aws.amazon.com/opensearch-service/pricing/>
   - <https://aws.amazon.com/opensearch-service/pricing/?nc=sn&loc=3>  (Serverless)
   - <https://aws.amazon.com/ebs/pricing/>
   - <https://aws.amazon.com/s3/pricing/>
   - <https://aws.amazon.com/emr/pricing/>

2. For each instance class and region in `pricing_data.json`, update the `usd_per_hour` field.

3. Update the `as_of` date.

4. Run `python3 -m unittest discover tests` to confirm the test fixtures still pass.

5. Commit with a message like `chore(pricing): refresh OpenSearch list prices to YYYY-MM-DD`.

## What the JSON contains

The shipped JSON covers six regions:
**us-east-1**, **us-west-2**, **eu-west-1**, **ap-southeast-1**,
**ap-south-1**, **us-gov-west-1**.

For each region, the `service` block includes:

- `t3.small.search` — burstable, 2 vCPU / 2 GiB.
- `m6g.{large,xlarge,2xlarge,4xlarge}.search` — Graviton2 general-purpose.
- `m7g.{xlarge,2xlarge,4xlarge}.search` — Graviton3 general-purpose (~12% faster than m6g).
- `r6g.{large,xlarge,2xlarge,4xlarge}.search` — Graviton2 memory-optimized (k-NN, aggregations).
- `r7g.{xlarge,2xlarge,4xlarge}.search` — Graviton3 memory-optimized.
- `c6g.{large,xlarge}.search` — Graviton2 compute-optimized (smaller-mem indexing).
- `or1.{medium,large,xlarge,2xlarge,4xlarge,8xlarge}.search` — S3-backed primary
  storage; ~2× r6g indexing throughput, replica=1 sufficient. **Not in
  us-gov-west-1 or ap-south-1.**
- `ultrawarm1.{medium,large}.search` — UltraWarm node hour (cache only;
  warm GB priced separately).
- `ebs_gp3_*` — GP3 attached-storage, IOPS, throughput. NOTE: AOS-managed
  GP3 is bundled at ~52% above raw EC2 EBS GP3 — the JSON already reflects
  the AOS-managed rate.
- `ultrawarm_managed_storage_per_gb_month` — UW S3-backed warm tier.
- `cold_managed_storage_per_gb_month` — cold tier.

Top-level blocks `serverless`, `data_transfer`, `osi`, `emr`, `s3` mirror
the same regional keys.

```jsonc
{
  "as_of": "2026-05-22",
  "currency": "USD",
  "service": {
    "us-east-1": {
      "or1.2xlarge.search": { "usd_per_hour": 1.124, "vcpu": 8, "memory_gib": 64 },
      "r7g.xlarge.search":  { "usd_per_hour": 0.472, "vcpu": 4, "memory_gib": 32 },
      "ultrawarm1.large.search": { "usd_per_hour": 1.910, "vcpu": 8, "memory_gib": 64 },
      "ebs_gp3_per_gb_month": 0.122,
      "ultrawarm_managed_storage_per_gb_month": 0.024,
      "cold_managed_storage_per_gb_month": 0.0125,
      "...": "more instances and per-GB prices"
    }
  },
  "serverless": {
    "us-east-1": {
      "ocu_per_hour": 0.24,
      "managed_storage_per_gb_month": 0.024,
      "minimum_ocu_redundant": 4,
      "minimum_ocu_non_redundant": 2
    }
  },
  "ri_discounts": {
    "graviton_1yr_no_upfront":  0.31,
    "graviton_3yr_no_upfront":  0.48,
    "graviton_3yr_all_upfront": 0.52
  },
  "govcloud_uplift_vs_us_east_1": {
    "m6g":  0.258,
    "r6g":  0.204,
    "aoss_ocu": 0.258
  }
}
```

The estimator falls back to `us-east-1` with a warning if the requested
region is missing — never silently substitute. For deeper TCO modeling
(hidden line items, RI discount math, GovCloud uplift table), see
[`real-world-tco.md`](real-world-tco.md).

## Disclaimer in every report

The pricing estimator embeds the following text in every output, verbatim:

> **Pricing disclaimer.** Estimates use AWS list prices snapshot as of `<as_of>`. Actual cost
> depends on Reserved Instances, Savings Plans, EDP discounts, free-tier credits, AWS Marketplace
> add-ons, and your AWS account's billing region. Validate with the
> [AWS Pricing Calculator](https://calculator.aws) and, if available, the AWS MCP Server's
> `pricing.get_products` API before commitment. This estimate is **not** a quote.
