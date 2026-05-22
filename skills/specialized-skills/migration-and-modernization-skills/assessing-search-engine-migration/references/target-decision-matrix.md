# Target Decision Matrix — Amazon OpenSearch Service vs Amazon OpenSearch Serverless

Use these rules to pick a target. The same rules are codified in
[`scripts/decision_engine.py`](../scripts/decision_engine.py) — keep this doc and the script in sync.

For every rule that fires, the recommendation report MUST include a citation from the AWS Knowledge
MCP Server. The canonical queries are listed in
[aws-knowledge-integration.md](aws-knowledge-integration.md).

## Hard blockers (rule out Serverless)

If ANY of these apply, recommend **Amazon OpenSearch Service**:

| Blocker | Why |
|---|---|
| Custom plugins (Learning to Rank, custom analyzers, Sigma rule plugin, etc.) | Serverless does not run customer plugin code. |
| Anomaly Detection or Alerting plugin | Not available on Serverless. |
| Cross-cluster Replication (CCR) | Not available on Serverless. |
| Cross-cluster search to non-AWS clusters | Not available on Serverless. |
| ISM with custom transitions (e.g. shrink, force-merge) | Time-series collections handle tiering automatically; advanced ISM is not exposed. |
| Snapshot to a user-owned S3 repository | Serverless uses managed snapshots and does not write user S3 directly. |
| Sub-100 GB or sub-1 OCU minimum-load workloads where cost ceiling is critical | OCU floor produces a per-month minimum that exceeds a small `t3.small.search` Service domain. Quantify in Phase 6. |
| FedRAMP High / GovCloud-only requirement (if Serverless not yet available there) | Confirm with AWS Knowledge MCP at recommendation time. |
| Need to run JVM-level scripts beyond Painless / SQL / PPL | Not exposed on Serverless. |

## Soft preferences (favor Serverless)

If ALL Service-only blockers are absent AND ANY of these apply, recommend **Amazon OpenSearch Serverless**:

| Preference | Collection type |
|---|---|
| Bursty traffic with idle troughs (e.g. business-hours ingest only) | search or time-series |
| Append-only logs/metrics with TTL | time-series |
| Vector index for embedding retrieval / RAG | vector |
| Multi-tenant SaaS that wants per-collection isolation | search (one collection per tenant) |
| Team has zero ops bandwidth | any |
| Workload has unpredictable size growth and the team prefers paying-for-use over capacity planning | any |

## Soft preferences (favor Service)

If ALL of these apply, recommend **Amazon OpenSearch Service**:

| Preference | Why |
|---|---|
| Steady, predictable load 24×7 | Reserved instances + provisioned capacity is cheapest. |
| Data >5 TB primary | Serverless storage rate exceeds gp3 EBS at this scale. |
| Tight p95 < 50 ms read latency | Provisioned warm caches and dedicated coordinators give finer control. |
| Existing investment in OpenSearch features (LTR, Anomaly Detection, custom packages) | Keep them. |
| Cost-optimization with reserved instances or savings plans | Available on Service, not Serverless. |
| Hot / warm / cold tiering with explicit policies | Service exposes UltraWarm and Cold tiers with full control. |

## Tie-breakers

If both targets pass the above, default to:

1. The cheaper option at the user's projected steady-state load (Phase 6 will compute this).
2. If the costs are within ±15%, default to **Service** for predictable workloads and **Serverless**
   for unpredictable ones.
3. Always quote the break-even point in the final report.

## Collection-type sub-decisions (Serverless)

| If Serverless is recommended... | Pick collection type |
|---|---|
| Workload is append-only with timestamps and time-based TTL | `time-series` |
| Workload is mutable text search / catalog / e-commerce | `search` |
| Workload stores high-dimensional vectors for semantic search / RAG | `vector` |

If the workload mixes patterns, prefer the collection type that matches the dominant traffic and
explicitly note the trade-off.

## Service tier sub-decisions

| If Service is recommended... | Pick |
|---|---|
| Steady search workload, latency-sensitive | `m6g` / `m7g` general-purpose; `r6g` if memory-bound |
| Time-series with cost focus | Hot tier (m6g/r6g) + UltraWarm (`ultrawarm1.medium.search`) + Cold tier on S3 |
| Vector search, large index | `r6g` / `r7g` (vector engines are memory-bound) |
| Dev / test / small | `t3.small.search` (with caveats — no SLA, single-AZ-only at small sizes) |

## Region and compliance gates

For each of these, query the AWS Knowledge MCP Server at decision time — answers can change
month-to-month:

- "Amazon OpenSearch Serverless availability in `<region>`"
- "Amazon OpenSearch Service FIPS-validated endpoint regions"
- "Amazon OpenSearch Serverless GovCloud availability"
- "Amazon OpenSearch Service HIPAA eligibility"

Record the answer in `facts.target.compliance_check` and surface it in the report.

## Decision rule trace (what the engine emits)

```json
{
  "target": "service-general",
  "runner_up": "aoss-search",
  "rules_fired": [
    {"rule": "soft-pref-service:steady-load", "matched": true},
    {"rule": "blocker-serverless:custom-plugin", "matched": true,
     "evidence": "facts.source.plugins_in_use contains 'opensearch-learning-to-rank'"}
  ],
  "citations_required": [
    "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-overview.html",
    "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/learning-to-rank.html"
  ]
}
```
