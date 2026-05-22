# End-to-End Evals — Two Harnesses, One Rubric

This directory contains end-to-end evaluations that exercise the skill's
decision logic via the agent's prompt. They are **optional** — the unit
tests under `tests/` remain the source of truth for deterministic logic —
but the evals catch prompt-level regressions when the skill is loaded
into a real agent.

Two harnesses are shipped, both reading the same fixtures so a regression
caught by one is caught by the other:

| Harness | Runtime | When to run |
|---|---|---|
| `npx promptfoo eval` (`promptfooconfig.yaml`) | Node + any LLM provider | Local dev, CI with API keys to a hosted provider |
| `python3 run_bedrock.py` | Python + boto3 + Bedrock | AWS-native, no Node, no third-party provider |

## Layout

- `promptfooconfig.yaml` — top-level promptfoo config.
- `run_bedrock.py` — Bedrock-native harness (stdlib + boto3).
- `prompts/migration-assessor.txt` — prompt under test.
- `tests/*.yaml` — scenarios with assertions (shared by both harnesses).

## Running with promptfoo

```bash
cd evals/
npx promptfoo eval --providers openai:gpt-4o-mini    # or any provider
```

## Running with Bedrock (native AWS)

```bash
# 1. Get AWS creds (Isengard/SSO/IAM — anything boto3 can pick up)
ada credentials update --once    # or aws configure / aws sso login

# 2. From the skill directory:
python3 evals/run_bedrock.py \
  --region us-west-2 \
  --model us.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --json /tmp/bedrock-results.json
```

Defaults:

- region `us-west-2` (or `$AWS_REGION`)
- model `us.anthropic.claude-haiku-4-5-20251001-v1:0` (Claude Haiku 4.5
  inference profile — fastest/cheapest for eval) — override with `--model`
  or `$BEDROCK_MODEL_ID`. Sonnet/Opus profiles work; cost rises ~10-30×.

Other useful flags:

- `--dry-run` — exercises the harness without calling Bedrock (smoke test).
- `--tests <path.yaml>` (repeatable) — run a single fixture.
- `--json <out.json>` — write structured results.
- `--verbose` — print all assertion results plus output preview.

## What the evals check

| Scenario | Pass criteria |
|---|---|
| `solr-large-strict.yaml` | Recommends `direct-from-source` (Spark/EMR), notes Solr scope. |
| `es-7-small-simple.yaml` | Recommends `snapshot-and-restore`; picks Service over Serverless. |
| `es-bursty-time-series.yaml` | Recommends `aoss-time-series` collection. |
| `es-vector-workload.yaml` | Recommends `aoss-vector` collection. |
| `es-with-ltr-plugin.yaml` | Stays on Service (Serverless blocked by plugin). |
| `es-govcloud.yaml` | Stays on Service (Serverless blocked by GovCloud). |
| `pricing-disclosure.yaml` | Output contains the as-of date and the standard disclaimer. |
| `citations-required.yaml` | AWS Knowledge MCP citations present. |

## Cost (Bedrock harness)

Each test = one Converse call ≈ 1k-3k output tokens. Full 8-test sweep
on Claude Haiku 4.5 ≈ $0.10-$0.30 per run. Sonnet ≈ $1-$3. Opus ≈ $5-$15.
Use Haiku for CI; Sonnet/Opus for release-gate runs.

## Authoring new fixtures

Both harnesses share the YAML schema. Supported assertion types:
`contains`, `icontains`, `not-contains`, `regex`. Add a YAML under
`tests/` and both harnesses pick it up automatically.
