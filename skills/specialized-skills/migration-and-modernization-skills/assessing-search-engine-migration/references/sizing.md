# Sizing — Amazon OpenSearch Service and Serverless

These rules are codified in [`scripts/pricing_estimator.py`](../scripts/pricing_estimator.py).
Keep this doc and the script in sync.

ALL sizing output must be labeled as estimates with the assumptions stated explicitly. Under-sizing
is a much harder problem to fix than over-sizing — when in doubt, size up.

## Service (managed cluster) rules

| Rule | Value |
|---|---|
| Shard size target | 10–50 GB per shard |
| Shard count formula | `primary_shards = ceil(total_data_size_gb / target_shard_size_gb)` |
| Replica default | `number_of_replicas = 1` (2 total copies) for production. Set `0` during bulk load, restore to `1` after. |
| JVM heap | `-Xms == -Xmx`, never above 50% of node RAM, never above 32 GB. Recommended 16–31 GB on data nodes. |
| Cluster manager nodes | 3 dedicated nodes (odd count for quorum). Replaces SolrCloud ZooKeeper completely. |
| Coordinating nodes | ≥ 2 dedicated coordinators behind ALB / NLB for production search workloads above ~500 QPS. |
| Storage formula | `total_storage_gb = primary_data_gb × (1 + replicas) × 1.3 (overhead) × 1.25 (headroom)` |
| Storage type | EBS gp3 by default; io2 for write-latency-sensitive workloads. |
| Disk watermark | OpenSearch stops shard allocation at 85% and blocks writes at 90%. Size to stay under 75% under steady load. |
| Hot/warm/cold | Use UltraWarm (`ultrawarm1.medium.search`) for warm data >30 days old; Cold tier (S3) for compliance-only retention. |

### Instance class guidance

| Workload | Class | Notes |
|---|---|---|
| Steady search, balanced | `m6g.large.search`–`m6g.4xlarge.search` | General purpose, Graviton. |
| Latency-sensitive search | `m7g`/`r7g` | Newer Graviton, lower p99. |
| Memory-bound (large filter caches, vector) | `r6g`/`r7g` | More RAM per vCPU. |
| Time-series, ingest-heavy | `m6g` data nodes + `ultrawarm1.medium.search` warm | Hot/warm/cold tier. |
| Dev/test only | `t3.small.search` | Burstable, no SLA, single-AZ only. |

### Data node count

```text
data_nodes = max(
  ceil(primary_shards / shards_per_node_target),
  ceil(total_storage_gb / per_node_storage_target_gb),
  azs (typically 3 for prod)
)
```

Targets:

- `shards_per_node_target = 25` for general workloads.
- `per_node_storage_target_gb = 1500` for `m6g.large.search` with gp3, scaling up by instance size.
- `azs = 3` for production (Multi-AZ with standby).

## Serverless (collection) rules

OpenSearch Serverless is billed by OpenSearch Compute Units (OCUs). Each OCU is a fixed bundle of
compute, memory, and storage I/O. Indexing OCUs and search OCUs scale independently.

| Rule | Value |
|---|---|
| OCU minimum | 4 OCUs minimum per collection in production (2 indexing + 2 search) for HA. Dev collections can use 1+1 or 0.5+0.5 (verify current minimum against AWS Knowledge MCP — it has decreased over time). |
| Indexing OCU sizing | One OCU sustains roughly 1 GB/min of indexing throughput. Round up. |
| Search OCU sizing | One OCU sustains roughly 8 K simple QPS or 1–2 K complex QPS. Workload-dependent — measure during a pilot. |
| Storage | Pay-per-GB managed storage, billed at the time-series or search rate from the pricing data table. |
| Vector collections | Use the `vector` collection type with OCU rules per the AWS Knowledge MCP query `"Amazon OpenSearch Serverless vector collection sizing"`. |
| Time-series collections | Hot tier auto-rolls older indices to S3-backed warm storage — no manual ISM. |

### When Serverless is cheaper than Service

- Workload is bursty: peak QPS far exceeds steady-state QPS, so a provisioned cluster sized for peak wastes capacity.
- Workload is small and you would otherwise pay for an underused 3-node multi-AZ cluster.
- Team has zero operational bandwidth and the cost premium is acceptable.

### When Service is cheaper than Serverless

- Workload is steady-state >0.5 OCU equivalent on both indexing and search 24×7.
- Data > ~5 TB primary — managed storage rate exceeds gp3.
- You can use 1- or 3-year reserved instances or a Savings Plan.

The pricing estimator computes both at the user's profile and surfaces the break-even point.

## Worked example

**Source:** Elasticsearch 7.10, 8 nodes, 4 TB primary data, 200 M docs, 200 docs/s peak ingest,
500 QPS peak read, 24×7 steady traffic, e-commerce search.

**Service sizing (recommended):**

- Shards: `ceil(4096 / 30) = 137` primary shards (split across indices as appropriate).
- Storage: `4096 × 2 × 1.3 × 1.25 = 13,312 GB` total provisioned EBS.
- Data nodes: 6 × `m6g.4xlarge.search` (3 AZ × 2), 2 TB EBS each.
- Cluster manager: 3 × `m6g.large.search.cluster_manager`.
- Coordinator: 2 × `c6g.xlarge.search`.

**Serverless sizing (alternative):**

- Indexing OCUs: ceil(200 docs/s × avg doc size / (1 GB/min)) — typically 2 indexing OCUs steady, scaling to 4 at peak.
- Search OCUs: 500 QPS / 4 K QPS per OCU = 0.125 → 2 OCU minimum for HA.
- Total: 4 OCUs minimum; expect 4–8 OCU-hours billed per hour at peak.

The pricing estimator turns both into monthly dollar ranges; the report quotes both with break-even.
