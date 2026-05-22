# Vector Search — AOS k-NN vs AOSS VECTORSEARCH

> **Live data first.** Engine support, dimension caps, and AOSS OCU/
> capacity rules are maintained in AWS docs and read live via MCP — do
> not embed snapshots:
>
> ```jsonc
> // k-NN engines, dimension limits, RAM rules
> { "tool": "aws___read_documentation",
>   "args": { "url": "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/knn.html",
>             "max_length": 8000 } }
>
> // AOSS vector engine + OCU sharing rules
> { "tool": "aws___read_documentation",
>   "args": { "url": "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-vector-search.html",
>             "max_length": 6000 } }
>
> // AOSS scaling and capacity caps
> { "tool": "aws___read_documentation",
>   "args": { "url": "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-scaling.html",
>             "max_length": 4000 } }
> ```

If the user has any `knn_vector` field, RAG workload, semantic search,
recommendation system, or "embeddings" anywhere in their description,
walk this decision before recommending a target.

## Decision flow (the assessor's call)

1. **Need IVF / IVFQ / Lucene engine, or HNSW parameter tuning, or LTR
   re-ranking?** → AOS k-NN. AOSS supports HNSW + faiss only.
2. **Need `force_merge` for indexing throughput?** → AOS k-NN. AOSS does
   not expose force_merge.
3. **Workload is bursty / Bedrock Knowledge Base / new project with no
   operator team?** → AOSS VECTORSEARCH.
4. **High-QPS production with strict p99 budgets and steady RAM?** →
   AOS k-NN with **r-family** (vector graphs are RAM-bound; OR1
   cache-misses hurt latency).
5. **Mixed lexical + vector in a single query?** → AOS k-NN (one cluster,
   hybrid queries). AOSS would require two collections with separate OCU
   pools, since VECTORSEARCH cannot share OCUs with SEARCH/TIME_SERIES
   even under the same KMS key.

## RAM math for AOS k-NN sizing (not in docs)

```text
graph_ram_gb = (num_vectors * (4 * dim + 24)) / 1e9   # HNSW float32
# 16-bit quantized: divide by ~2
# 8-bit quantized:  divide by ~4
# binary:           divide by ~32

cluster_ram_required_gb = graph_ram_gb / 0.25
# Because k-NN circuit-breaker defaults to 50% of off-heap; heap = 50%
# of total. Net: graphs get ~25% of total cluster RAM at the cb limit.
```

Use this to project node count before recommending an instance shape.
The estimator at `scripts/pricing_estimator.py` implements this formula.

## Performance levers (operator wisdom)

- **HNSW**: tune `m` (default 16; raise to 24–48 for higher recall) and
  `ef_construction` (default 100; raise to 256–512 for higher recall at
  build cost).
- **IVFQ**: target `nlist ≈ 4 × sqrt(num_docs)`; `nprobe` 8–32 at query
  time.
- **Disk-based faiss**: ~75% RAM reduction at ~10–30% recall hit; great
  for cost-bound RAG.
- **`force_merge` to 1 segment after bulk load** on AOS — single biggest
  query-latency win in vector search (often 10× p99 reduction).
- **AOSS vector OCU sizing rule of thumb**: budget **~2 GB graph RAM per
  OCU** as the hot-cache target.

## Mixed-workload pricing trap

When a customer has search + vector and budget is sensitive: AOSS
**doubles the floor** because the two pools cannot share. Surface this
explicitly — at $174/mo per pool minimum it's not a rounding error.
AOS managed with a single cluster is usually the right answer.
