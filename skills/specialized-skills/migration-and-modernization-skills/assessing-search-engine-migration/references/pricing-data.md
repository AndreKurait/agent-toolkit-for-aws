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

```jsonc
{
  "as_of": "2025-01-15",
  "currency": "USD",
  "service": {
    "us-east-1": {
      "m6g.large.search":   { "usd_per_hour": 0.167, "vcpu": 2,  "memory_gib": 8 },
      "m6g.xlarge.search":  { "usd_per_hour": 0.334, "vcpu": 4,  "memory_gib": 16 },
      "m6g.2xlarge.search": { "usd_per_hour": 0.668, "vcpu": 8,  "memory_gib": 32 },
      "m6g.4xlarge.search": { "usd_per_hour": 1.336, "vcpu": 16, "memory_gib": 64 },
      "r6g.large.search":   { "usd_per_hour": 0.211, "vcpu": 2,  "memory_gib": 16 },
      "r6g.xlarge.search":  { "usd_per_hour": 0.422, "vcpu": 4,  "memory_gib": 32 },
      "r6g.2xlarge.search": { "usd_per_hour": 0.844, "vcpu": 8,  "memory_gib": 64 },
      "r6g.4xlarge.search": { "usd_per_hour": 1.688, "vcpu": 16, "memory_gib": 128 },
      "t3.small.search":    { "usd_per_hour": 0.036, "vcpu": 2,  "memory_gib": 2 },
      "ultrawarm1.medium.search": { "usd_per_hour": 0.238, "vcpu": 2, "memory_gib": 16 },
      "ebs_gp3_per_gb_month": 0.122,
      "ebs_gp3_per_iops_month": 0.008,
      "ebs_gp3_per_throughput_mbps_month": 0.097
    }
  },
  "serverless": {
    "us-east-1": {
      "ocu_per_hour": 0.24,
      "managed_storage_per_gb_month": 0.024
    }
  },
  "data_transfer": {
    "us-east-1": {
      "cross_az_per_gb": 0.01,
      "internet_egress_first_10tb_per_gb": 0.09
    }
  },
  "emr": {
    "us-east-1": {
      "emr_serverless_vcpu_hour": 0.052624,
      "emr_serverless_memory_gb_hour": 0.0057785
    }
  },
  "s3": {
    "us-east-1": {
      "standard_per_gb_month_first_50tb": 0.023
    }
  }
}
```

Adjust per region: pricing varies, especially for GovCloud and APAC regions. The estimator falls
back to `us-east-1` with a warning if the requested region is missing — never silently substitute.

## Disclaimer in every report

The pricing estimator embeds the following text in every output, verbatim:

> **Pricing disclaimer.** Estimates use AWS list prices snapshot as of `<as_of>`. Actual cost
> depends on Reserved Instances, Savings Plans, EDP discounts, free-tier credits, AWS Marketplace
> add-ons, and your AWS account's billing region. Validate with the
> [AWS Pricing Calculator](https://calculator.aws) and, if available, the AWS MCP Server's
> `pricing.get_products` API before commitment. This estimate is **not** a quote.
