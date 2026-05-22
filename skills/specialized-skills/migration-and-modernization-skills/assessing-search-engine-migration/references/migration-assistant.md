# Migration Assistant — Operator Notes

> **Live data first.** The architecture, supported source/target version
> matrix, deployment commands, and cost model are maintained in AWS docs
> and read live via MCP — do not embed snapshots:
>
> ```jsonc
> // Solution overview + version matrix
> { "tool": "aws___read_documentation",
>   "args": { "url": "https://docs.aws.amazon.com/solutions/latest/migration-assistant-for-amazon-opensearch-service/solution-overview.html",
>             "max_length": 8000 } }
>
> // Cost (AWS publishes a worked example: ~$3,096 for 100 TB / 15 days
> // / 15 MBps live traffic in us-east-1, broken down by component)
> { "tool": "aws___read_documentation",
>   "args": { "url": "https://docs.aws.amazon.com/solutions/latest/migration-assistant-for-amazon-opensearch-service/cost.html",
>             "max_length": 6000 } }
> ```
>
> Repo: <https://github.com/opensearch-project/opensearch-migrations>
> Docs: <https://opensearch.org/docs/latest/migration-assistant/>

This file augments the live docs with **operator-side numbers and
pitfalls** the AWS docs don't surface.

## Realistic per-worker throughput (RFS)

Not in the AWS docs; empirically observed across customer migrations:

- **≈ 5–15 MiB/s of source-snapshot bytes per RFS worker** on Fargate.
- **≈ 30–80 GiB/hour/worker** depending on doc size, mapping, target
  shard count, and Fargate task class.
- **20–50 workers** is typical for multi-TB. Beyond ~100 you start to
  saturate the target's bulk-write capacity before adding throughput.

Use these to project wall-clock for your customer's data volume:

| Path | 1 TB | 10 TB | 100 TB |
|---|---|---|---|
| Snapshot+restore (OS→OS direct) | 1–3 h | 8–20 h | 4–8 days |
| Migration Assistant RFS | 2–6 h (20 workers) | 1–2 days | 1–2 weeks (50–100) |
| Reindex-from-remote (8 slices) | 6–24 h | 4–10 days | impractical |
| Logstash (10 pipelines) | 12–36 h | 1–2 weeks | impractical |
| OSI (auto-scaled OCUs) | 4–10 h | 1.5–4 days | 2–3 weeks |
| Spark/EMR (100 executors) | 2–5 h | 1–2 days | ~1 week |

Assumes target sized **~2× steady-state** during migration with
`refresh_interval: -1` and `number_of_replicas: 0` during load, restored
afterward.

## Common pitfalls (operator wisdom, not in docs)

- **Snapshot system indices.** AOS rejects them on restore. Use
  `indices: "*,-.*"` when taking the source snapshot.
- **`include_global_state: false` is mandatory** — true collides with the
  managed cluster's internal settings.
- **Searchable_snapshots partial-format snapshots are not restorable** —
  full snapshots only.
- **AOSS does not support arbitrary-repo restore.** RFS works because it
  bulk-writes; the underlying repo lives on the source side.
- **MSK throughput planning** — replayer replays at user-specified
  speedup; Kafka must keep up. Default 3 brokers sized for ~50k req/s;
  scale up for higher ingest before launching the replay.
- **Tuple-file size** — verbose req/resp logs balloon S3 fast. Set
  retention to 7–14 days unless audit requires otherwise.

## Validation flow (recommended sequence)

1. Metadata migrate (idempotent).
2. RFS backfill historical data.
3. Capture-replay live traffic at 1×.
4. Diff tuples; threshold diff rate per SLO.
5. Replay at 2–5× to catch the live delta.
6. DNS swap.
7. Decommission source after observing target stability for N days
   (typically 14–30 depending on SLO criticality).

## Source-eligibility thresholds (decision rules)

- **RFS requires ES 6.8+ snapshots.** For ES 1.x–5.x sources, fall back
  to traffic-replay or reindex-from-remote — but those preserve only what
  is queryable, not historical data older than your replay window. Plan
  accordingly.
- **AOSS as target requires the metadata sanitizer** (drops
  `number_of_shards`, `refresh_interval`, etc.). Confirm sanitizer mode
  in the metadata-migrate command before running.
- **Versions older than ES 1.x or Solr 6.x:** out of scope for Migration
  Assistant; recommend an external ingest pipeline (Logstash / OSI).
