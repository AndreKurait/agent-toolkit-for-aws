# OR1, UltraWarm, and Cold Storage — AOS Tiers Deep Dive

## OR1 ("OpenSearch-Optimized") instance family

GA at re:Invent 2023. Architecture: **each shard is durably persisted to S3
as primary storage; local NVMe is a hot cache** for query/index. Result:

- **One replica is enough** for durability (the classic 2-replica r-family
  pattern is unnecessary).
- Indexing throughput ~**2× r6g** at equivalent shape.
- ~30% lower compute cost per indexed-doc; ~**40% TCO** once the
  eliminated replica is counted.
- Hourly is ~25% above r6g, but each OR1 carries the durability r6g requires
  2× of.

### When OR1 wins

- **Indexing-heavy logs/observability** (>50 GB/day/node).
- **Spiky write workloads** — S3-backed segments make scale-out elastic.
- **Multi-PB log tiers** — replica elimination compounds.

### When r-family still wins

- **Latency-sensitive search** with small indices fitting in r6g.2xlarge RAM.
- **Heavy aggregations** on hot indices (OR1 cache miss = S3 round-trip).
- **Vector / k-NN workloads** — k-NN graphs are RAM-bound; favor r-family.
- **Steady-state low ingest, high-fanout query** — r-family cheaper.

### Regional availability

OR1 GA in 15 commercial regions. **Not yet:** us-gov-west-1, us-gov-east-1,
China regions, ap-southeast-3, af-south-1, me-south-1.

## UltraWarm

UW nodes use **S3 + node-local cache**, not attached storage. The number
that matters for capacity planning is **max addressable warm = 5× cache**.

| UW instance | Cache | Max addressable warm |
|---|---|---|
| ultrawarm1.medium.search | – | 1.5 TiB |
| ultrawarm1.large.search  | – | 20 TiB |
| oi2.large                | 375 GB | 1,875 GB |
| oi2.xlarge               | 750 GB | 3,750 GB |
| oi2.2xlarge              | 1,500 GB | 7,500 GB |
| oi2.4xlarge              | 3,000 GB | 15,000 GB |
| oi2.8xlarge              | 6,000 GB | 30,000 GB |

Warm = read-only unless returned to hot.

```
POST _ultrawarm/migration/<idx>/_warm
GET  _ultrawarm/migration/_status
```

Pre-2.x k-NN indexes can NOT migrate to UW or Cold.

Hot+warm node combined cap = data-nodes-per-AZ row (1-AZ 334 / 2-AZ 668 /
3-AZ 1,002); warm-only sub-cap 250 / 500 / 750.

[UltraWarm](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/ultrawarm.html) ·
[Limits](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/limits.html)

## Cold storage

[Cold](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/cold-storage.html)

**Cold is NOT directly queryable.** "You selectively attach it to existing
UltraWarm nodes" — Cold→Warm migration is required before any query reaches
the data. Up to 100 migrations queueable; monitor
`WarmToColdMigrationQueueSize`.

No transfer charges between warm/cold; one copy charged during migration.

## Cost ratios (us-east-1, indicative)

| Tier | $/GB-mo | Notes |
|---|---|---|
| Hot AOS-managed gp3 | 0.122 | Bundled volume + IOPS baseline + mgmt overhead |
| Hot raw EBS gp3 (ref) | 0.080 | NOT what you pay on AOS |
| UltraWarm S3-backed | ~0.024 | Plus the UW instance hour |
| Cold S3-backed | ~0.0125 | Roughly S3-Standard-IA |

Multiplied across replicas, shard overhead, snapshot retention, and Multi-AZ
data transfer, hot-tier costs dominate. Most teams under-utilize the warm
and cold tiers on day-1 of a migration.

## Tiering decision tree

```
Is data write-once-read-occasionally with a known retention?
├── Yes — does query latency tolerate seconds-to-minutes for the rarest 20%?
│   ├── Yes → 7-day hot, 30-day UltraWarm, 90-day Cold (or longer).
│   └── No  → 14-day hot, 60-day UltraWarm, no Cold.
└── No — fully hot. (Often the right call for SEARCH workloads.)
```

ISM policies automate the transitions:

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

ISM is **NOT available on AOSS** — TIME_SERIES auto-tiers but you don't
control it.
