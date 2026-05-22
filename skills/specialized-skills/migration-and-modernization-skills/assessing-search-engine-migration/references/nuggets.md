# Hidden Nuggets — Migration Assessment Gotchas

The traps experienced practitioners hit. Each one is a real failure mode that
silently breaks a migration plan. Cite these in your risk register when the
profile matches.

## 1. AOSS rejects custom `_id` PUT/upsert on TIME_SERIES and VECTORSEARCH

Only the `SEARCH` collection type supports `PUT <idx>/_doc/<id>` and
`POST <idx>/_create/<id>`. Idempotent client-keyed pipelines (Solr `uniqueKey`,
ES `external` versioning, dedup-by-fingerprint) silently break on
`TIME_SERIES`/`VECTORSEARCH` migrations.

**Detect:** `facts.source.update_pattern in {mutable, bulk_reindex}` AND target
is a non-`SEARCH` AOSS collection.

**Fix:** Choose `SEARCH`, OR move to AOS managed, OR refactor the writer to
let AOSS auto-generate `_id` and migrate dedup logic upstream (e.g., into OSI's
`fingerprint` processor with the result written to a side-channel).

[AOSS API reference](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-genref.html)

## 2. OpenSearch 2.17 made `cluster.max_shards_per_node` un-tunable

The new rule: **1,000 shards per 16 GiB heap, capped at 4,000**. ES 7.x
clusters that ran past 1,000 shards/node by raising `cluster.max_shards_per_node`
hit a wall on upgrade — they must consolidate indices or move to denser memory
instances. There is no override.

**Detect:** ES/OS source with shards/node > 800 (count `shards / data_nodes`).

**Fix:** Plan re-architecture pre-migration: ISM rollover to fewer larger
shards, denser r6g/r7g instances (16+ GiB heap each), or move to AOSS where
sharding is automatic.

[Limits](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/limits.html)

## 3. Cold storage is NOT directly queryable

The phrase "cold storage" suggests S3 Glacier-style on-demand query. It is
not. Cold indexes must be migrated back to UltraWarm before any search hits
them. The migration queue caps at 100 outstanding requests; monitor
`WarmToColdMigrationQueueSize`.

**Detect:** User says "we want occasional queries on archived data".

**Fix:** Either accept the warm-up latency (minutes-to-hours), keep that data
in UltraWarm permanently, or use S3+Athena/OpenSearch direct-query for true
on-demand on archives.

[Cold storage](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/cold-storage.html)

## 4. AOSS VECTORSEARCH cannot share OCUs with SEARCH/TIME_SERIES

Even under the same KMS key — a normally sufficient condition for OCU pool
sharing via collection groups — VECTORSEARCH gets its own pool. Adding a
single vector collection to an existing AOSS account roughly **doubles** the
idle floor (another 4 half-OCUs minimum at $174-$350/mo).

**Detect:** Mixed workload — keyword + vector. User assumes one bill.

**Fix:** Project both floors in pricing. If vector is small/exploratory,
consider AOS k-NN on the existing managed cluster instead.

[AOSS scaling](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-scaling.html)

## 5. AOSS silently drops index settings from snapshots/restores

`number_of_shards`, `number_of_replicas`, `refresh_interval`,
`index.translog.*`, `index.routing.allocation.*` — all ignored. Snapshot
restores "succeed" but the resulting layout is whatever AOSS auto-picked.
Sizing models built around shard counts in the source mapping mislead users.

**Detect:** Plan involves restoring an existing snapshot to AOSS.

**Fix:** Use Migration Assistant's metadata-migration AOSS-mode sanitizer, or
hand-strip index settings before bulk into AOSS. Re-validate by querying
`GET <idx>/_settings` post-load and adjusting the cost model.

## 6. SigV4 comma-encoding in `_cat` APIs

botocore signs commas raw but AOS canonicalizes them as `%2C`, producing a
403 "signature does not match" on URLs like
`_cat/indices?h=index,docs.count&format=json`. Manifests as inconsistent
discovery scripts during assessment.

**Detect:** Any AOS automation hitting `_cat/*?h=a,b,c`.

**Fix:** Use `requests-aws4auth(urlencode_querystring=False)`, OR pre-encode
`,` → `%2C` BEFORE signing AND BEFORE sending (both URLs identical), OR drop
the `h=` parameter and parse the full response.

## 7. Lucene 9 vs 10 segment-format wall

OpenSearch 1.x/2.x = Lucene 9. OpenSearch 3.x = Lucene 10. **Lucene-9 →
Lucene-10 restore works; the reverse fails** with `IndexFormatTooNewException`.
A snapshot from a 3.x source cannot land on a 2.x target. Pick the target
version *before* taking the snapshot.

[Migration Assistant docs](https://opensearch.org/docs/latest/migration-assistant/)

## 8. `fielddata: true` in old ES 1.x mappings will OOM AOS data nodes

Pre-ES 2.0, text fields used in-memory `fielddata` for sorting/aggregations.
ES 2+ and OpenSearch use disk-backed `doc_values` on keyword instead. ES 1.x
mappings still carry `"fielddata": true` on text fields and will OOM AOS data
nodes the first time someone runs an aggregation.

**Detect:** Source = ES 1.x or 2.x. Mapping JSON contains `fielddata`.

**Fix:** Strip `fielddata` from the mapping. Add a `.keyword` subfield. The
Migration Assistant transformer does this automatically; hand-rolled `_reindex`
must do it explicitly.

## 9. ES 7 → OS 1 `_type` removal

ES 7 still allows the placeholder type `_doc`. OpenSearch 1.0 removed types
entirely. Templates/mappings carrying `"_doc": {...}` blow up
`_reindex`/`_bulk` with `[mapper_parsing_exception] unsupported parameters: [_doc]`.

**Fix:** Use Migration Assistant's metadata transformer, OR pre-flatten:
`jq 'del(.mappings._doc) | .mappings = .mappings._doc' template.json`.

## 10. `max_clause_count` differs across the boundary

ES 7 = 1024. OpenSearch 2.x = 4096. Wildcard- and term-heavy queries can fail
either way. A query that worked at the source may be too wide at the target,
or a re-tuned target query may be too narrow on a fallback path.

**Detect:** Application uses generated `terms`/`should` clauses with
unbounded list size.

**Fix:** Cap clauses application-side, OR set `indices.query.bool.max_clause_count`
on AOS (advanced cluster settings, requires blue/green).

## 11. Cross-AZ data-transfer with Multi-AZ-with-Standby is not free

Replication from primary to the standby AZ bills at **$0.01/GB each way**.
On a 100 MB/s steady ingest cluster this is ~$5,200/mo of "invisible" cost.
Most TCO models forget it.

**Detect:** Target requires Multi-AZ-with-Standby (high availability or
99.99% SLA).

**Fix:** Project it explicitly using the ingest rate × 2 (in + out) × 730 hr.

## 12. AOS-managed gp3 storage is ~52% above raw EBS gp3

The list price for `aos-storage-gp3` includes the volume + provisioned-IOPS
baseline + management overhead. Most TCO calculators reuse the raw EBS rate
and underestimate by half.

**Detect:** Hand-built TCO spreadsheet.

**Fix:** Use the AOS-managed gp3 rate (e.g., us-east-1 = $0.122/GB-mo, not
$0.080). See `references/pricing-data.md`.

## 13. AOSS minimum is 4 OCUs (a.k.a. 4 half-OCUs)

The 2024 reduction made the unit 0.5 OCU, but the floor for a redundant
collection is still **2 indexing + 2 search OCUs** (= 4 × 0.5 with redundancy).
Roughly **$691/mo us-east-1 floor per collection** even idle. With redundancy
off and persistence-only, 0.5 + 0.5 ≈ $174/mo.

**Detect:** Bursty/low-volume user thinking "I'll only pay for what I use".

**Fix:** Quote both floors. Consider t3.small.search managed (~$26/mo) for
truly tiny workloads.

[Half-OCU blog](https://aws.amazon.com/blogs/big-data/amazon-opensearch-serverless-cost-effective-search-capabilities-at-any-scale/)

## 14. OSI persistent buffering steals OCUs from your declared max

With persistent buffering enabled, OSI consumes Ingestion-OCUs from the same
budget as the data flow. A pipeline with `max_units: 10` and persistence on
may only have 6–7 OCUs available for actual processing. Stateful pipelines
also cap at **48 OCU** vs **96 OCU** stateless.

**Detect:** Throughput plan assumes full `max_units` is available for ingest.

**Fix:** Raise `max_units` accordingly. Pre-test under load.

[OSI features](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/osis-features-overview.html)

## 15. NAT Gateway charges on private VPC clusters

A 3-AZ private cluster fetching plugins, Bedrock embeddings, IDP metadata,
or external knowledge sources easily racks up **>$300/mo NAT charges** before
data egress. Most TCO models forget the NAT.

**Detect:** Target is in a private VPC subnet AND any external HTTP(S) is
expected (Bedrock KB, third-party IDP, plugin fetch, OSI external sources).

**Fix:** VPC endpoints for S3, Bedrock, STS, OpenSearch Service. Project
remaining NAT cost at $0.045/hr/AZ + $0.045/GB processed.

## 16. UltraWarm cache, not attached storage

OR1/OR2/OM2/OI2 UW nodes use S3 + node-local cache (80% of local). The number
that matters for capacity planning is **max addressable warm = 5× cache size**,
not the local SSD. Treat ultrawarm1.large.search as 20 TiB warm capacity, not
1.5 TiB SSD.

[Limits](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/limits.html)

## 17. OR1 indexing throughput ≈ 2× r6g, replica = 1

OR1 stores segments in S3 as primary, with local NVMe as cache. **One replica
is enough** for durability — the classic 2-replica r6g pattern is unnecessary.
Net TCO drops ~40% on indexing-heavy workloads. Loses to r-family on cache-miss
aggregations and on k-NN graphs (RAM-bound).

**Detect:** `peak_indexing_rate_docs_s` is dominant cost driver, not query latency.

**Fix:** Recommend OR1 if `peak_indexing_rate_docs_s` × `avg_doc_size_kb` > 50
GB/day/node target.

## 18. Manual snapshot S3 storage is on YOUR bucket

Automated AOS snapshots (14-day retention) are free. Anything beyond — manual
snapshots, custom retention, cross-region replication — bills against a
customer-owned S3 bucket at standard rates ($0.023/GB-mo us-east-1 + PUT
charges during creation).

**Detect:** User says "I want 90-day snapshot retention".

**Fix:** Add S3 storage line to the cost model: `data_size × 90 days / 30 ×
0.023` plus PUT cost ≈ `(snapshot_count × 1000) × $0.005/1000 PUTs`.

## 19. Solr → OpenSearch is document-level, not segment-level

Solr writes Lucene segments, but the *codec* and *schema layout* differ from
ES/OpenSearch. There is **no segment-level migration**. All Solr migrations
are document-level: DIH/SolrJ, `/export` handler → JSON → bulk, or Spark +
spark-solr → OpenSearch Spark connector.

**Detect:** User asks "can I just copy the Solr index files?".

**Fix:** Recommend Spark+spark-solr+opensearch-spark for TB-scale; `/export`
handler for 100 GB-2 TB; SolrJ cursorMark for <100 GB. See
`references/migration-paths.md`.

## 20. AOSS does not support `repository-s3` / `_snapshot`

You cannot bring an existing snapshot into AOSS. The migration paths into
AOSS are: Migration Assistant (with the AOSS-mode sanitizer), OSI pull
pipelines, Logstash, or direct application bulk. Plan accordingly.

**Detect:** Target = AOSS AND user has snapshots in S3.

**Fix:** Migration Assistant Metadata + RFS to a *managed* AOS, validate,
THEN reindex-from-remote into AOSS — or skip the intermediate hop and use
OSI's S3 source.
