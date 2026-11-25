"""Score saved predictions without accessing a model provider."""

import argparse
import hashlib
import json
import tomllib
from collections import Counter
from pathlib import Path

from ..cli import git_metadata
from .spider import evaluate_spider

_EVALUATORS = {"spider": evaluate_spider}


def read_predictions(path: Path) -> tuple[dict[str, dict], str]:
    data = path.read_bytes()
    predictions = {}
    for line_number, line in enumerate(data.decode("utf-8").splitlines(), start=1):
        record = json.loads(line)
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise ValueError(f"{path}:{line_number}: expected a prediction with a string ID")
        if record["id"] in predictions:
            raise ValueError(f"{path}:{line_number}: duplicate prediction ID {record['id']}")
        if record.get("sql") is not None and not isinstance(record["sql"], str):
            raise ValueError(f"{path}:{line_number}: sql must be a string or null")
        predictions[record["id"]] = record
    return predictions, hashlib.sha256(data).hexdigest()


def summarize(results: list[dict]) -> dict:
    statuses = Counter(result["status"] for result in results)
    correct = statuses["correct"]
    protocol_errors = statuses["gold_error"] + statuses["evaluator_error"]
    return {
        "example_count": len(results),
        "correct": correct,
        "accuracy": None if protocol_errors else correct / len(results),
        "status_counts": dict(statuses),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate saved Text-to-SQL predictions.")
    parser.add_argument("--run", required=True, type=Path, help="Generation run directory")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="New directory for evaluation artifacts")
    args = parser.parse_args()
    try:
        run_data = (args.run / "run.json").read_bytes()
        run = json.loads(run_data)
        predictions, prediction_hash = read_predictions(args.run / "predictions.jsonl")
        config = tomllib.loads(args.config.read_text(encoding="utf-8"))["evaluation"]
        adapter = config["adapter"]
        if adapter not in _EVALUATORS:
            raise ValueError(f"unknown evaluation adapter: {adapter!r}")
        output = args.output or args.run / f"evaluation-{config['metric']}"
        if output.exists():
            raise ValueError(f"output directory already exists: {output}")
        results, provenance = _EVALUATORS[adapter](args.config.parent, config, run, predictions)
        overall = summarize(results)
        by_difficulty = {}
        for difficulty in sorted({result["difficulty"] or "unknown" for result in results}):
            by_difficulty[difficulty] = summarize([
                result for result in results if (result["difficulty"] or "unknown") == difficulty
            ])
        summary = {
            "adapter": adapter,
            "metric": config["metric"],
            "scope": "full_split" if provenance["is_full_split"] else "subset",
            "run_sha256": hashlib.sha256(run_data).hexdigest(),
            "predictions_sha256": prediction_hash,
            "evaluation_code": git_metadata(),
            "protocol": provenance,
            **overall,
            "by_difficulty": by_difficulty,
        }

        output.mkdir(parents=True, exist_ok=False)
        with (output / "per_example.jsonl").open("x", encoding="utf-8") as file:
            for result in results:
                file.write(json.dumps(result, ensure_ascii=False) + "\n")
        (output / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.error(str(exc))

    if overall["accuracy"] is None:
        print(f"Evaluation incomplete due to protocol errors. See {output / 'summary.json'}")
        return 1
    print(f"{summary['metric']}: {overall['correct']}/{len(results)} "
          f"({overall['accuracy']:.2%}, {summary['scope']}). See {output / 'summary.json'}")
    return 0
