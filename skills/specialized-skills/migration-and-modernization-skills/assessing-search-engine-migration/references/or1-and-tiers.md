# OR1, UltraWarm, Cold — Tiering Decisions

> **Live data first.** Instance specs, regional availability, and tiering
> mechanics are maintained in AWS docs and read live via MCP — do not
> embed snapshots:
>
> ```jsonc
> // OR1/OR2/OM2/OI2 architecture, limitations, tuning
> { "tool": "aws___read_documentation",
>   "args": { "url": "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/or1.html",
>             "max_length": 8000 } }
>
> // UltraWarm spec + supported instance types
> { "tool": "aws___read_documentation",
>   "args": { "url": "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/ultrawarm.html",
>             "max_length": 6000 } }
>
> // Cold storage spec + ISM transitions
> { "tool": "aws___read_documentation",
>   "args": { "url": "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/cold-storage.html",
>             "max_length": 4000 } }
>
> // OR1 regional availability (structured)
> { "tool": "aws___get_regional_availability",
>   "args": { "resource_type": "product",
>             "regions": ["us-east-1", "us-gov-west-1", "us-gov-east-1"],
>             "filters": ["Amazon OpenSearch Service"] } }
> ```

This file augments the live docs with **the decision logic** the docs
don't pre-make for you.

## When OR1 wins over r-family

- **Indexing-heavy logs/observability** — >50 GB/day/node steady-state.
- **Spiky write workloads** — S3-backed segments make scale-out elastic.
- **Multi-PB log tiers** — replica elimination compounds (OR1 needs 1
  replica for durability vs r-family's typical 2).
- **Rapid recovery requirements** — automatic data recovery from S3 on
  node failure beats EBS-snapshot restore.

## When r-family still wins over OR1

- **Latency-sensitive search** with small indices fitting in r6g.2xlarge
  RAM. Cache-miss → S3 round-trip on OR1.
- **Heavy aggregations on hot indices** — same cache-miss penalty.
- **Vector / k-NN workloads** — k-NN graphs are RAM-bound; favor r6g/r7g.
- **Steady-state low ingest, high-fanout query** — r-family cheaper per
  query.

## Tiering decision tree (the assessor's call)

```
Is data write-once-read-occasionally with a known retention?
├── Yes — does query latency tolerate seconds-to-minutes for the rarest 20%?
│   ├── Yes → 7-day hot, 30-day UltraWarm, 90-day Cold (or longer).
│   └── No  → 14-day hot, 60-day UltraWarm, no Cold.
└── No — fully hot. (Often the right call for SEARCH workloads.)
```

ISM policy template (apply on AOS managed; ISM is **not available on AOSS**
— TIME_SERIES collections auto-tier without operator control):

```json
{
  "states": [
    {"name":"hot",  "transitions":[{"state_name":"warm",
      "conditions":{"min_index_age":"7d"}}]},
    {"name":"warm", "actions":[{"warm_migration":{}}],
      "transitions":[{"state_name":"cold",
      "conditions":{"min_index_age":"30d"}}]},
    {"name":"cold", "actions":[{"cold_migration":{}}]}
  ]
}
```

## Cold-storage operational gotchas (not in the canonical page)

- **Cold is NOT directly queryable.** You selectively attach it to
  existing UltraWarm nodes; the migration is a queue (max 100 in flight).
  Monitor `WarmToColdMigrationQueueSize` before assuming queries can hit
  cold data on demand.
- Pre-2.x k-NN indexes **cannot** migrate to UW or Cold — flag during
  source profiling if the user's k-NN data predates 2.x.
- Hot+warm combined cap = data-nodes-per-AZ row (1-AZ 334 / 2-AZ 668 /
  3-AZ 1,002); warm-only sub-cap 250 / 500 / 750. Use these when sizing.
- One copy is charged during cold-migration transit; no transfer between
  warm and cold steady-state.

## Operator wisdom on day-1 tiering

Most teams under-utilize warm and cold tiers on day-1 of a migration —
they over-provision hot to "feel safe" and pay for it. The aggressive
default is: anything older than 7 days that hasn't been queried in 24
hours belongs in UltraWarm. Set ISM accordingly, then loosen if SLO
breaches show up in `IndexLatency` on warm reads.
