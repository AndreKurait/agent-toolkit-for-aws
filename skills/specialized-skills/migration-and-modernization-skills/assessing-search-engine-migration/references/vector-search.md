# Vector Search — AOS k-NN vs AOSS VECTORSEARCH

If the user has any `knn_vector` field, RAG workload, semantic search,
recommendation system, or "embeddings" anywhere in their description, walk
this decision before recommending a target.

## AOS k-NN (managed cluster)

[k-NN docs](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/knn.html)

- Engines: **HNSW (nmslib, faiss, lucene)**, **IVF / IVFQ (faiss)**,
  **disk-based (faiss + 16-bit / binary quantization)**.
- Dimension cap: **16,000**. Query `k`: max **10,000**.
- RAM math: heap = ½ instance RAM, capped at 32 GiB. The k-NN circuit
  breaker defaults to 50% of off-heap = ~25% of total RAM for graphs.
  `knn.memory.circuit_breaker.limit` is settable; `enabled`/`triggered` are
  not on AOS.
- `force_merge` after bulk load is a major throughput win (10x query latency
  reduction in HNSW). Available on AOS, **NOT on AOSS**.
- Painless re-scoring on hybrid (lexical + vector) queries: yes.
- Learning-to-Rank (LTR): yes.

## AOSS VECTORSEARCH

[Vector engine](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-vector-search.html)

- Engine: **HNSW + faiss only**. No IVF, no IVFQ, no Lucene, no nmslib.
- Faiss 16-bit scalar quantization: yes. Binary vectors: yes. Disk-based: yes.
- Dimension cap: **16,000** (same as managed).
- Refresh interval: **~60 s** (vs 10 s on SEARCH/TIME_SERIES).
- No `force_merge`. No HNSW parameter tuning. No Painless scripts. No LTR.
- Cannot share OCUs with SEARCH/TIME_SERIES even under same KMS — separate
  pool, separate floor.

## Decision flow

1. **Need IVF / IVFQ / Lucene engine, or HNSW parameter tuning, or LTR?**
   → AOS k-NN.
2. **Need force_merge for indexing throughput?** → AOS k-NN.
3. **Workload is bursty / Bedrock KB / new project?** → AOSS VECTORSEARCH.
4. **High-QPS production with strict p99 budgets and steady RAM?** → AOS
   k-NN with r-family (vector graphs are RAM-bound; OR1 cache-misses hurt).
5. **Mixed lexical + vector?** → AOS k-NN (one cluster, hybrid queries).
   AOSS would require two collections with separate OCU pools.

## Performance levers

- HNSW: tune `m` (default 16; raise to 24-48 for higher recall) and
  `ef_construction` (default 100; raise to 256-512 for higher recall at
  build cost).
- IVFQ: target `nlist ≈ 4 × sqrt(num_docs)`; `nprobe` 8-32 at query time.
- Disk-based faiss: ~75% RAM reduction at ~10-30% recall hit; great for
  cost-bound RAG.
- Always `force_merge` to 1 segment after bulk load on AOS — single biggest
  query-latency win in vector search.
- Vector OCU sizing on AOSS: budget **2 GB graph RAM per OCU** as the
  hot-cache target.

## RAM math for AOS k-NN sizing

```
graph_ram_gb = (num_vectors * (4 * dim + 24)) / 1e9   # HNSW float32
# 16-bit quantized: divide by ~2
# 8-bit quantized:  divide by ~4
# binary:           divide by ~32

cluster_ram_required_gb = graph_ram_gb / 0.25
# Because k-NN cb defaults to 50% of off-heap; heap = 50% of total
# Net: graphs get ~25% of total cluster RAM at the cb limit.
```

Use this to project node count before recommending an instance shape. The
pricing estimator implements this in `pricing_estimator.py`.
