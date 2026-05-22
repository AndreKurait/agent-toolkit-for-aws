# AOSS — Decision Logic and Compatibility Checklist

> **Live data first.** AOSS overview, collection-type details, supported
> operations/plugins, encryption + network policies, and OCU economics
> are maintained in AWS docs and read live via MCP — do not embed
> snapshots:
>
> ```jsonc
> // AOSS overview
> { "tool": "aws___read_documentation",
>   "args": { "url": "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-overview.html",
>             "max_length": 6000 } }
>
> // Supported operations + plugin allowlist
> { "tool": "aws___read_documentation",
>   "args": { "url": "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-genref.html",
>             "max_length": 8000 } }
>
> // OCU scaling rules and minimums
> { "tool": "aws___read_documentation",
>   "args": { "url": "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-scaling.html",
>             "max_length": 4000 } }
>
> // Regional availability (structured)
> { "tool": "aws___get_regional_availability",
>   "args": { "resource_type": "product",
>             "regions": ["us-east-1", "us-gov-west-1", "us-gov-east-1"],
>             "filters": ["Amazon OpenSearch Serverless"] } }
> ```

This file augments live docs with **the assessor's call**: when AOSS is
the right answer and when it's a trap.

## Compatibility checklist (BEFORE recommending AOSS)

- [ ] No custom plugins required (LTR, Anomaly Detection, Security
      Analytics, etc.).
- [ ] No reliance on `_cat/shards|nodes|allocation|recovery|segments|
      health` — AOSS blocks these.
- [ ] No reliance on `_cluster/settings`, `_cluster/state`, `_nodes/*`,
      `_tasks/*`.
- [ ] No reliance on stored Painless (`/_scripts`) — inline-only on AOSS.
- [ ] No `_snapshot` workflows for backup/restore — blocked on AOSS.
- [ ] No ISM, alerting, anomaly-detection, async-search, cross-cluster-
      replication.
- [ ] No `_forcemerge`, `_shrink`, `_split`, `_clone`, `_reindex`,
      `_rollover`, `_open`, `_close`.
- [ ] **For TIME_SERIES / VECTORSEARCH:** no client-keyed upsert pattern
      (`update_pattern` / `_id` PUT) — those collections are append-only.
- [ ] Customer's idle hours can absorb a **floor of $174/mo (non-redundant
      dev) or ~$350/mo (redundant production) per collection**.

If any box is unchecked, AOSS is off the table — recommend AOS managed.

## When AOSS is a clear win

- **Bursty, unpredictable load with long idle.** Pay-for-OCU-hours wins
  cleanly over a 24/7 cluster.
- **New project with no operator team.** Zero capacity tuning to get
  wrong.
- **Bedrock RAG knowledge base** — managed integration is first-class
  on AOSS VECTORSEARCH.
- **Multi-tenant SaaS** where each tenant maps to one collection —
  isolation is automatic.

## When AOSS is a clear lose

- **Steady-state >50 GB/day ingest.** AOS managed with OR1 wins on
  $/throughput by a wide margin.
- **ISM-driven hot/warm/cold tiering required.** TIME_SERIES auto-tiers
  but the operator has no knob. If retention/promotion logic is a
  business requirement, AOS is the answer.
- **LTR, Anomaly Detection, Security Analytics, async-search.** None
  available on AOSS.
- **Mutable docs with idempotent client-keyed upserts** (CDC pipelines,
  e-commerce inventory) targeting TIME_SERIES — the collection rejects
  custom `_id`. SEARCH collection accepts custom `_id` but is hot-only
  with a 1 TiB cap.
- **Mixed search + vector and budget-sensitive.** The "no shared OCU
  pool between VECTORSEARCH and SEARCH/TIME_SERIES" rule **doubles the
  floor**. AOS managed with one cluster is usually cheaper.

## Floor cost worked example (operator wisdom)

A customer with 5 collections (3 SEARCH + 2 VECTORSEARCH), redundancy ON,
us-east-1: floor ≈ 5 × $350 = **$1,750/mo before any traffic**. If their
peak actual usage is bursty 30 hours/month, AOS managed on a single
or1.medium would be ~$200/mo. **The floor is the trap** — surface it
explicitly when collection count is high relative to peak usage.

## OCU sizing rules of thumb (not in docs)

- Hot-cache capacity ≈ **120 GiB hot index per OCU** for SEARCH /
  TIME_SERIES.
- VECTORSEARCH OCU ≈ **2 GB OS / 2 GB JVM / 2 GB graph** budget.
- Account caps: default **10 indexing + 10 search OCUs**; max **1,700 +
  1,700**. If projected peak exceeds 100 OCUs in either pool, file the
  quota increase early — approval can take days.
