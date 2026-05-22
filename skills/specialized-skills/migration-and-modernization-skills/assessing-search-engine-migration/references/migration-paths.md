# Migration Paths — Choosing the Mechanism

Four supported mechanisms. The decision is independent of target choice (Service vs Serverless) —
all four paths can land data in either target, with caveats noted below.

The same rules are codified in [`scripts/decision_engine.py`](../scripts/decision_engine.py) under
`decide_path(...)`.

## Path A — AWS Migration Assistant for OpenSearch (recommended default)

**What it is.** A managed migration toolkit (open source, AWS-supported) that performs a
Reindex-from-Snapshot (RFS) backfill of historical data from a source ES/OS snapshot in S3,
optionally combined with capture-and-replay or live-replay of in-flight traffic for a
cutover-with-zero-data-loss workflow. Docs:

- AWS Knowledge MCP query: `"AWS Migration Assistant for OpenSearch overview"`
- Repository: <https://github.com/opensearch-project/opensearch-migrations>

**When it wins.**

- Source is Elasticsearch 5.x – 8.x or OpenSearch 1.x – 3.x.
- You want a tested, supported, and documented workflow with a recovery story.
- You need transformations during migration (e.g. type-removal for ES 5.x → modern OpenSearch).
- You want capture-and-replay validation before flipping production traffic.
- You want the option to fork DR traffic to the new cluster as a confidence-building step.

**When it loses.**

- Source is Apache Solr (MA does not support Solr — see Path D).
- Source is so small (< ~50 GB) that the operational overhead of MA exceeds plain snapshot-and-restore.
- You need a continuous, ongoing replication pipeline rather than a one-time cutover (see Path C).

**Pros.**

- Tested compatibility matrix across many ES → OS version pairs.
- Backfill via RFS scales horizontally (Reindex-from-Snapshot workers can be tuned).
- Capture-and-replay gives traffic-level validation without exposing the new cluster prematurely.
- Open source — you own the runbook end-to-end.

**Cons.**

- Operator effort to deploy MA's infrastructure (typically EKS or ECS).
- RFS throughput depends on snapshot S3 region locality and worker count.
- Capture proxies add a hop to the source cluster during the capture window.

**Migration-period cost drivers.**

- MA infra (EKS or ECS): typically a small cluster running for the duration of backfill +
  capture-and-replay. Estimate `1 × m6g.xlarge` per few-TB of source data per day of allowed
  backfill, scaled up for parallelism.
- S3 storage for snapshots (one-time).
- Inter-region or cross-AZ data transfer if source is on-prem or another region.

## Path B — Snapshot-and-Restore

**What it is.** Take a Lucene snapshot from the source, copy it to an S3 bucket, register the
bucket as a `repository-s3` repository on the Amazon OpenSearch Service domain, and restore.

**When it wins.**

- Source is Elasticsearch 7.x or OpenSearch 1.x – 3.x AND target is a compatible OpenSearch
  version (consult the AWS-published compatibility matrix at recommendation time).
- The data fits in a single restore window of acceptable downtime.
- No transformations are required.
- Total data volume is small enough that the simplicity outweighs MA's safety nets (rule of thumb:
  ≤ ~500 GB primary data, single-index or homogeneous mappings).

**When it loses.**

- Source is Elasticsearch 5.x or 6.x — the snapshot format is too old for direct restore.
- Source is Solr — incompatible snapshot format.
- Target is Amazon OpenSearch Serverless — Serverless does not support user-bucket snapshot
  restore. Confirm the current state with the AWS Knowledge MCP Server before recommending.
- You need transformations or any data shape change.

**Pros.**

- Cheapest mechanism by a wide margin — only S3 storage and a brief restore window.
- Uses the documented OpenSearch `repository-s3` plugin path.
- Restorable to any compatible version that can read the snapshot.

**Cons.**

- Tight version compatibility constraints.
- All-or-nothing per index (no field-level transformations).
- Cutover requires application-level downtime or a separate dual-write strategy.

**Migration-period cost drivers.**

- S3 snapshot storage (one-time, typically pennies per GB-month for weeks).
- Cross-AZ or cross-region data transfer if source is on-prem or another region.

## Path C — OpenSearch Ingestion (OSI)

**What it is.** A managed, OCU-billed pipeline service (Data Prepper-based) that pulls from a
source (Elasticsearch, OpenSearch, S3, Kafka, Kinesis, etc.) and writes to a target Amazon
OpenSearch Service domain or Serverless collection, with optional in-flight transformations.

- AWS Knowledge MCP query: `"Amazon OpenSearch Ingestion supported sources"`

**When it wins.**

- You need transformations during migration (renames, type changes, field derivation).
- You want a continuous replication pipeline that keeps source and target in sync until cutover.
- You want a managed service rather than running MA infrastructure yourself.
- The target is Amazon OpenSearch Serverless (where MA's RFS path may not apply directly —
  re-verify against AWS Knowledge MCP at recommendation time).

**When it loses.**

- Source is not on the OSI supported source list (verify at recommendation time).
- Total backfill volume is large enough that OCU-hours exceed the cost of MA's RFS path.
- Source has bespoke authentication that OSI cannot natively configure.

**Pros.**

- Fully managed — no infrastructure to deploy.
- Native OpenSearch and Elasticsearch source support.
- Per-document transformation in the pipeline.
- Auto-scales OCUs.

**Cons.**

- OCU-hour cost can dominate for large historic backfills.
- Pipeline definitions are YAML — non-trivial to author for complex transformations.
- Some advanced source connectors are still maturing — re-verify support.

**Migration-period cost drivers.**

- OCU-hours for the duration of backfill + steady replication.
- Storage and ingest costs on the target Service or Serverless.

## Path D — Direct from Source (Spark on EMR / Glue / Lambda)

**What it is.** A custom batch job, typically Spark on Amazon EMR (Serverless or provisioned),
that reads from the source (Solr `cursorMark` paging, ES `_search` with PIT, JDBC) and writes
to OpenSearch via the OpenSearch Spark connector or the OpenSearch SDK.

**When it wins.**

- Source is Apache Solr (MA does not yet apply).
- Source is a niche ES fork or a vector DB that no other path supports.
- You need maximum transformation flexibility (PySpark / Scala UDFs).
- You already have an EMR / Spark practice in-house.

**When it loses.**

- You don't have Spark/EMR operational experience and the workload doesn't justify standing it up.
- Source is plain ES or OS and Path A or C would do the job.

**Pros.**

- Maximum flexibility — any source, any transform.
- Works for Solr, where MA does not.
- Can leverage existing EMR / Glue infrastructure.

**Cons.**

- You own the operator effort end-to-end.
- No built-in capture-and-replay — cutover strategy is yours to design.
- Must handle restartability, idempotence, and progress checkpointing yourself.

**Migration-period cost drivers.**

- EMR cluster (or EMR Serverless) for the duration of backfill.
- S3 for staging or checkpoints if needed.
- Inter-region/AZ data transfer.

## Quick decision flow

```text
source_engine?
├─ solr   → Path D (direct-from-source via Spark/EMR)
│             unless data is small + simple → consider exporting to NDJSON and using Path C (OSI from S3)
└─ elasticsearch | opensearch
   ├─ continuous replication required?
   │     └─ yes → Path C (OSI)
   ├─ transformations required?
   │     └─ yes → Path C (OSI)  [or Path A if you prefer self-hosted]
   ├─ backfill > 1 TB or strict cutover SLO?
   │     └─ yes → Path A (Migration Assistant with RFS + capture/replay)
   └─ simple, small, version-compatible
         └─ Path B (snapshot-and-restore)
```

## Combination patterns

These are non-exclusive; a real migration often combines paths:

- **A + B**: take a snapshot-and-restore for historic, run MA capture-and-replay for the cutover window.
- **A + C**: MA backfill, then keep an OSI pipeline running post-cutover as a safety net.
- **D + C**: Spark/EMR for the historic Solr backfill, OSI as a steady-state ingest path from the new system of record.

In the final report, name the primary path and any complementary paths explicitly.
