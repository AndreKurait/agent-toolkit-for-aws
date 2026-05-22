---
name: assessing-search-engine-migration
description: >-
  Assess and recommend a migration from Apache Solr, Elasticsearch, or
  self-managed OpenSearch to Amazon OpenSearch Service or Amazon OpenSearch
  Serverless. Profiles the source, picks Service vs Serverless, picks the
  migration mechanism (AWS Migration Assistant, snapshot-restore, OSI, or
  Spark/EMR), prices both targets across regions including GovCloud, and
  produces a written assessment plan with citations.
  Triggers on: assess Solr migration, evaluate Elasticsearch to OpenSearch,
  plan OpenSearch migration, OpenSearch Service vs Serverless, Migration
  Assistant, snapshot restore to OpenSearch, OSI ingestion, EMR reindex,
  OpenSearch pricing, migration cost estimate, OR1 vs r6g, AOSS OCU sizing.
  Do NOT use for executing the migration itself (use Migration Assistant or
  the AWS Transform skill), for query/schema translation (use the upstream
  solr-opensearch-migration-advisor), or for non-search workloads
  (DynamoDB, RDS, Redshift, etc.).
metadata:
  author: AndreKurait
  version: 0.2.0
  capability: migration-assessment
---

# Assessing Search Engine Migration to Amazon OpenSearch

This skill produces a defensible, evidence-backed migration assessment.
It does not execute the migration.

The deliverable: a written plan covering target choice (Service vs
Serverless), migration mechanism, sizing, pricing across regions, plugin
compatibility, hidden costs, risks, and a cutover strategy — every
non-obvious claim cited against the AWS Knowledge MCP Server.

## Progressive disclosure

This SKILL.md is the lean front matter. Read it first. The deep references
are loaded **on demand** by phase. Do not read everything upfront.

| When | Load |
|---|---|
| Start | This file + `references/knowledge-retrieval.md` (fetch-vs-embed map + live MCP recipes) |
| Phase 1-2 | `references/source-profile.md` |
| Phase 3 (target choice) | `references/target-decision-matrix.md` + `references/aoss-deep-dive.md` (if AOSS candidate) + `references/vector-search.md` (if vectors involved) |
| Phase 4 (migration mechanism) | `references/migration-paths.md` + `references/migration-assistant.md` |
| Phase 5 (sizing) | `references/sizing.md` + `references/or1-and-tiers.md` (if logs/observability) |
| Phase 6 (pricing) | `references/pricing-data.md` + `references/real-world-tco.md` |
| Phase 7 (risks) | `references/nuggets.md` + `references/plugin-compatibility-matrix.md` |
| Throughout | `references/aws-knowledge-integration.md` for live citations |

## Fetch live, don't trust stale embeddings

This skill embeds decision logic, sizing math, and structural prose. It
does **not** embed factual lookup tables that AWS owns and updates on
its own cadence. Always retrieve the following from the AWS Knowledge
MCP server (`https://knowledge-mcp.global.api.aws`) instead of trusting
the snapshot files in `references/`:

- Plugin compatibility matrix (use `aws___read_documentation` on the
  supported-plugins page)
- FedRAMP / regional availability claims (use
  `aws___get_regional_availability` with `resource_type=product`)
- Current pricing numbers (use `aws___read_documentation` on the
  pricing page; reconcile against the embedded snapshot)
- Migration Assistant supported sources (search + read)
- OR1 / OR2 / OI2 / UltraWarm specs and limitations (read live)
- Vector / k-NN current limits

Full per-area recipes (verified against the live endpoint) are in
`references/knowledge-retrieval.md`. The probe at
`scripts/probe_aws_knowledge_mcp.py` confirms all six MCP tools are
reachable; run it before an assessment if you suspect schema drift.

## Philosophy

- **Cite every recommendation.** Every non-obvious claim about Amazon
  OpenSearch Service, Amazon OpenSearch Serverless, OSI, or Migration
  Assistant must be backed by a fresh lookup against the AWS Knowledge
  MCP Server (`https://knowledge-mcp.global.api.aws`). Inline the URL in
  the report. See `references/aws-knowledge-integration.md`.
- **Estimates are estimates.** Sizing and pricing numbers come from
  documented formulas; always state assumptions and tell the user how to
  validate via the AWS Pricing Calculator and the AWS MCP Server `pricing`
  query. See `steering/accuracy.md`.
- **Pick a path, give the trade-offs.** Don't shrug between options.
  Recommend one mechanism per workload with a clear rationale; list the
  rejected alternatives with why.
- **Stay in scope.** This skill assesses; it does not execute. When the
  user is ready to run the migration, hand off to AWS Migration
  Assistant docs or the upstream `solr-opensearch-migration-advisor`.

## When to use

Trigger phrases: "assess my Solr/Elasticsearch/OpenSearch migration",
"should I move to OpenSearch Service or Serverless", "Migration Assistant
vs snapshot restore", "estimate OpenSearch cost", "plan a search migration",
"OpenSearch Ingestion vs EMR reindex", "review my migration plan", "OR1 vs
r6g for logs", "AOSS OCU sizing".

Do NOT use this skill for:

- Executing the migration (Migration Assistant docs and the AWS Transform
  skill cover that).
- Solr schema/query translation deep-dives — use the upstream
  `solr-opensearch-migration-advisor`.
- Non-search workloads (RDS, Redshift, DynamoDB, etc.).

## Prerequisites (run once per session)

### 1. AWS Knowledge MCP Server

Public, no-auth endpoint at `https://knowledge-mcp.global.api.aws`. You
MUST use it for documentation lookups. If configured, call
`aws___search_documentation` and `aws___read_documentation` (tool names
vary by runtime). If not configured, fall back to the curated link table
in `references/aws-knowledge-integration.md` and tell the user the live
MCP would be more current.

### 2. AWS MCP Server (optional, live pricing + account context)

If configured (see this repo's README), prefer it for:

- `pricing.get_products` — canonical instance-hour and EBS pricing.
- `aoss.list_collections` / `es.describe_domain` — what's already deployed.
- `sts.get_caller_identity` — confirm the account/region.

If unavailable, use the offline pricing estimator and note the limitation.

### 3. Account context (ask once, store as `facts.account_context`)

- Target AWS region (default `us-east-1`).
- Whether environment is FedRAMP / GovCloud (changes service availability
  and pricing — typical 22% uplift).
- Compliance constraints (FIPS 140-3, HIPAA, PCI) that affect
  Service-vs-Serverless choice.

## Workflow

Walk these phases stepwise. Each phase produces a fact table the next
phase reads. Confirm derived assumptions with the user before proceeding.

### Phase 1 — Intake

Open with:

> "I'll help you assess a migration to Amazon OpenSearch Service or Amazon
> OpenSearch Serverless. First, what are you migrating from — Apache Solr,
> Elasticsearch, or self-managed OpenSearch — and what's your primary goal?
> (cut cost, exit end-of-life, scale up, exit on-prem, simplify ops, etc.)"

Capture under `facts.intake`:

- `source_engine` ∈ {`solr`, `elasticsearch`, `opensearch`}.
- `source_version` — major.minor (probe later if unknown).
- `primary_goal` — free text plus a tag from {`cost`, `eol`, `scale`,
  `on_prem_exit`, `ops_simplification`, `compliance`, `feature_gap`}.
- `business_criticality` — `low` / `medium` / `high`.

If `source_engine == solr`, note the upstream
[solr-opensearch-migration-advisor](https://github.com/opensearch-project/opensearch-migrations/tree/main/AIAdvisor/skills/solr-opensearch-migration-advisor)
covers schema and query translation — this skill complements it on the
AWS-side assessment.

### Phase 2 — Source profile

Build a structured profile. Load `references/source-profile.md` for the
full questionnaire. Validate with:

```bash
python3 scripts/source_assessor.py validate --profile-json /tmp/source-profile.json
```

For unknowns, infer a plausible range — never silently guess. Confirm
inferences before storing.

### Phase 3 — Target choice (Service vs Serverless)

Run:

```bash
python3 scripts/decision_engine.py target --profile-json /tmp/source-profile.json
```

Returns: `aoss-time-series` / `aoss-search` / `aoss-vector` /
`service-general` / `service-large-scale` / `service-ultrawarm` with a
ranked second choice and the matched rules.

Load `references/target-decision-matrix.md` for rule explanations. If the
candidate is AOSS, also load `references/aoss-deep-dive.md`. If any
vector/`knn_vector` workload is mentioned, load `references/vector-search.md`.

For each rule that fired, retrieve a citation via the AWS Knowledge MCP
Server and inline it. Canonical queries are in
`references/aws-knowledge-integration.md`.

If both targets fit, recommend the cheaper one for the projected
steady-state load (Phase 6) and call out the break-even.

Store under `facts.target` with the rule trace.

### Phase 4 — Migration path

Load `references/migration-paths.md`. Quick-look:

| Path | Wins when | Key constraint |
|---|---|---|
| **AWS Migration Assistant** (default) | ES 5.x-8.x or OS 1.x-3.x source; need backfill + cutover | Source must be supported version |
| **Snapshot-and-restore** | OS→OS or ES 7+→OS, simple/cheap | Version compatibility matrix |
| **OpenSearch Ingestion (OSI)** | Continuous CDC, transformations, native AWS sources (DDB/S3/MSK) | Cost; not ideal for huge backfill |
| **Direct from source (Spark/EMR)** | Solr; bespoke transforms; sources MA doesn't support | You own operator effort |

Run:

```bash
python3 scripts/decision_engine.py path --profile-json /tmp/source-profile.json
```

The engine emits matched rules, rejected alternatives, and per-rule
"validate this with AWS Knowledge" query strings. Use them verbatim and
inline the citations.

For Migration Assistant deep-dive (architecture, RFS throughput,
capture-replay, console CLI), load `references/migration-assistant.md`.

Store under `facts.migration_path`.

### Phase 5 — Sizing

Load `references/sizing.md`. If logs/observability or >50 GB/day/node
ingest is suggested, also load `references/or1-and-tiers.md`.

Run:

```bash
python3 scripts/pricing_estimator.py size \
  --profile-json /tmp/source-profile.json \
  --target $(jq -r .target /tmp/facts.json)
```

Sizing rules (10-50 GB shards, ≤32 GB heap, ≥3 cluster manager nodes,
+30% storage overhead, +25% headroom, replica count, OCU floor for
Serverless) are codified in the script. Always state assumptions in the
final report.

Store under `facts.sizing`.

### Phase 6 — Pricing

Load `references/pricing-data.md` for the embedded list-price tables.
Load `references/real-world-tco.md` for hidden cost line items, RI
discounts, GovCloud uplift, and three reference case studies (Yelp,
Sumo Logic, Adobe).

Run:

```bash
python3 scripts/pricing_estimator.py price \
  --profile-json /tmp/source-profile.json \
  --target $(jq -r .target /tmp/facts.json) \
  --region $(jq -r .account_context.region /tmp/facts.json)
```

Emits low / mid / high monthly cost ranges for the recommended target
plus the runner-up, broken down by:

- Compute (instance hours or OCU hours).
- Storage (gp3 EBS for Service — note the AOS-managed premium; per-GB for
  Serverless and managed storage).
- Data transfer (cross-AZ replication for Multi-AZ-with-Standby,
  ingestion, dashboards).
- Migration-period costs (Migration Assistant infra, OSI pipeline OCU,
  EMR cluster).

Always tell the user to confirm against the live
[AWS Pricing Calculator](https://calculator.aws) and, if available, the
AWS MCP Server `pricing` API. See `steering/accuracy.md`.

Store under `facts.pricing`.

### Phase 7 — Risks & pros/cons

Load `references/nuggets.md` (the hidden-gotcha catalog) and
`references/plugin-compatibility-matrix.md`.

For each major decision (target choice, migration path, sizing, security,
plugin/feature gaps), record a row in `facts.risks`:

```yaml
- decision: "Recommend Amazon OpenSearch Serverless TIME_SERIES collection"
  pros:
    - "Zero cluster ops; auto-scales on ingest and query."
    - "Built-in S3-backed durability."
  cons:
    - "OCU floor (~$691/mo us-east-1) — small/idle workloads pay more
       than a t3.small.search domain."
    - "TIME_SERIES rejects custom _id PUT/upsert (nugget #1)."
    - "No custom plugins; LTR / Anomaly Detection unavailable."
  citation: "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-supported.html"
  mitigation: "Quantify break-even at projected QPS — see pricing table."
```

Cross-check against `references/nuggets.md` — if the source profile
matches any of the 20 nuggets, add a risk row referencing it.

### Phase 8 — Final report

```bash
python3 scripts/source_assessor.py report \
  --facts /tmp/facts.json \
  --out /tmp/migration-assessment.md
```

The report contains:

1. Executive summary (one paragraph: target + path + cost band).
2. Source profile.
3. Target recommendation with rule trace and citations.
4. Migration path recommendation with pros/cons of all four paths.
5. Sizing.
6. Pricing (steady-state + migration period).
7. Risk register (cross-referenced to nuggets).
8. Cutover & rollback plan.
9. Validation checklist (what to sanity-check before commitment).
10. Appendix: every AWS Knowledge MCP query used with its citation URL.

Hand the user the file path and offer to walk through any section.

## Tools shipped with this skill

| File | Purpose |
|---|---|
| `scripts/source_assessor.py` | Profile validation; final report rendering |
| `scripts/decision_engine.py` | Target and path decision (rule-based, deterministic) |
| `scripts/pricing_estimator.py` | Sizing math and monthly cost estimation |
| `scripts/pricing_data.json` | Multi-region price data (us-east-1, us-west-2, eu-west-1, ap-southeast-1, ap-south-1, us-gov-west-1) |

All scripts are stdlib-only, exit non-zero on validation failure, and have
unit tests under `tests/`. End-to-end LLM evaluations live under `evals/`
(promptfoo for portable runs; `evals/run_bedrock.py` for native AWS
Bedrock validation against Claude on Amazon Bedrock).

## Hand-offs

- **Solr schema/query translation** — `solr-opensearch-migration-advisor`
  (upstream OpenSearch project).
- **Executing the migration** — [AWS Migration Assistant for OpenSearch](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/migration.html);
  for code-level changes, the `aws-transform` skill.
- **Live cluster operations** — Amazon OpenSearch Service console + AWS
  MCP Server.
