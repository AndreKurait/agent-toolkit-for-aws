# Promptfoo Evals — End-to-end Quality Gates

This directory contains [promptfoo](https://promptfoo.dev) evaluations that exercise the skill's
decision logic via the agent's prompt. They are **optional** — the unit tests under `tests/` are
the source of truth for deterministic logic — but the evals catch prompt-level regressions when
the skill is loaded into a real agent.

## Layout

- `promptfooconfig.yaml` — top-level eval config. Targets a generic chat provider; override with
  `--provider` at runtime to test against your agent.
- `prompts/migration-assessor.txt` — the prompt under test (loads the SKILL.md verbatim).
- `tests/*.yaml` — individual scenarios with assertions.

## Running

```bash
cd evals/
npx promptfoo eval --providers openai:gpt-4o-mini   # or your preferred provider
```

If you don't have `promptfoo` installed, the YAML files still serve as machine-readable scenario
documentation. The unit tests validate the underlying logic without needing an LLM.

## What the evals check

| Scenario | Pass criteria |
|---|---|
| `solr-large-strict.yaml` | Recommends `direct-from-source` (Spark/EMR), notes Solr scope. |
| `es-7-small-simple.yaml` | Recommends `snapshot-and-restore`, picks Service over Serverless. |
| `es-bursty-time-series.yaml` | Recommends `aoss-time-series` collection. |
| `es-vector-workload.yaml` | Recommends `aoss-vector` collection. |
| `es-with-ltr-plugin.yaml` | Stays on Service (Serverless blocked by plugin). |
| `es-govcloud.yaml` | Stays on Service (Serverless blocked by GovCloud). |
| `pricing-disclosure.yaml` | Output contains the AS_OF date and disclaimer. |
| `citations-required.yaml` | At least 3 AWS Knowledge MCP citations present. |
