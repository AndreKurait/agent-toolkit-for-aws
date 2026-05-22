## Skill Overview

**Skill name (kebab-case):**
assessing-search-engine-migration

**One-paragraph description:**
Assesses and recommends a migration from Apache Solr, Elasticsearch, or self-managed OpenSearch to Amazon OpenSearch Service (AOS managed) or Amazon OpenSearch Serverless (AOSS). The skill profiles the source workload, picks Service vs Serverless, picks the migration mechanism (AWS Migration Assistant, snapshot-restore, OSI, or Spark/EMR), prices both targets across commercial regions and GovCloud, and produces a written assessment plan with citations to AWS documentation. Volatile facts (plugin compatibility, instance specs, regional availability, current pricing) are fetched live via the AWS Knowledge MCP Server; the skill embeds only decision logic, sizing math, operator-side numbers, and mandatory output disclaimers.

**AWS service(s) involved:**
opensearch-service, opensearch-serverless, opensearch-ingestion (OSI), s3, ec2 (instance pricing), iam (data-access policies), kms, cloudwatch, msk (Migration Assistant traffic-replay), ecs-fargate (Migration Assistant runtime), emr (Spark reindex path), bedrock-knowledge-bases (AOSS VECTORSEARCH integration)

---

## Target Users

**Who is this Skill for?**
Three personas:
1. AWS Solutions Architects and ProServe consultants scoping a search-engine migration for a customer.
2. Customer-side platform/search engineers who own a self-managed Solr or Elasticsearch cluster and need to choose AOS vs AOSS, size it, price it, and pick a migration mechanism.
3. Migration-team operators kicking off a Migration Assistant deployment who need realistic per-worker throughput and pitfalls before committing.

**What are they trying to accomplish?**
Produce a written migration assessment that includes: (a) source profile (versions, plugins, shard count, ingest/query rate, retention), (b) AOS-vs-AOSS recommendation with explicit decision rules, (c) target sizing (instance shape, count, OCU pool minimums, vector RAM math), (d) migration-mechanism choice with realistic wall-clock for the customer's data volume, (e) line-itemized monthly cost estimate including hidden costs (cross-AZ transfer, AOS-managed gp3 premium, snapshot S3, NAT, AOSS floor) with the mandatory pricing disclaimer, and (f) a commercial-region vs GovCloud uplift table when relevant.

**What goes wrong without this Skill?**
Without it, generalist LLMs default to AWS-marketing-shaped answers — "AOSS is cheaper because serverless," "OR1 always wins on cost," "Migration Assistant just works" — and miss the trapdoors: AOSS's $174–$350/mo per-collection floor, the no-shared-OCU rule between VECTORSEARCH and SEARCH, OR1's cache-miss penalty on aggregations and k-NN, the AOS-managed gp3 premium (~52% over raw EBS), the GovCloud uplift (20–28%), the AOS-only plugin list that disqualifies AOSS, and RFS's per-worker throughput ceiling. Cost estimates land within ~5% of reality only when these are surfaced; without the skill they typically come in 30–50% low because the floor / hidden-line-item / replica math is missed.

---

## Ownership

**Owning team:**
<TBD — needs input. Suggest the AWS Migrations / Search team owning Migration Assistant, since their on-call already triages source-eligibility and RFS-throughput questions.>

**Owning CTI:**
<TBD — needs input. Tentative: AWS / OpenSearch / Migration-Assessment, but the actual CTI must come from the owning team.>

**Sev-2 routing confirmation:**
[ ] To be confirmed by owning team. The skill is advisory (it generates assessments, not infrastructure changes), so customer-impacting Sev-2 is unlikely — but a routing confirmation is still required.

**Primary point of contact (alias):**
andrekurait@

**Secondary point of contact (alias):**
<TBD>

---

## Planned Test Cases

The fork already ships 8 Bedrock eval fixtures under `evals/tests/` exercising real user phrasings:

**Positive queries** (the Skill should be selected):
1. "We're running Elasticsearch 7.10 with about 1 TB of data and 200 QPS. What would it cost to move to AWS?"
2. "I have a 50 TB Solr 8.x cluster on-prem with strict latency SLOs. Help me plan an OpenSearch migration."
3. "We need to migrate Elasticsearch to OpenSearch in us-gov-west-1 for FedRAMP. What's the cost uplift and what's not available?"
4. "Should we go OpenSearch Service or Serverless for a Bedrock RAG knowledge base with bursty load?"
5. "Our ES cluster uses Learning-to-Rank. Can we move to AOSS?"
6. "We have 4 PB of logs on r6g hot-only. How much would OR1 + UltraWarm save us?"
7. "How long will Migration Assistant take to move 100 TB from ES 7.17 to AOS?"
8. "Estimate the OCU floor for 5 AOSS collections (3 SEARCH + 2 VECTORSEARCH) in us-east-1."

(Plus the harness-internal `citations-required` and `pricing-disclosure` fixtures that verify every output cites AWS docs and includes the "not a quote" disclaimer.)

**Negative queries** (the Skill should NOT be selected):
1. "Translate this Solr query DSL to OpenSearch query DSL." → routes to upstream `solr-opensearch-migration-advisor`.
2. "Run the Migration Assistant CDK deploy for me." → execution skill, not assessment.
3. "Migrate my DynamoDB table to OpenSearch." → wrong source engine class; not a search-engine migration.
4. "Tune my AOS cluster's heap settings." → ops/tuning skill, not migration assessment.

---

## Evaluation Framework

**Framework choice:**
[X] Other — specify below.

**If "Other", which framework and why:**
The skill ships a native AWS-Bedrock-based eval harness at `evals/run_bedrock.py`. It loads `SKILL.md` + a per-fixture scenario, calls Bedrock InvokeModel directly (no promptfoo, no mocks), and applies regex / icontains / not-icontains assertions defined in YAML under `evals/tests/`. Current sweep: 8/8 PASS on `us.anthropic.claude-haiku-4-5-20251001-v1:0` in us-west-2.

Reasons this is preferred over AWSMCPSkillsEval for this skill specifically:
- The skill is fundamentally about producing long-form written assessments with mandatory disclaimers and citations — the assertion model needs to test for verbatim phrases ("not a quote", "as of YYYY-MM-DD"), regex-shaped patterns (citation URLs), and substring presence/absence at scale, not slot-filling.
- The harness is fixture-driven (YAML), stdlib-only (no promptfoo/Node dependency), and runs with `ada credentials update` against any Bedrock-enabled account in <5 minutes.
- Assertions are rubric-as-code, not exact slug matching — they test meaning, not vocabulary, which matches the "rigorous but realistic" preference for cross-tech migration harnesses.

Happy to port to AWSMCPSkillsEval if the reviewing team requires it; the YAML fixtures translate directly.

Repo: <https://github.com/AndreKurait/agent-toolkit-for-aws> (PR #1 against fork's own main is the active reference).

---

## Existing Coverage Check

**Have you searched AWSMCPSOPs/skills for overlapping Skills?**
[ ] No — fork-only work to date on `AndreKurait/agent-toolkit-for-aws`. Need to do this search before submitting upstream. Best candidates to compare against:
- Anything tagged `migration`, `opensearch`, `elasticsearch`, `search`.
- The upstream `solr-opensearch-migration-advisor` (referenced in the skill's `Do NOT use for...` clause as the query/schema translation owner — this skill is upstream of it in the workflow).

**Closest existing Skill (if any) and how this one differs:**
- `solr-opensearch-migration-advisor` (upstream) — focused on **query and schema translation**, the post-decision execution. This skill sits **before** it: profile-source, decide AOS-vs-AOSS, pick the mechanism, price it, write the plan. The advisor is invoked AFTER the assessment recommends a target. The two are complementary; the SKILL.md `Do NOT use for...` clause routes translation work to the advisor explicitly.
- AWS Migration Assistant skills (if any exist) — focused on **executing** the migration runtime. This skill is **assessment-only**: it tells the user MA is the right mechanism, sizes the worker fleet, and warns about pitfalls, but does not deploy CDK or invoke `console` commands.

---

## Timeline

**Any external dependencies or deadlines:**
None hard-coded. Soft drivers:
- AWS Knowledge MCP Server availability (already GA at https://knowledge-mcp.global.api.aws — 7/7 probe tests pass against the live endpoint).
- Migration Assistant solution version drift (currently supports ES 1.x–8.x, OS 1.x–2.x sources; new source-version support requires updating one fetch-recipe in `references/migration-assistant.md`, no embedded matrix to maintain).
- Pricing snapshot freshness (`scripts/pricing_data.json` exists for deterministic test fixtures only; estimator emits `WARN: pricing data is stale` after 90 days and the report defers to live MCP-fetched prices).

---

## Additional Context

- Repo: <https://github.com/AndreKurait/agent-toolkit-for-aws>
- Active branch: `mcp-first-knowledge-retrieval` @ `3ff1d5c` (HEAD after the aggressive cut + 8/8 Bedrock PASS).
- Prior PR #1 (`assessing-search-engine-migration` → fork's own `main`): open at `e5ed2cc`.
- Design notes worth surfacing for the reviewer:
  - Progressive disclosure: SKILL.md is 348 lines; deep details live in 14 reference files under `references/`, loaded on-demand.
  - Fetch-vs-embed dividing line: volatile + AWS-owned + lookup-shaped → fetch via MCP; decision logic, math, opinions, mandatory disclaimers → embed.
  - Pricing snapshot stays embedded ONLY for deterministic estimator unit tests, with mandatory "as-of date" disclaimer surfaced in every report.
  - All eval assertions are meaning-shaped (icontains / regex / negation), not exact-slug — matches the "assertion-as-rubric" principle.
  - 56 KB of MCP coverage probes were captured before the aggressive cut — the cut deletes only what MCP demonstrably returns equivalent or better content for.
  - Pre-push hygiene: `grep -niE "elastic" AUTHORED files only`; "elasticsearch" appears solely as a product/source-engine name (allowed by the no-ES-internals rule).
