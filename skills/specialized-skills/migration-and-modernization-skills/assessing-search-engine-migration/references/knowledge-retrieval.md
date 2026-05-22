# Knowledge Retrieval Strategy

This skill follows a **fetch-first, embed-rarely** rule. Knowledge that
changes (pricing, regional availability, plugin matrix, AWS announcements)
is retrieved live via the AWS Knowledge MCP server. Knowledge that doesn't
change (decision frameworks, sizing math, this skill's opinions) stays in
the repo.

## The dividing line

| Property                          | Embed in skill | Fetch via MCP / tool |
|-----------------------------------|----------------|----------------------|
| Changes more than yearly?         | No             | Yes                  |
| Authoritative source = AWS docs?  | No             | Yes                  |
| Decision logic / phrasing / flow? | Yes            | No                   |
| Math / heuristics / ratios?       | Yes            | No                   |
| Quotes verbatim from AWS?         | No             | Yes (read on demand) |
| User-supplied profile data?       | n/a            | n/a                  |

## AWS Knowledge MCP server

Endpoint: `https://knowledge-mcp.global.api.aws`
Transport: Streamable HTTP (no auth, no client-side install).

Six tools, all live, all verified against this skill's domain:

| Tool                              | Use it for                                                    |
|-----------------------------------|---------------------------------------------------------------|
| `aws___search_documentation`      | Find authoritative pages for any factual claim.               |
| `aws___read_documentation`        | Pull full markdown of a specific docs.aws.amazon.com page.    |
| `aws___list_regions`              | Enumerate AWS regions (commercial + GovCloud + China).        |
| `aws___get_regional_availability` | Verify a service/feature is available in a region.            |
| `aws___recommend`                 | Get related-page suggestions for a docs.aws.amazon.com URL.   |
| `aws___retrieve_skill`            | Pull a published AWS agent skill by exact name.               |

### Configuration (Hermes Agent and any MCP-aware client)

Add to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  aws_knowledge:
    url: "https://knowledge-mcp.global.api.aws"
    timeout: 60
    connect_timeout: 30
```

Tools then appear as `mcp_aws_knowledge_aws___search_documentation`, etc.
For Kiro / Claude Code / Cursor, use the same URL with the client's
`url`+`type: http` config form (see the awslabs/mcp README).

## Per-knowledge-area retrieval recipes

The patterns below are the actual queries this skill should run during an
assessment. Each one was verified live against the production endpoint.

### 1. Plugin compatibility — DO NOT EMBED

Authoritative source: the supported-plugins page, updated by AWS as new
plugins ship.

```jsonc
// First find it
{
  "tool": "aws___search_documentation",
  "args": { "search_phrase": "Amazon OpenSearch Service supported plugins",
            "limit": 3 }
}
// Then read the canonical page
{
  "tool": "aws___read_documentation",
  "args": { "url": "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/supported-plugins.html",
            "max_length": 6000 }
}
```

Why MCP, not a snapshot: the table changes each minor release. A snapshot
in this repo will be wrong within a quarter.

### 2. FedRAMP / GovCloud / regulated workload claims — DO NOT EMBED

```jsonc
{
  "tool": "aws___get_regional_availability",
  "args": {
    "resource_type": "product",
    "regions": ["us-gov-west-1", "us-gov-east-1"],
    "filters": ["Amazon OpenSearch Serverless", "Amazon OpenSearch Service"]
  }
}
```

Returns one of `isAvailableIn | isNotAvailableIn | isComingSoon` per
(product, region) pair. Use this to replace any "must verify with AWS"
hedge in the assessment narrative.

For FedRAMP-level claims (which the regional API does not encode),
search docs:

```jsonc
{
  "tool": "aws___search_documentation",
  "args": { "search_phrase": "Amazon OpenSearch Service FedRAMP High GovCloud",
            "limit": 3 }
}
```

### 3. OR1 / OR2 / OI2 / UltraWarm instance details — DO NOT EMBED

```jsonc
{
  "tool": "aws___read_documentation",
  "args": { "url": "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/or1.html",
            "max_length": 8000 }
}
```

The OR1 page evolves (limitations list grows, tuning guidance updates).
Always read live during sizing.

### 4. Pricing — embed STRUCTURE only, fetch CURRENT NUMBERS

This skill embeds a `scripts/pricing_data.json` snapshot for **deterministic
unit-test math** (so the pricing estimator is testable offline). The
estimator emits a clear "Pricing as of `<date>`" disclaimer in every
report.

For "what does this cost today?" the agent should ALSO call:

```jsonc
{
  "tool": "aws___read_documentation",
  "args": { "url": "https://aws.amazon.com/opensearch-service/pricing/",
            "max_length": 8000 }
}
```

and reconcile any drift before sending the final number to the user.

### 5. Migration Assistant capabilities — DO NOT EMBED

```jsonc
{
  "tool": "aws___search_documentation",
  "args": { "search_phrase": "Migration Assistant for OpenSearch supported sources",
            "limit": 3 }
}
{
  "tool": "aws___read_documentation",
  "args": { "url": "https://docs.aws.amazon.com/solutions/latest/migration-assistant-for-amazon-opensearch-service/solution-overview.html",
            "max_length": 8000 }
}
```

The supported-source matrix (ES 1.x–8.x, OS 1.x–2.x, Solr 6.x–9.x) drifts
upward as new versions ship.

### 6. Snapshot / restore mechanics — DO NOT EMBED

```jsonc
{
  "tool": "aws___read_documentation",
  "args": { "url": "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/managedomains-snapshots.html",
            "max_length": 6000 }
}
```

### 7. Vector / k-NN / Neural Search current limits — DO NOT EMBED

Replace any embedded vector-search facts with:

```jsonc
{
  "tool": "aws___search_documentation",
  "args": { "search_phrase": "OpenSearch k-NN vector index limits",
            "limit": 3 }
}
```

### 8. Service-Linked Role / IAM details — DO NOT EMBED

Always fetch fresh; IAM permissions surface change frequently.

```jsonc
{
  "tool": "aws___search_documentation",
  "args": { "search_phrase": "Amazon OpenSearch Service service-linked role",
            "limit": 3 }
}
```

### 9. Published AWS agent skills (peer skills) — RETRIEVE, don't reimplement

If `aws___search_documentation` returns a result with a `skill_name`
field, prefer that skill over re-deriving its content here:

```jsonc
{
  "tool": "aws___retrieve_skill",
  "args": { "skill_name": "<exact_name_from_search_result>" }
}
```

As of this skill's authoring, AWS publishes the OpenSearch Agent Skills
collection on GitHub (`opensearch-launchpad`, an incident investigator,
a deployer, and a Solr-to-OpenSearch migrations skill). They are not yet
indexed in `aws___retrieve_skill`'s registry; when they are, this skill
should defer to them for source-specific implementation playbooks and
keep itself focused on the cross-source **assessment** layer above them.

### 10. Real-time region enumeration — DO NOT EMBED

```jsonc
{ "tool": "aws___list_regions", "args": {} }
```

Returns id + long name for every AWS region. Useful for any "what
regions can I deploy to?" branch.

## What this skill SHOULD keep embedded

These are evergreen and load-bearing:

- `SKILL.md` — the eight-phase flow, the prose template, the phrasing
  contract that downstream tools (eval harness, smoke tests) test against.
- `references/migration-paths.md` — the **decision tree** between Path A/B/C/D.
  The names of the paths and the criteria (volume, transformation needs,
  downtime tolerance) are the skill's opinion. *Implementation details
  per path = fetch from MCP.*
- `references/target-decision-matrix.md` — the rules that map a profile
  to `service-general` / `aoss-search` / `aoss-vector` / `aoss-time-series`.
  The slugs are this skill's controlled vocabulary.
- `references/sizing.md` — shard math, heap math, replica overhead. These
  are heuristics, not AWS facts.
- `scripts/*.py` and `scripts/pricing_data.json` — deterministic for tests.
- `evals/` — tests that pin the skill's contract.

## What this skill PREVIOUSLY embedded but should now fetch

These reference files are kept (for offline/CI determinism) but each
one's content section now begins with: "**Prefer live retrieval — see
references/knowledge-retrieval.md §N**" and the embedded text is
demoted to "fallback if MCP is unavailable":

- `references/plugin-compatibility-matrix.md` → MCP §1
- `references/aoss-deep-dive.md`               → MCP §2 + §7
- `references/or1-and-tiers.md`                → MCP §3
- `references/pricing-data.md`                 → MCP §4
- `references/migration-assistant.md`          → MCP §5
- `references/vector-search.md`                → MCP §7
- `references/real-world-tco.md`               → MCP §4 (numbers)

The decision-shaping bits in those files (when to use OR1 vs r6g, when
plugin X disqualifies Serverless) stay; the lookup tables don't.

## Verification

The exact 6-tool probe used to author this file lives in
`scripts/probe_aws_knowledge_mcp.py`. Run it any time AWS publishes
something that might invalidate the recipes above.
