# Text-to-SQL Experiments

Controlled Python experiments on how tools and agent architectures affect
Text-to-SQL accuracy, latency, and cost. This repository supports undergraduate
research at IME-USP.

## Baseline

For each example, the baseline sends one user message containing the natural-language
question and the full database schema to a single LLM. The prompt asks for one SQL
query. Generation uses no tools, examples, schema filtering, execution, or revision.
The provided schema is included verbatim. The runner trims whitespace and removes
a surrounding Markdown code fence when it encloses the entire response.

This version includes a two-example synthetic SQLite fixture for checking the
generation pipeline. The first benchmark, evaluation protocol, and model are
still to be selected. The fixture does not measure benchmark accuracy.

## Setup

Install [uv](https://docs.astral.sh/uv/), then run from the repository root:

```sh
uv sync --locked
```

The project uses Python 3.12. Set `TEXT_TO_SQL_API_KEY` in your environment and
set `TEXT_TO_SQL_BASE_URL` to the provider's API base URL, including any version
prefix and excluding `/chat/completions`. The endpoint must accept Chat Completions
requests with `model`, `messages`, `temperature`, and `max_tokens`. Use a model ID
supported by that endpoint. Keep the API key out of tracked files.

## Run the baseline

Run one fixture example to verify the integration:

```sh
uv run --locked text-to-sql --model YOUR_MODEL_ID --limit 1
```

Run every example in the configured split:

```sh
uv run --locked text-to-sql --config configs/baseline.toml --model YOUR_MODEL_ID
```

For your own data, copy `configs/baseline.toml`, update the dataset fields, and
point `--config` to that file. The dataset path is relative to the configuration
file. The runner reads UTF-8 JSONL in file order. Each line has a unique string
`id`, a string `question`, and a string `schema` containing the full schema,
including tables, column types, and keys where available. A configuration can
specify `generation.model` to make `--model` optional.

## Run artifacts

By default, each invocation writes to a new timestamped directory under `runs/`.
Use `--output` to choose a new directory explicitly.

| File | Contents |
| --- | --- |
| `run.json` | Git commit and working tree status, Python version, dataset identity, split and SHA-256, API endpoint, resolved generation settings and planned example count. |
| `predictions.jsonl` | One record per attempted example with ID, exact prompt, raw model text, extracted SQL, returned model ID, usage when available, request latency in milliseconds, finish reason, and error if any. |

Requests are sequential and failures are recorded without retries. A run with
recorded failures exits with status 1. Keep the artifacts with each reported
result. The lockfile, configuration, and dataset digest help reproduce the
procedure. A hosted model can still return different SQL in a new run. The saved
predictions are the inputs for future benchmark-specific evaluation.

Update this README in the same commit as any change to the documented commands,
input format, or experimental protocol.
