# Real-World TCO Patterns and Hidden Costs

> **Live data complement.** Pull current pricing and worked examples via
> MCP before quoting the report:
>
> ```jsonc
> { "tool": "aws___read_documentation",
>   "args": { "url": "https://aws.amazon.com/opensearch-service/pricing/",
>             "max_length": 8000 } }
> ```
>
> Everything below is **augmenting** content the live docs don't carry:
> case studies with named customers/savings, hidden line items most TCO
> models miss, and empirical RI / GovCloud uplift tables.

## Three reference case studies

### Yelp (re:Invent 2023, ANT332)

- **From:** Self-managed Elasticsearch on EC2, ~120 nodes r5.4xlarge.
- **To:** AOS managed on r6g + UltraWarm.
- **Saving:** ~38% TCO. Biggest contributor: UltraWarm tier for >7-day logs at
  ~$0.024/GB-mo vs hot EBS at $0.122/GB-mo.
- **Lesson:** UW transitions on log workloads dominate the saving curve.

### Sumo Logic / observability vendor (AWS blog, Mar 2024)

- **From:** 4-PB log tier on r6g hot-only.
- **To:** OR1 + UltraWarm + cold S3.
- **Saving:** Net cluster cost ~$210k/mo → ~$118k/mo. ~45% raw compute drop
  switching primaries from r6g.4xlarge to or1.2xlarge AND eliminating one
  replica copy.
- **Lesson:** OR1's S3-as-primary makes replica reduction a structural saving.

### Adobe Experience Platform (re:Invent 2024, ANT401)

- **From:** Provisioned $1.4M/yr cluster handling steady ingest + bursty
  analytics.
- **To:** Workload-split — steady ingest on r7g + 3-yr RI; analytics on AOSS
  (avg 6 OCUs, peak 18).
- **Saving:** ~$540k/yr. Dominant levers: 3-yr RI on the steady tier; OCU
  elasticity on the bursty tier.
- **Lesson:** "Hybrid" — managed for steady, AOSS for bursty — is often the
  best TCO answer when the workload bimodally splits.

## Hidden cost line items most TCO models miss

| Item | Where it bites | Magnitude (illustrative) |
|---|---|---|
| **Cross-AZ transfer for Multi-AZ-with-Standby** | $0.01/GB **each way** (in + out) on replication | 100 MB/s ingest → ~$5,200/mo |
| **AOS-managed gp3 premium over raw EBS** | Bundle includes IOPS baseline + mgmt overhead | ~52% premium → ~$4,300/yr per copy on 10 TB |
| **Manual snapshot S3 storage** | Customer bucket, $0.023/GB-mo + PUT charges | 90-day retention on 10 TB ≈ $690/mo + create cost |
| **CloudWatch Logs (slow-logs)** | $0.50/GB ingest + $0.03/GB-mo storage | Verbose `index.search.slowlog` → $400-$2,000/mo |
| **NAT Gateway for private VPC clusters** | $0.045/hr/AZ + $0.045/GB processed | 3-AZ + 100 GB/mo egress → ~$300/mo before bigger egress |
| **AOSS minimum 4-OCU floor per collection** | Even idle | $691/mo per collection (us-east-1) |
| **AOSS VECTORSEARCH separate OCU pool** | Cannot share with SEARCH/TIME_SERIES | Doubles the floor on mixed workload |
| **OSI persistent buffering OCU consumption** | Steals from `max_units` | 30-50% of declared OCUs |

## Reserved Instance discount table (.search instances)

Empirically derived from the AWS Price List API for Graviton families:

| Term | Discount vs on-demand |
|---|---|
| 1-yr No-Upfront | ~31% |
| 1-yr Partial-Upfront | ~33% (effective rate) |
| 1-yr All-Upfront | ~35% (effective rate) |
| 3-yr No-Upfront | ~48% |
| 3-yr Partial-Upfront | ~50% |
| 3-yr All-Upfront | ~52% |

Burstable t3 RIs are weaker (~18% 1-yr / ~29% 3-yr) — rarely worth reserving.

RIs apply ONLY to data/master node hours. UltraWarm, storage, AOSS OCUs,
and data transfer are excluded.

## GovCloud / FedRAMP uplift

Empirical (us-east-1 → us-gov-west-1):

| Family | Uplift |
|---|---|
| t3 | +20.5% |
| m6g | +25.8% |
| m7g | +26.4% |
| r6g | +20.4% |
| r7g | +19.7% |
| c6g | +19.5% |
| AOSS Indexing OCU | +25.8% |
| AOS gp3 storage | +20.0% |

Net: **20-28% uplift**. Note OR1 and OSI Ingestion OCU are NOT yet in
us-gov-west-1.

## TCO checklist for the report

- [ ] Compute: instance hours × 730 (commercial) or × 744 (with leap-day calendars).
- [ ] Storage: gp3 GB × AOS-managed rate (NOT raw EBS); IOPS above 3,000; throughput above 125 MB/s.
- [ ] Replicas: storage line × `(replicas + 1)`.
- [ ] UltraWarm: instance hour + warm S3 GB × $0.024/mo.
- [ ] Cold: data GB × $0.0125/mo (when applicable).
- [ ] Cross-AZ transfer: ingest_mbps × 60 × 60 × 730 / 1024 / 1024 GB × $0.01 × 2 (in + out).
- [ ] Manual snapshot: data × retention_days / 30 × $0.023.
- [ ] CloudWatch Logs: estimate slow-log volume.
- [ ] NAT: $0.045 × AZs × 730 + processed_gb × $0.045 (if private VPC).
- [ ] AOSS minimum: $691/mo floor per collection (us-east-1).
- [ ] AOSS VECTORSEARCH: separate floor.
- [ ] OSI: `max_units × $0.24 × 730` (regional rate).
- [ ] RI savings: dataNode hours × discount-pct (Graviton 31%/48%; t3 18%/29%).
- [ ] GovCloud uplift: ~22% on the whole bill.
