# Plugin Compatibility — Decision Rules

> **Live data first.** The full plugin-by-version table and AOSS allowlist
> are maintained in AWS docs and read live via MCP — do not embed snapshots:
>
> ```jsonc
> // Full AOS plugin × OpenSearch version table
> { "tool": "aws___read_documentation",
>   "args": { "url": "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/supported-plugins.html",
>             "max_length": 6000 } }
>
> // AOSS supported operations + plugin subset
> { "tool": "aws___read_documentation",
>   "args": { "url": "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-genref.html",
>             "max_length": 6000 } }
>
> // Custom (ZIP) plugin upload story
> { "tool": "aws___read_documentation",
>   "args": { "url": "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/custom-plugins.html",
>             "max_length": 4000 } }
> ```

This file augments the live data with **decision rules** the docs don't
articulate.

## Decision rules (the assessor's job, not in the docs)

1. Source uses **any AOS-only plugin** (alerting, anomaly-detection, ISM,
   security-analytics, async-search, LTR, notifications, observability UI,
   performance-analyzer, reporting, cross-cluster-replication) →
   **AOSS is OFF the table.** Recommend AOS managed.

2. Source uses **any custom Java plugin** (third-party, in-house, forked) →
   both AOS and AOSS reject. Reimplement as ingest pipeline, OSI processor,
   Lambda, or external service.

3. Source uses **X-Pack ML, X-Pack Watcher, or X-Pack Graph** → factor
   rewrite cost into the plan regardless of target. Watcher → Alerting
   monitor JSON is a translation, not a port.

4. Source uses **only language analyzers + ICU + mappers + painless** →
   green light on either target. AOSS allows inline Painless but blocks
   stored scripts (`/_scripts`).

5. Source uses **dictionary-driven analysis** (Sudachi, Hunspell, custom
   synonyms/stopwords) → AOS managed (custom packages via Console
   "Packages"). AOSS does not support custom packages.

## X-Pack → OpenSearch port-cost cheat sheet

When the live AWS docs identify the OpenSearch equivalent, these are the
**rewrite-cost signals** to surface in the report:

- X-Pack Watcher → opensearch-alerting Monitor — **schema differs**, rewrite
  is mechanical but not zero-cost. Estimate ~1 day per 10 watchers.
- X-Pack ML → anomaly-detection + ML Commons — feature-equivalent for
  detector use cases; supervised ML jobs require ML Commons model upload.
- X-Pack Transforms → OpenSearch Transforms — subset of source feature set;
  audit each transform definition.
- X-Pack Graph → no direct replacement — flag as a re-architecture item.
- X-Pack SQL → opensearch-sql + PPL — usually drop-in.
- X-Pack Beats → OpenTelemetry Collector / Data Prepper / OSI — pipeline
  migration is a separate workstream.

## Plugin name disambiguation

When the source cluster reports a plugin via `_cat/plugins`, normalize to
the AWS-side name before checking compatibility:

- `analysis-icu` / `analysis-kuromoji` / `analysis-smartcn` /
  `analysis-stempel` / `analysis-nori` / `analysis-phonetic` /
  `analysis-ukrainian` — preinstalled on both AOS and AOSS.
- `mapper-size`, `mapper-murmur3`, `mapper-annotated-text` — preinstalled
  on both.
- `repository-s3` — present on AOS for managed snapshots; **`_snapshot` API
  is blocked on AOSS** (RFS bulk-writes instead of restoring).
- `ingest-attachment` — AOS only; replace with OSI `parse_json` or external
  Tika sidecar for AOSS targets.
