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

The first benchmark is [Spider 1.0](https://yale-lily.github.io/spider/), using
the public development split (1,034 examples). The repository also includes a
two-example synthetic SQLite fixture for checking the generation pipeline.

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

## Run on Spider 1.0

Download the archive linked on the [official Spider 1.0 page](https://yale-lily.github.io/spider/).
Extract it under `data/` so that the split and databases are at
`data/spider_data/dev.json` and
`data/spider_data/database/<db_id>/<db_id>.sqlite`. If your extracted folder has
a different name, rename it or update `dataset.path` in `configs/spider.toml`.

Run a small smoke test, then run the complete development split:

```sh
uv run --locked text-to-sql --config configs/spider.toml --model YOUR_MODEL_ID --limit 3
uv run --locked text-to-sql --config configs/spider.toml --model YOUR_MODEL_ID
```

The adapter reads the native split in file order and assigns zero-based IDs
such as `dev:0000`. It opens each example's SQLite database read-only once per
database to collect every table and view definition, excluding SQLite's
internal objects. The prompt receives the schema as declared in SQLite and
the question. Gold SQL and row contents are excluded. The CLI produces
predictions for later evaluation. It does not execute them or compute accuracy.

## Run the synthetic fixture

Run one fixture example to verify the integration:

```sh
uv run --locked text-to-sql --model YOUR_MODEL_ID --limit 1
```

Run every example in the configured split:

```sh
uv run --locked text-to-sql --config configs/baseline.toml --model YOUR_MODEL_ID
```

## Add a dataset

The dataset configuration selects an adapter with `dataset.format` (defaults
to `jsonl`). The dataset path is relative to the configuration file.

- For prepared data, use `jsonl`. Each UTF-8 line has a unique string `id`,
  a string `question`, and a string `schema` containing the full schema.
- For a new native format, implement a loader in `src/text_to_sql/datasets/`
  and register it in the adapter map. A loader takes a path and returns
  `LoadedDataset` with ordered examples, the SHA-256 of the input, and optional
  per-database schema hashes. Each example supplies `id`, `question`, and
  `schema` as strings, plus an optional string `db_id` for the prediction log.
  Add a configuration that selects the adapter and declares the SQL dialect.
  The baseline uses the same prompt and generation flow for all adapters.

Any configuration can specify `generation.model` to make `--model` optional.

## Run artifacts

By default, each invocation writes to a new timestamped directory under `runs/`.
Use `--output` to choose a new directory explicitly.

| File | Contents |
| --- | --- |
| `run.json` | Git commit and working tree status, Python version, dataset identity, split, input SHA-256 and schema hashes when available, API endpoint, resolved generation settings and planned example count. |
| `predictions.jsonl` | One record per attempted example with ID, database ID when supplied, exact prompt, raw model text, extracted SQL, returned model ID, usage when available, request latency in milliseconds, finish reason, and error if any. |

Requests are sequential and failures are recorded without retries. A run with
recorded failures exits with status 1. Keep the artifacts with each reported
result. The lockfile, configuration, and dataset digest help reproduce the
procedure. A hosted model can still return different SQL in a new run. The saved
predictions are the inputs for future benchmark-specific evaluation.

Update this README in the same commit as any change to the documented commands,
input format, or experimental protocol.
