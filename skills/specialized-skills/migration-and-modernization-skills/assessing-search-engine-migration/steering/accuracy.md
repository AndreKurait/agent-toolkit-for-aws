# Accuracy & Estimate Discipline

This skill produces estimates, not quotes. Every numeric output must follow these rules.

## Always label estimates

- Sizing numbers MUST be labelled "estimate" with the assumption set inline.
- Pricing numbers MUST include the `as_of` date of the underlying list-price snapshot, the region,
  and the disclaimer text from `references/pricing-data.md`.
- Latency, throughput, or QPS projections MUST state whether they came from user-provided data,
  inference from cluster topology, or pure rule-of-thumb defaults.

## Never present a single number

Always quote a range — at minimum a low / mid / high band. The estimator emits these by varying
key inputs (replica count, OCU peak factor, search pattern complexity) within documented bounds.

## Verify with authoritative sources

Recommendations that touch:

- Service availability per region
- Compliance posture
- OCU pricing
- Plugin support

MUST be verified against the AWS Knowledge MCP Server at recommendation time. The skill MUST NOT
rely on this repository's static text for those facts.

## What counts as a sizing or pricing error

- Quoting a single dollar figure without a range or `as_of` date.
- Recommending a shard size outside 10–50 GB without justification.
- Setting JVM heap above 32 GB or above 50% of node RAM.
- Recommending fewer than 3 cluster manager nodes for a production cluster.
- Quoting a Serverless OCU minimum without checking the AWS Knowledge MCP for the current value.
- Mixing regions in a single estimate without disclosing it.
- Failing to state the recommended path's cutover plan and rollback story.

If any of the above slips into the report, fix it before delivering.

## Stale-data discipline

If `pricing_data.json.as_of` is older than 90 days, the estimator emits a `WARN` and the report
must surface that warning prominently. Refresh the snapshot per `references/pricing-data.md`
before relying on the numbers for a real decision.
