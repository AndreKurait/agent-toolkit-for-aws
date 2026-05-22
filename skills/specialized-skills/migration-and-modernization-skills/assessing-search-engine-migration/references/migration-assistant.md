# AWS Migration Assistant for OpenSearch — Deep Dive

The default recommended path for ES 5.x-8.x and OS 1.x-3.x sources.

Repo: <https://github.com/opensearch-project/opensearch-migrations>
Docs: <https://opensearch.org/docs/latest/migration-assistant/>

## Architecture — three loosely-coupled tools on ECS Fargate

Deployed via a CDK app that emits CloudFormation. Components run in your VPC.

### 1. Metadata Migration

One-shot port of:

- Index templates (legacy `_template` and modern `_index_template`).
- Index settings and mappings.
- Aliases and ISM policies.

Applies version transformations:

- ES 6 `_type` collapse.
- ES 7 `_doc` strip.
- AOSS-mode sanitizer drops unsupported settings (`number_of_shards`,
  `refresh_interval`, etc.).

Idempotent — safe to re-run.

### 2. Reindex-from-Snapshot (RFS)

Workers read a Lucene snapshot directly from S3, decode segments, rebuild
`_source`, and bulk into the target. **Zero source-cluster load.**

A coordination index on the target hands shards to workers — natural
parallelism, restart-safe.

**Realistic throughput:** ≈ 5-15 MiB/s of source-snapshot bytes per worker
(≈30-80 GiB/hour/worker) depending on doc size, mapping, target shard count,
and instance class. Scale by raising Fargate `desiredCount`. 20-50 workers is
typical for multi-TB.

S3 snapshot bucket layout (standard Lucene repository):

```
index-N           # latest manifest
index.latest
meta-<uuid>.dat
snap-<uuid>.dat
indices/<indexUUID>/<shardId>/__<segmentFile>
```

RFS lists `indices/*/N/` to enumerate work units.

### 3. Capture-and-Replay (Traffic Replayer)

Netty proxy in front of source ships req/resp pairs to MSK Kafka. Replayer
SigV4-signs and replays against target. Used for:

- **Live-traffic validation** — diff source vs target responses, threshold
  on diff rate.

- **Zero-downtime cutover** — DNS swap once diff rate falls under SLO.

The diff output (tuple file) is the single most useful artifact for
migration confidence.

## Source/target version matrix

**Sources:** ES 1.x, 2.x, 5.x, 6.x, 7.x (incl. 7.10.2 OSS, 7.17), OS 1.x/2.x.

**Targets:** OS 1.3+, 2.x, AOS managed, AOSS (Metadata sanitizer required).

**RFS requires ES 6.8+ snapshots.** For ES 1-5 sources, use traffic-replay
or reindex-from-remote — but those preserve only what's queryable, not
historical data older than your replay window. Plan accordingly.

## Deployment

```bash
git clone https://github.com/opensearch-project/opensearch-migrations
cd opensearch-migrations/deployment/cdk/opensearch-service-migration
npm ci
cdk deploy "*" --c contextId=<your-context-id>
```

Synthesizes nested CloudFormation stacks:

- VPC + endpoints (S3, MSK, ECS) — minimize NAT.
- MSK cluster.
- ECS cluster with:
  - migration-console task (bastion with the `console` CLI).
  - capture-proxy task (in front of source).
  - replayer task.
  - RFS task.
- Optional target AOS domain.

`console` is the CLI for orchestrating. Useful commands:

- `console clusters connection-check` — verify both endpoints from inside the VPC.
- `console metadata migrate --otel-collector-endpoint=<otel>` — kick off metadata.
- `console snapshot create` — take a fresh snapshot on the source via API.
- `console backfill start` — start RFS workers.
- `console replayer start --speedup-factor 2.0` — replay live traffic at 2×.

## Common pitfalls

- **Snapshot system indices.** AOS rejects them on restore.
  Use `indices: "*,-.*"`.

- **`include_global_state: false` is mandatory** — it collides with the
  managed cluster's settings.

- **Searchable_snapshots partial format is not restorable** — full snapshots
  only.

- **AOSS does not support arbitrary-repo restore.** RFS works because it
  bulk-writes; the underlying repo is on the source side.

- **MSK throughput planning** — replayer replays at user-specified speedup;
  Kafka must keep up. Default 3 brokers is sized for ~50k req/s; scale up
  for higher ingest.

- **Tuple file size** — verbose req/resp logs balloon S3. Set retention to
  7-14 days unless you need them for audit.

## Validation flow

1. Metadata migrate (idempotent).
2. RFS backfill the historical data.
3. Capture-replay live traffic at 1×.
4. Diff tuples, threshold diff rate.
5. Replay at 2-5× to catch the live delta.
6. DNS swap.
7. Decommission source after observing target stability for N days.

## Realistic timing (TB-scale, all paths)

| Path | 1 TB | 10 TB | 100 TB |
|---|---|---|---|
| Snapshot+restore (OS→OS direct) | 1-3 h | 8-20 h | 4-8 days |
| Migration Assistant RFS | 2-6 h (20 workers) | 1-2 days | 1-2 weeks (50-100) |
| Reindex-from-remote (8 slices) | 6-24 h | 4-10 days | impractical |
| Logstash (10 pipelines) | 12-36 h | 1-2 weeks | impractical |
| OSI (auto-scaled OCUs) | 4-10 h | 1.5-4 days | 2-3 weeks |
| Spark/EMR (100 executors) | 2-5 h | 1-2 days | ~1 week |

Assumes target sized ~2× steady-state during migration, `refresh_interval: -1`,
`number_of_replicas: 0` during load, restored after. The MA console exposes
all of these knobs as defaults.
