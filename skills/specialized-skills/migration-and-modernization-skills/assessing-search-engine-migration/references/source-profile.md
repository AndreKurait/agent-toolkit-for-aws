# Source Profile — Questionnaire and Interpretation

Use this checklist to fill `facts.source` in Phase 2. For every field the user cannot answer
exactly, propose a plausible value with explicit assumptions and confirm before storing.

## Topology

| Question | Why we ask | How to interpret |
|---|---|---|
| How many nodes? Roles? | Sets a floor for target node count; identifies dedicated coordinators / cluster managers. | Solr ZooKeeper ensemble does NOT translate — OpenSearch uses a Raft-based cluster manager built in. Document that the user should drop ZK from the target topology. |
| Single cluster or cross-cluster (CCR / CDCR)? | Drives Service vs Serverless and replication design. | Serverless does not currently support CCR — flag as a blocker if cross-cluster replication is in use. |
| What was the cluster instance type? | Anchor for sizing recommendations. | Use as the baseline for Phase 5 sizing (1:1 mapping, then adjust). |
| Self-managed, ECE/EKS, or hosted (Bonsai, Aiven, Elastic Cloud)? | Affects snapshot accessibility and migration permissions. | Hosted ES typically allows S3 snapshots only with their cooperation — flag if MA's RFS path is the chosen mechanism. |

## Data shape

| Question | Why we ask | How to interpret |
|---|---|---|
| Index/collection count? | Drives shard math and Serverless suitability (per-collection OCU floors). | If >100 small indices, recommend ISM rollover or grouping; if 1–10 large, plain shard split is fine. |
| Total data size (primary copy, GB or TB)? | Storage cost, snapshot duration, RFS time. | Flag anything ≥10 TB for ultrawarm/cold storage on Service, or for Serverless time-series tiering. |
| Total document count? | With size, gives average doc size — drives shard size recommendations. | Average doc size <1 KB usually → over-shard risk. |
| Average and p99 document size? | Memory pressure and refresh interval planning. | Large docs (>100 KB) suggest disabling `_source` for some fields or moving to S3-only blob storage. |

## Workload pattern

| Question | Why we ask | How to interpret |
|---|---|---|
| Is the data append-only, mutable, or bulk-reindexed? | Serverless time-series only supports append-only with TTL — mutable workloads must use Service or Serverless `search` collections. | Mutable + frequent updates → Service strongly preferred. |
| Update rate (docs/sec, peak)? | Serverless OCU sizing (each indexing OCU sustains ~1 GB/min of indexing); Service replica and refresh tuning. | Sustained ≥10 K docs/s → Service with dedicated coordinators or Serverless ≥4 OCU. |
| Query rate (QPS, peak and steady)? | Replica count; Serverless OCU floors. | Below 1 QPS sustained → Serverless cost-floor is likely worse than Service `t3.small.search`. |
| Read/write ratio? | Hot vs warm tiering; replica count. | Read-heavy → more replicas / coordinating tier; write-heavy → more shards / refresh lag tolerance. |
| Latency SLO (p95)? | Drives instance class and Serverless OCU minimums. | <100 ms p95 → m6g/m7g/r6g class on Service; Serverless OK for ≥200 ms. |

## Retention and lifecycle

| Question | Why we ask |
|---|---|
| Fixed retention (e.g. 90 days)? | Time-series collection type for Serverless or hot/warm/cold tiering on Service. |
| Per-index ISM policies? | Some Solr deployments don't have an equivalent — OpenSearch ISM is the target. |
| Snapshot policy? Where do snapshots live? | If S3, MA's RFS path can use the same bucket. |

## Security and access

| Question | Why we ask |
|---|---|
| Auth model (Basic, mTLS, OIDC, SAML, IAM, AWS Cognito)? | Maps to OpenSearch Security plugin domains; Serverless uses IAM-based access policies and SAML. |
| Network exposure (public, VPC-only, on-prem via PrivateLink)? | Drives VPC placement and PrivateLink endpoints. |
| Compliance regimes (FedRAMP, HIPAA, PCI, FIPS 140-3)? | Service availability and required AMIs/regions; Serverless availability is more limited. |

## Plugin compatibility

| Plugin / feature | Service support | Serverless support | Notes |
|---|---|---|---|
| ICU analysis | yes | yes | Built-in. |
| Phonetic analysis | yes | yes | Built-in. |
| Smart Chinese / IK / Kuromoji | yes (Service-managed) | partial | Confirm with AWS Knowledge MCP — Serverless analyzers are evolving. |
| Custom JAR plugins (Learning to Rank, custom analyzers) | yes (custom packages) | **no** | Hard blocker for Serverless. |
| Anomaly Detection | yes | **no** | Hard blocker for Serverless. |
| Alerting | yes | **no** (use EventBridge) | Re-architect alerts for Serverless. |
| ISM | yes (full) | partial | Serverless time-series collections handle hot/warm tiering automatically. |
| SQL / PPL | yes | yes | |
| k-NN / Vector | yes | yes (vector collection type) | Serverless vector has specific OCU rules. |
| Cross-cluster Replication (CCR) | yes | **no** | Hard blocker for Serverless. |
| Snapshot to user S3 bucket | yes | partial | Serverless uses managed snapshots; restore is to OpenSearch only. |

For any plugin not in this table: query the AWS Knowledge MCP Server with
`"Amazon OpenSearch <plugin name> support"` and record the answer in the report.

## Validation

After collecting all fields, run:

```bash
python3 scripts/source_assessor.py validate --profile-json /tmp/source-profile.json
```

The script checks for required fields, value ranges, and internal consistency (e.g. peak indexing
rate vs total data size vs retention).
