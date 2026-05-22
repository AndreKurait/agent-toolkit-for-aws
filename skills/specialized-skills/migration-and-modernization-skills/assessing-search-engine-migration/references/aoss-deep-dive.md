# Amazon OpenSearch Serverless — Deep Dive

Use this when the candidate target is AOSS or when the user asks "should I
go serverless?". All claims cite official AWS docs; every claim should be
re-validated via the AWS Knowledge MCP Server before commitment.

## OCU economics

- **1 OCU** = 6 GiB RAM + corresponding vCPU + GP3 disk + S3 transfer.
- **0.5 OCU** = 3 GB RAM, ½ vCPU, 60 GB disk (2024 reduction).
- Hot-cache capacity ≈ **120 GiB hot index per OCU**.
- Scaling step: 0.5 → 1 → +1 OCU.
- Account caps: default **10 indexing + 10 search**; max **1,700 + 1,700**.

Floor cost (us-east-1):

- Redundancy ON: 2 indexing × 0.5 + 2 search × 0.5 = 4 half-OCUs ≈ **$350/mo**.
- Redundancy OFF: 0.5 + 0.5 ≈ **$174/mo**.

S3 is the durable system of record; OCUs are caches. VECTORSEARCH cannot
share OCUs with SEARCH or TIME_SERIES even under the same KMS key.

[AOSS overview](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-overview.html) ·
[Half-OCU blog](https://aws.amazon.com/blogs/big-data/amazon-opensearch-serverless-cost-effective-search-capabilities-at-any-scale/) ·
[Scaling](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-scaling.html)

## Collection types

|                          | SEARCH         | TIME_SERIES        | VECTORSEARCH   |
|--------------------------|----------------|--------------------|----------------|
| Storage                  | All hot        | Hot + warm/S3      | All hot        |
| Index size cap           | 1 TiB          | 100 TiB hot        | 1 TiB          |
| Custom `_id` PUT/upsert  | Yes            | **No**             | **No**         |
| `knn_vector` field       | No             | No                 | Yes            |
| Refresh                  | ~10 s          | ~10 s              | ~60 s          |
| Best fit                 | Mutable docs, e-commerce, log search | Append-only logs/metrics | RAG, semantic search, KB |

Account caps: 1,000 indexes per collection.

## API allowlist (vs AOS managed)

**Blocked:** `_snapshot/*` (manual), `_forcemerge`, `_shrink`, `_split`,
`_clone`, `_reindex`, `_rollover`, `_open`, `_close`, `_cluster/*`, `_nodes/*`,
`_tasks/*`, legacy `_template`, `/_scripts`, ISM, alerting, anomaly detection,
async-search.

**Most `_cat/*` blocked** except `_cat/indices`, `_cat/aliases`, `_cat/templates`.
NO `_cat/shards|nodes|allocation|recovery|segments|health`.

**Allowed:** `_aliases`, `_index_template`, `_component_template`,
`_search/point_in_time`, `_field_caps`, `_count`, `_explain`, `_msearch`.

[AOSS API allowlist](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-genref.html)

## What scaling triggers OCU growth

- Ingest rate spikes (raises **indexing** OCU pool).
- QPS / query latency spikes (raises **search** OCU pool).
- Persistent data growth (raises both).
- Shard count growth (auto-managed; user has no knob).
- Vector index RAM (each VECTORSEARCH OCU offers ~2 GB OS / 2 GB JVM /
  2 GB graph budget).

## Compatibility checklist before recommending AOSS

- [ ] No custom plugins required (LTR, Anomaly Detection, etc.).
- [ ] `update_pattern` ≠ keyed-upsert if collection type is TIME_SERIES or
      VECTORSEARCH.

- [ ] No reliance on `_cat/shards`, `_cluster/settings`, `_tasks`, ISM, or
      alerting JSON.

- [ ] No reliance on stored Painless (`/_scripts`).
- [ ] No `_snapshot` workflows for backup/restore.
- [ ] Idle hours unacceptable to pay $174-$350/mo per collection? → not AOSS.

## When AOSS is a clear win

- Bursty, unpredictable load with long idle.
- New project with no operator team.
- Bedrock RAG knowledge base (managed integration).
- Multi-tenant SaaS where each tenant maps to one collection.

## When AOSS is a clear lose

- Steady-state >50 GB/day ingest (managed OR1 wins on $/throughput).
- ISM-driven hot/warm/cold tiering required.
- LTR, Anomaly Detection, Security Analytics, async-search.
- Mutable docs with idempotent client-keyed upserts to TIME_SERIES.
- Mixed search+vector and budget-sensitive (the no-pool-share rule doubles
  the floor).
