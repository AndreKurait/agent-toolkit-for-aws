---
name: assessing-search-engine-migration
description: >-
  Assess and recommend a migration path from Apache Solr, Elasticsearch, or self-managed OpenSearch
  to Amazon OpenSearch Service or Amazon OpenSearch Serverless. Profiles the source cluster,
  scores Service-vs-Serverless suitability, picks a migration mechanism (AWS Migration Assistant
  for OpenSearch, snapshot-and-restore, OpenSearch Ingestion / OSI, or direct from source via
  Spark on EMR), surfaces pros and cons, calls the AWS Knowledge MCP Server for authoritative
  documentation references on every claim, and produces a sized, priced migration plan.
  Triggers on: assess Solr migration, evaluate Elasticsearch to OpenSearch, plan OpenSearch
  migration, OpenSearch Service vs Serverless, Migration Assistant, snapshot restore to
  OpenSearch, OSI ingestion, EMR reindex, OpenSearch pricing, migration cost estimate.
  Do NOT use for executing the migration itself (use Migration Assistant or AWS Transform skill),
  for query/schema translation (use the upstream solr-opensearch-migration-advisor),
  or for non-search workloads (DynamoDB, RDS, Redshift, etc.).
metadata:
  author: AndreKurait
  version: 0.1.0
  capability: migration-assessment
---

# Assessing Search Engine Migration to Amazon OpenSearch

Produce a defensible, evidence-backed migration plan that recommends:

1. **Target service** — Amazon OpenSearch Service (managed cluster) or Amazon OpenSearch Serverless (collection),
   plus any complementary services (e.g. OpenSearch Ingestion / OSI, Amazon S3, Amazon EMR, Amazon MSK).
2. **Migration mechanism** — Migration Assistant for OpenSearch (the recommended default for ES/OS sources),
   snapshot-and-restore, OSI pull pipelines, or a custom direct-from-source reindex (typically Spark on EMR).
3. **Sizing and pricing** — instance shape, node count, storage, plus monthly cost ranges for both targets.
4. **Risks and pros/cons** — each finding linked to a citation from the AWS Knowledge MCP Server.

This is an **assessment skill**: the deliverable is a written plan, not an executed migration.

## Philosophy

- **Cite every recommendation.** Every non-obvious claim about Amazon OpenSearch Service, Amazon
  OpenSearch Serverless, OSI, or Migration Assistant MUST be backed by a fresh lookup against the
  AWS Knowledge MCP Server (`https://knowledge-mcp.global.api.aws`). Inline the URL in the report.
  See [references/aws-knowledge-integration.md](references/aws-knowledge-integration.md).
- **Estimates are estimates.** Sizing and pricing numbers are produced from public, documented
  formulas; always state the assumptions and tell the user how to validate them with the AWS
  Pricing Calculator and an AWS MCP Server `pricing` query. See [steering/accuracy.md](steering/accuracy.md).
- **Pick a path, give the trade-offs.** Don't shrug between options — recommend one mechanism
  per workload with a clear rationale, and list the rejected alternatives with why.
- **Stay in scope.** This skill assesses; it does not execute. When the user is ready to run the
  migration, hand off to the AWS Migration Assistant docs or the upstream
  `solr-opensearch-migration-advisor` skill for Solr-specific schema/query translation.

## When to Use

Trigger phrases: "assess my Solr/Elasticsearch/OpenSearch migration", "should I move to OpenSearch
Service or Serverless", "Migration Assistant vs snapshot restore", "estimate OpenSearch cost",
"plan a search migration", "OpenSearch Ingestion vs EMR reindex", "review my migration plan".

Do NOT use this skill for:

- Executing the migration (Migration Assistant docs and the AWS Transform skill cover that).
- Solr schema/query translation deep-dives — use the upstream `solr-opensearch-migration-advisor`.
- Non-search workloads (RDS, Redshift, DynamoDB, etc.).

## Prerequisites

Run prerequisite checks ONCE per session, only after the user has stated what they want to assess.

### 1. AWS Knowledge MCP Server

The AWS Knowledge MCP Server is a public, no-auth endpoint exposed at
`https://knowledge-mcp.global.api.aws`. You MUST use it for every documentation lookup performed
by this skill. If the user's agent has it configured, use the tools `aws___search_documentation`
and `aws___read_documentation` (names vary by agent runtime). If not configured, fall back to the
[references/aws-knowledge-integration.md](references/aws-knowledge-integration.md) curated link
table — but tell the user the live MCP would be more up to date.

### 2. AWS MCP Server (optional, for live pricing and account-aware checks)

If the user has the AWS MCP Server configured (see this repo's README), prefer it for:

- `pricing.get_products` — canonical instance-hour and EBS pricing.
- `aoss.list_collections` / `es.describe_domain` — to see what is already deployed in the account.
- `sts.get_caller_identity` — to confirm the right account/region before producing region-specific costs.

If unavailable, proceed with the offline pricing estimator (see Step 6) and note the limitation.

### 3. AWS account context

Ask the user once:

- Target AWS region (default `us-east-1` if they have no preference).
- Whether the target environment is FedRAMP / GovCloud (changes service availability and pricing).
- Anything compliance-driven (FIPS 140-3, HIPAA, PCI) that constrains the choice of Service vs Serverless.

Store under `facts.account_context`. Don't ask again.

## Workflow

Walk the user through these phases stepwise. Do not skip — each phase produces a fact table that
the next phase reads. Confirm derived assumptions with the user before proceeding.

### Phase 1 — Intake

Open the conversation with:

> *"I'll help you assess a migration to Amazon OpenSearch Service or Amazon OpenSearch Serverless.
> First, what are you migrating from — Apache Solr, Elasticsearch, or self-managed OpenSearch — and
> what's your primary goal? (cut cost, exit end-of-life, scale up, exit on-prem, simplify ops, etc.)"*

Capture under `facts.intake`:

- `source_engine` — one of `solr`, `elasticsearch`, `opensearch`.
- `source_version` — major.minor (probe later if unknown).
- `primary_goal` — free text plus a tag from {`cost`, `eol`, `scale`, `on_prem_exit`, `ops_simplification`, `compliance`, `feature_gap`}.
- `business_criticality` — `low` / `medium` / `high` (drives RPO/RTO targets later).

If `source_engine == solr`, note that the upstream
[solr-opensearch-migration-advisor](https://github.com/opensearch-project/opensearch-migrations/tree/main/AIAdvisor/skills/solr-opensearch-migration-advisor)
covers schema and query translation in much greater depth — this skill complements it by handling
the AWS-side assessment.

Move to Phase 2.

### Phase 2 — Source Profile

Build a structured profile of the source cluster. See [references/source-profile.md](references/source-profile.md)
for the full questionnaire and how to interpret answers.

Collect the following into `facts.source`:

| Field | Why it matters |
|---|---|
| `cluster_topology` (nodes, dedicated coordinators, ZK ensemble for Solr) | Drives target node count and whether to keep a coordinating tier |
| `index_or_collection_count` | Drives shard math and Serverless suitability |
| `total_data_size_gb` (primary copy) | Storage cost, snapshot duration, OSI throughput |
| `total_doc_count` | Throughput and refresh interval planning |
| `peak_indexing_rate_docs_s` | Ingestion strategy (OSI vs MA backfill) |
| `peak_query_rate_qps` | OCU sizing for Serverless, replica count for Service |
| `query_latency_p95_ms` | Tier choice and Serverless OCU minimums |
| `update_pattern` (`append_only`, `mutable`, `bulk_reindex`) | Serverless time-series suitability |
| `retention_pattern` (`fixed`, `sliding_window`, `time_partitioned`) | Time-series workload type |
| `auth_model` | Affects target Security configuration and migration headers |
| `kibana_or_dashboards_usage` | Whether to enable OpenSearch Dashboards |
| `plugins_in_use` | Compatibility — see [references/source-profile.md](references/source-profile.md) §Plugin compatibility |

Use the offline helper to validate the profile shape:

```bash
python3 scripts/source_assessor.py --profile-json /tmp/source-profile.json
```

For each piece of data the user can't provide, mark it as `unknown` and infer a plausible
range — never silently guess. Confirm inferences with the user before storing them.

Move to Phase 3.

### Phase 3 — Target Choice (Service vs Serverless)

Run the decision engine:

```bash
python3 scripts/decision_engine.py target --profile-json /tmp/source-profile.json
```

The engine returns one of: `aoss-time-series`, `aoss-search`, `aoss-vector`, `service-general`,
`service-large-scale`, `service-ultrawarm`, with a ranked second choice and the matched rules.

The decision rules are documented in
[references/target-decision-matrix.md](references/target-decision-matrix.md). Summary:

- **Amazon OpenSearch Serverless** wins when the workload is bursty, the team wants
  zero ops, the use case fits a supported collection type (search / time-series / vector),
  and there are no hard blockers (custom plugins, advanced ISM, sub-100 GB-per-OCU price-floor concerns).
- **Amazon OpenSearch Service (managed cluster)** wins for steady-state, large-data, plugin-heavy,
  cost-optimized at scale, or feature-rich workloads (ISM with custom transitions, SQL/PPL,
  cross-cluster replication, custom packages, snapshot policies, anomaly detection, learning to rank, etc.).

For each rule that fired, retrieve a citation from the AWS Knowledge MCP Server and inline it
in the recommendation:

```text
Tool: aws___search_documentation
Query: "Amazon OpenSearch Serverless supported collection types"
```

See [references/aws-knowledge-integration.md](references/aws-knowledge-integration.md) for the full
list of canonical queries this skill expects.

If both targets fit, recommend the cheaper one for the projected steady-state load (see Phase 6),
and call out the break-even point in writing.

Store the decision under `facts.target` with the rule trace.

Move to Phase 4.

### Phase 4 — Migration Path

Pick the migration mechanism. The four supported paths and when each wins are documented at
[references/migration-paths.md](references/migration-paths.md). Quick-look summary:

| Path | When it wins | Key constraint |
|---|---|---|
| **AWS Migration Assistant for OpenSearch (MA)** | Default for Elasticsearch 5.x–8.x and OpenSearch 1.x–3.x sources. Supports backfill via Reindex-from-Snapshot (RFS) plus optional capture-and-replay or live-replay for cutover. | Source must be one of the supported engine versions. |
| **Snapshot-and-restore** | Same-engine, same-or-newer-major-version OpenSearch→OpenSearch (or recent ES→OS via repository-s3). Cheapest. | Version compatibility matrix; no in-flight transformation. |
| **OpenSearch Ingestion (OSI)** | Steady-state replication or zero-downtime cutover with transformations; adding fields, renaming indices, persistent CDC from a source. | Ingest throughput cost; not a backfill tool by itself for very large historic data. |
| **Direct from source (Spark on EMR / Glue / Lambda)** | Solr sources where MA does not apply, very custom transforms, or pulling from a system MA does not yet support (vector DBs, niche ES forks). | You own the operator effort. |

Run:

```bash
python3 scripts/decision_engine.py path --profile-json /tmp/source-profile.json
```

For each candidate path, the engine emits the rules that matched, the rejected alternatives, and a
"validate this with AWS Knowledge" query string. Use those queries verbatim against the AWS
Knowledge MCP Server and inline the citation.

Capture under `facts.migration_path`.

Move to Phase 5.

### Phase 5 — Sizing

Use [references/sizing.md](references/sizing.md) plus the offline calculator:

```bash
python3 scripts/pricing_estimator.py size \
  --profile-json /tmp/source-profile.json \
  --target $(jq -r .target facts.json)
```

The sizing rules (10–50 GB shards, ≤32 GB heap, ≥3 cluster manager nodes, +30% storage overhead,
+25% headroom, replica count, OCU-min for Serverless) are codified in the script and explained in
the reference. Always state the assumptions in the final report.

Store sizing under `facts.sizing`.

Move to Phase 6.

### Phase 6 — Pricing

Run the pricing estimator:

```bash
python3 scripts/pricing_estimator.py price \
  --profile-json /tmp/source-profile.json \
  --target $(jq -r .target facts.json) \
  --region $(jq -r .account_context.region facts.json)
```

The estimator emits a low / mid / high monthly cost range for the recommended target plus the
runner-up, broken down by:

- Compute (instance hours or OCU hours).
- Storage (gp3 / io2 EBS for Service; per-GB for Serverless and managed storage).
- Data transfer (cross-AZ replication, ingestion, dashboards).
- Migration-period costs (Migration Assistant infra, OSI pipeline OCU, EMR cluster).

Pricing data is sourced from the embedded list-price tables in
[references/pricing-data.md](references/pricing-data.md), which are curated from public AWS pricing
pages. ALWAYS instruct the user to confirm with the live
[AWS Pricing Calculator](https://calculator.aws) and, if available, query the AWS MCP Server's
`pricing` API for canonical figures. See [steering/accuracy.md](steering/accuracy.md).

Store pricing under `facts.pricing`.

Move to Phase 7.

### Phase 7 — Risks & Pros/Cons

For each major decision (target choice, migration path, sizing assumptions, security model,
plugin/feature gaps), record a row in `facts.risks`:

```yaml
- decision: "Recommend Amazon OpenSearch Serverless time-series collection"
  pros:
    - "Zero cluster ops; auto-scales on ingest and query."
    - "Built-in S3-backed durability."
  cons:
    - "OCU-minute floor; small/idle workloads will pay more than a t3.small.search domain."
    - "No custom plugins; LTR and Anomaly Detection are not available."
  citation: "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-supported.html"
  mitigation: "Quantify break-even at projected QPS — see pricing table."
```

Use the AWS Knowledge MCP Server for each citation. The expected canonical queries are listed in
[references/aws-knowledge-integration.md](references/aws-knowledge-integration.md).

Move to Phase 8.

### Phase 8 — Final Report

Generate the report:

```bash
python3 scripts/source_assessor.py report --facts /tmp/facts.json --out /tmp/migration-assessment.md
```

The report contains:

1. Executive summary (one paragraph, target + path + cost band).
2. Source profile.
3. Target recommendation with rule trace and citations.
4. Migration path recommendation with pros/cons of all four paths.
5. Sizing.
6. Pricing (steady-state + migration period).
7. Risk register.
8. Cutover & rollback plan.
9. Validation checklist (what the user should sanity-check before commitment).
10. Appendix: every AWS Knowledge MCP query used + its citation URL.

Hand the user the file path and offer to walk through any section in detail.

## Tools & Scripts (this skill ships with these)

| File | Purpose |
|---|---|
| [scripts/source_assessor.py](scripts/source_assessor.py) | Profile validation; final report rendering. |
| [scripts/decision_engine.py](scripts/decision_engine.py) | Target and path decision engines (rule-based, deterministic). |
| [scripts/pricing_estimator.py](scripts/pricing_estimator.py) | Sizing math and monthly cost estimation; reads embedded list-price tables. |

All scripts are stdlib-only, exit non-zero on validation failure, and have unit tests under
[tests/](tests/) plus end-to-end LLM evaluations under [evals/](evals/) (promptfoo).

## References

- [references/source-profile.md](references/source-profile.md) — questionnaire + plugin compatibility.
- [references/target-decision-matrix.md](references/target-decision-matrix.md) — Service vs Serverless rules.
- [references/migration-paths.md](references/migration-paths.md) — MA / snapshot / OSI / EMR pros & cons.
- [references/sizing.md](references/sizing.md) — sizing formulas (mirrors the upstream Solr advisor's `steering/sizing.md`, adapted for AWS-managed hosts and Serverless OCUs).
- [references/pricing-data.md](references/pricing-data.md) — embedded list-price tables and the freshness policy.
- [references/aws-knowledge-integration.md](references/aws-knowledge-integration.md) — canonical AWS Knowledge MCP queries.
- [steering/accuracy.md](steering/accuracy.md) — what counts as an estimate, how to label them.
- [steering/scope.md](steering/scope.md) — what this skill does and does not do.
- [steering/assumptions.md](steering/assumptions.md) — required disclosures and default assumptions.

## Hand-offs

- **Solr schema / query translation** — `solr-opensearch-migration-advisor` (upstream OpenSearch project).
- **Executing the migration** — [AWS Migration Assistant for OpenSearch](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/migration.html); for code-level changes, the [`aws-transform`](../aws-transform/) skill.
- **Live cluster operations** — Amazon OpenSearch Service console + AWS MCP Server.
