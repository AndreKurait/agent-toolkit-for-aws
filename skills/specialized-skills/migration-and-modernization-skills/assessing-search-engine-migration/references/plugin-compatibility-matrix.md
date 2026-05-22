# Plugin Compatibility Matrix

Y = available · P = partial · N = not available

Use this as a fast filter when the user lists their installed plugins.

| Plugin | AOS | AOSS | Notes |
|---|---|---|---|
| opensearch-knn | Y | P | AOSS: VECTORSEARCH collection only |
| opensearch-ml (ML Commons) | Y | Y | `_plugins/_ml/*` allowlisted on AOSS |
| opensearch-security | Y | N | AOSS uses IAM data-access policies |
| opensearch-anomaly-detection | Y | N | |
| opensearch-asynchronous-search | Y | N | |
| opensearch-cross-cluster-replication | Y | N | Excluded from AOSS |
| opensearch-index-state-management | Y | N | AOSS auto-tiers on TIME_SERIES |
| opensearch-learning-to-rank | Y | N | |
| opensearch-notifications | Y | N | |
| opensearch-observability | Y | P | flow-framework yes; full UI no |
| opensearch-performance-analyzer | Y | N | CloudWatch only on AOSS |
| opensearch-reporting | Y | N | |
| opensearch-sql + PPL | Y | Y | `_plugins/_sql`, `_plugins/_ppl` allowlisted |
| opensearch-security-analytics | Y | N | |
| opensearch-alerting | Y | N | |
| opensearch-geospatial | Y | P | features only through OpenSearch 2.1 |
| repository-s3 | Y | N | `_snapshot` API blocked on AOSS |
| ingest-attachment | Y | TBD | Not in AOSS allowlist; use OSI parse_json or external Tika |
| analysis-icu | Y | Y | Both |
| analysis-kuromoji (Japanese) | Y | Y | Both |
| analysis-smartcn (Chinese) | Y | Y | Both |
| analysis-stempel (Polish) | Y | Y | Both |
| analysis-phonetic | Y | Y | Both |
| analysis-nori (Korean) | Y | Y | Both |
| analysis-ukrainian | Y | Y | Both |
| mapper-size | Y | Y | Both |
| mapper-murmur3 | Y | Y | Both |
| mapper-annotated-text | Y | Y | Bonus on AOSS |
| painless | Y | P | AOSS = inline only; no stored scripts (`/_scripts` blocked) |
| expression / mustache | Y | Y | Both |

## Elasticsearch X-Pack equivalents

| ES X-Pack feature | OpenSearch replacement |
|---|---|
| X-Pack Security | opensearch-security (AOS) / IAM policies (AOSS) |
| X-Pack Watcher | opensearch-alerting (Monitor JSON ≠ Watcher JSON — must rewrite) |
| X-Pack ML | opensearch-anomaly-detection + ML Commons |
| X-Pack Transforms | OpenSearch Transforms (1.x+); subset of ES feature set |
| X-Pack SQL | opensearch-sql + PPL |
| X-Pack Graph | (no direct replacement — community queries / external) |
| X-Pack Beats | OpenTelemetry Collector / Data Prepper / OSI |

## Decision rules

1. Source uses **any** AOS-only plugin → AOSS is OFF the table.
2. Source uses **custom Java plugin** → both AOS and AOSS reject; reimplement
   as ingest pipeline, OSI processor, or Lambda.

3. Source uses **X-Pack ML / Watcher** → factor rewrite cost into the plan
   regardless of target.

4. Source uses **only language analyzers + ICU + mappers** → green light on
   either target.

## Custom packages on AOS managed (ZIP-PLUGIN)

AOS supports uploading ZIP packages for:

- Sudachi dictionaries (Japanese tokenizer).
- Hunspell language packs.
- Custom synonyms / stopwords.

Available via Console "Packages" tab. Not available on AOSS.

[AOS plugins](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/supported-plugins.html) ·
[AOSS plugins](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-genref.html)
