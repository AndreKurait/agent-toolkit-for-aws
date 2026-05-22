# AWS Knowledge MCP Integration

This skill REQUIRES the AWS Knowledge MCP Server to back its recommendations with live citations.
The endpoint is public and unauthenticated:

- **URL**: <https://knowledge-mcp.global.api.aws>
- **Docs**: <https://awslabs.github.io/mcp/servers/aws-knowledge-mcp-server/>
- **Cost**: free, no AWS account or auth required.

## Tools the skill expects

The runtime tool names vary by agent client (Claude, Codex, Q Developer, Bedrock AgentCore, etc.),
but all expose at least:

- `aws___search_documentation(query)` — full-text search across AWS docs.
- `aws___read_documentation(url)` — fetch a single AWS doc page.
- `aws___recommend(...)` — recommend related AWS pages from a starting URL.

If the user's agent has not configured the AWS Knowledge MCP, instruct them to install it from the
[awslabs/mcp](https://github.com/awslabs/mcp) repository OR fall back to the curated link table at
the bottom of this file. Always disclose the fallback in the report.

## When to call the MCP

Call it at minimum at these decision points:

| Phase | Trigger | Suggested query |
|---|---|---|
| Phase 3 — Target choice | Every Service-vs-Serverless rule that fires | `"Amazon OpenSearch Serverless supported features"` |
| Phase 3 — Target choice | Confirm regional availability | `"Amazon OpenSearch Serverless availability by region"` |
| Phase 3 — Target choice | Confirm compliance posture | `"Amazon OpenSearch Service FedRAMP HIPAA"` |
| Phase 4 — Migration path | MA support matrix | `"AWS Migration Assistant for OpenSearch supported source versions"` |
| Phase 4 — Migration path | OSI source list | `"Amazon OpenSearch Ingestion supported sources"` |
| Phase 4 — Migration path | Snapshot compatibility | `"Amazon OpenSearch Service snapshot restore from Elasticsearch"` |
| Phase 5 — Sizing | Confirm shard limits | `"Amazon OpenSearch Service shard limits per node"` |
| Phase 5 — Sizing | UltraWarm / Cold | `"Amazon OpenSearch Service UltraWarm cold tier"` |
| Phase 6 — Pricing | Confirm OCU rate | `"Amazon OpenSearch Serverless OCU pricing"` |
| Phase 6 — Pricing | Confirm instance pricing | `"Amazon OpenSearch Service instance pricing"` |
| Phase 7 — Risks | Plugin support | `"Amazon OpenSearch Service custom plugins"` |
| Phase 7 — Risks | Anomaly Detection availability | `"Amazon OpenSearch Service Anomaly Detection plugin"` |
| Phase 7 — Risks | Cross-cluster replication availability | `"Amazon OpenSearch Service cross-cluster replication"` |

## How to inline the citation

Every recommendation in the final report ends with a `Source:` line:

```text
Recommendation: Use Amazon OpenSearch Service (managed cluster) — the workload uses the
Learning to Rank plugin, which is not available on Serverless.
Source: aws___search_documentation("Amazon OpenSearch Service Learning to Rank")
   → https://docs.aws.amazon.com/opensearch-service/latest/developerguide/learning-to-rank.html
   (retrieved YYYY-MM-DD via AWS Knowledge MCP)
```

The `source_assessor.py report` command checks that every recommendation row has at least one
`Source:` line. Reports without citations fail validation.

## Curated fallback links

If the AWS Knowledge MCP is unreachable, use these links as a last-resort fallback. Disclose this
in the report.

| Topic | URL |
|---|---|
| Amazon OpenSearch Service overview | <https://docs.aws.amazon.com/opensearch-service/latest/developerguide/what-is.html> |
| Amazon OpenSearch Serverless overview | <https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-overview.html> |
| Serverless collection types | <https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-supported.html> |
| OpenSearch Ingestion overview | <https://docs.aws.amazon.com/opensearch-service/latest/developerguide/ingestion.html> |
| OSI supported sources | <https://docs.aws.amazon.com/opensearch-service/latest/developerguide/ingestion-sources.html> |
| Snapshot restore (manual) | <https://docs.aws.amazon.com/opensearch-service/latest/developerguide/managedomains-snapshots.html> |
| UltraWarm / Cold storage | <https://docs.aws.amazon.com/opensearch-service/latest/developerguide/ultrawarm.html> |
| Cross-cluster replication | <https://docs.aws.amazon.com/opensearch-service/latest/developerguide/replication.html> |
| Custom packages (plugins) | <https://docs.aws.amazon.com/opensearch-service/latest/developerguide/custom-packages.html> |
| Anomaly Detection | <https://docs.aws.amazon.com/opensearch-service/latest/developerguide/ad.html> |
| Learning to Rank | <https://docs.aws.amazon.com/opensearch-service/latest/developerguide/learning-to-rank.html> |
| Service pricing | <https://aws.amazon.com/opensearch-service/pricing/> |
| AWS Pricing Calculator | <https://calculator.aws> |
| Migration Assistant (open source) | <https://github.com/opensearch-project/opensearch-migrations> |

These URLs are evergreen but content drifts — always prefer a live MCP query.
