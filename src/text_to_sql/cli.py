"""Run the baseline and record its configuration and predictions."""

import argparse
import json
import os
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from .baseline import predict
from .datasets import load_dataset


def git_metadata() -> dict:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
        changes = subprocess.check_output(
            ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL, text=True
        )
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "working_tree_dirty": None}
    return {"commit": commit, "working_tree_dirty": bool(changes)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Text-to-SQL baseline predictions.")
    parser.add_argument("--config", type=Path, default=Path("configs/baseline.toml"))
    parser.add_argument("--model", help="Override the model in the configuration file")
    parser.add_argument("--limit", type=int, help="Run only the first N examples")
    parser.add_argument("--output", type=Path, help="Directory to create for this run")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")

    api_key = os.environ.get("TEXT_TO_SQL_API_KEY")
    base_url = os.environ.get("TEXT_TO_SQL_BASE_URL", "").rstrip("/")
    try:
        endpoint = urlsplit(base_url)
        if (
            endpoint.scheme not in ("http", "https")
            or not endpoint.hostname
            or endpoint.username is not None
            or endpoint.query
            or endpoint.fragment
        ):
            raise ValueError("set TEXT_TO_SQL_BASE_URL to an API base URL without credentials")
        if not api_key:
            raise ValueError("set TEXT_TO_SQL_API_KEY")
        with args.config.open("rb") as config_file:
            config = tomllib.load(config_file)
        dataset = config["dataset"]
        generation = config["generation"]
        model = args.model or generation.get("model")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("provide --model or set generation.model")
        for key in ("path", "name", "revision", "split", "dialect"):
            if not isinstance(dataset[key], str) or not dataset[key].strip():
                raise ValueError(f"dataset.{key} must be a nonempty string")
        temperature = generation["temperature"]
        max_tokens = generation["max_tokens"]
        timeout = generation["timeout_seconds"]
        if type(temperature) not in (int, float) or not 0 <= temperature <= 2:
            raise ValueError("generation.temperature must be between 0 and 2")
        if type(max_tokens) is not int or max_tokens < 1:
            raise ValueError("generation.max_tokens must be a positive integer")
        if type(timeout) not in (int, float) or not 0 < timeout < float("inf"):
            raise ValueError("generation.timeout_seconds must be positive and finite")
        dataset_format = dataset.get("format", "jsonl")
        if not isinstance(dataset_format, str):
            raise ValueError("dataset.format must be a string")
        loaded = load_dataset(args.config.parent / dataset["path"], dataset_format)
        selected = loaded.examples[:args.limit]
    except (OSError, TypeError, KeyError, ValueError) as exc:
        parser.error(str(exc))

    started_at = datetime.now(UTC)
    output = args.output or Path("runs") / started_at.strftime("%Y%m%dT%H%M%S%fZ")
    dataset_metadata = {**dataset, "format": dataset_format, "sha256": loaded.sha256}
    if loaded.schema_sha256 is not None:
        dataset_metadata["schema_sha256"] = loaded.schema_sha256

    metadata = {
        **git_metadata(),
        "started_at": started_at.isoformat(),
        "python_version": sys.version.split()[0],
        "dataset": dataset_metadata,
        "generation": {
            "model": model,
            "base_url": base_url,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout_seconds": timeout,
        },
        "limit": args.limit,
        "example_count": len(selected),
    }
    errors = 0
    try:
        output.mkdir(parents=True, exist_ok=False)
        (output / "run.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        with (output / "predictions.jsonl").open("x", encoding="utf-8", buffering=1) as records:
            for example in selected:
                prediction = predict(
                    example,
                    dialect=dataset["dialect"],
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout_seconds=timeout,
                )
                if "db_id" in example:
                    prediction["db_id"] = example["db_id"]
                records.write(json.dumps(prediction, ensure_ascii=False) + "\n")
                errors += prediction["error"] is not None
    except OSError as exc:
        print(f"Could not write run artifacts: {exc}", file=sys.stderr)
        return 1
    print(f"{len(selected)} predictions recorded in {output} ({errors} errors)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
