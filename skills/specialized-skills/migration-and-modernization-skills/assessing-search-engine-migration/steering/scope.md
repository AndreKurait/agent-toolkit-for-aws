# Scope — What This Skill Does and Does Not Do

## In scope

- Profile a Solr / Elasticsearch / OpenSearch source cluster for migration assessment.
- Recommend a target: Amazon OpenSearch Service or Amazon OpenSearch Serverless, plus collection
  type (search / time-series / vector) when applicable.
- Recommend a migration mechanism: Migration Assistant for OpenSearch, snapshot-and-restore,
  OpenSearch Ingestion, or direct-from-source via Spark on EMR.
- Produce sizing and monthly cost ranges for both candidate targets.
- Produce a written assessment report with citations against the AWS Knowledge MCP Server.

## Out of scope

- **Executing the migration.** Hand off to the Migration Assistant docs, the AWS Transform skill
  (for any required code changes), or the user's runbook when they're ready to act.
- **Solr schema and query translation deep-dives.** The upstream
  `solr-opensearch-migration-advisor` skill (in `opensearch-project/opensearch-migrations`) covers
  schema XML, Query DSL translation, analyzer migration, and similar. This skill assesses the AWS
  side and complements that work; it does not replace it.
- **Non-search workloads.** For RDS, Redshift, DynamoDB, or other migrations, use the appropriate
  AWS skills.
- **Operating a live OpenSearch cluster.** For day-2 operations, use the AWS MCP Server and the
  Amazon OpenSearch Service operational docs.
- **Procurement, EDP negotiation, or non-list pricing decisions.** This skill produces list-price
  estimates only.

## When the user crosses a scope boundary

Don't try to do it; recommend the right tool:

| User asks for... | Recommend |
|---|---|
| "Translate this Solr schema to OpenSearch" | `solr-opensearch-migration-advisor` |
| "Run the migration now" | Migration Assistant docs + the user's runbook |
| "Refactor my application code from SolrJ to opensearch-java" | `aws-transform` skill |
| "Tune my live OpenSearch cluster" | AWS MCP Server + OpenSearch operational docs |
| "Quote me an EDP-discounted price" | AWS Account Manager / Solutions Architect |
