"""Join a Spider generation run to its reference queries and SQLite test cases."""

import hashlib
import json
import math
import sqlite3
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

_UPSTREAM_REVISION = "e97acc546ecbee8fa27fa8dbf025ef61493a876c"


def _verify_upstream(path: Path) -> dict[str, str]:
    try:
        revision = subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        changes = subprocess.check_output(
            ["git", "-C", str(path), "status", "--porcelain", "--untracked-files=no"], text=True
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"expected the upstream evaluator checkout at {path}") from exc
    if revision != _UPSTREAM_REVISION or changes:
        raise ValueError(f"{path}: expected a clean checkout of {_UPSTREAM_REVISION}")
    try:
        return {name: version(name) for name in ("nltk", "sqlparse", "tqdm")}
    except PackageNotFoundError as exc:
        raise ValueError("install the evaluation extra with uv sync --locked --extra evaluation") from exc


def _align_examples(split_path: Path, run: dict, predictions: dict) -> tuple[list, str, int]:
    data = split_path.read_bytes()
    split_hash = hashlib.sha256(data).hexdigest()
    if run["dataset"]["format"] != "spider" or run["dataset"]["sha256"] != split_hash:
        raise ValueError("the Spider split differs from the split recorded in run.json")
    rows = json.loads(data)
    if not isinstance(rows, list) or not rows:
        raise ValueError("expected a nonempty Spider split array")

    limit = run["limit"]
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("invalid generation limit in run.json")
    selected = rows[:limit]
    if len(selected) != run["example_count"]:
        raise ValueError("example_count does not match the split and limit in run.json")
    expected_ids = {f"{split_path.stem}:{index:04d}" for index in range(len(selected))}
    missing = expected_ids - predictions.keys()
    extra = predictions.keys() - expected_ids
    if missing or extra:
        raise ValueError(
            f"incomplete or mismatched run: {len(missing)} missing IDs and {len(extra)} unexpected IDs"
        )
    aligned = []
    for index, row in enumerate(selected):
        example_id = f"{split_path.stem}:{index:04d}"
        db_id = row["db_id"]
        if not isinstance(db_id, str) or not db_id or Path(db_id).name != db_id or db_id in {".", ".."}:
            raise ValueError(f"{example_id}: invalid database ID")
        prediction = predictions[example_id]
        if prediction.get("db_id") != db_id:
            raise ValueError(f"{example_id}: prediction database does not match the reference")
        aligned.append((example_id, row, prediction))
    return aligned, split_hash, len(rows)


def _hash_database(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def _run_example(payload: dict, timeout: float) -> dict:
    try:
        process = subprocess.run(
            [sys.executable, "-m", "text_to_sql.evaluation.spider_worker"],
            input=json.dumps(payload), text=True, capture_output=True, timeout=2 * timeout + 10,
        )
    except subprocess.TimeoutExpired:
        return {"status": "evaluator_error", "difficulty": None, "error": "worker deadline exceeded"}
    if process.returncode:
        return {
            "status": "evaluator_error",
            "difficulty": None,
            "error": process.stderr.strip()[-1500:] or f"worker exit {process.returncode}",
        }
    return json.loads(process.stdout)


def evaluate_spider(base: Path, config: dict, run: dict, predictions: dict) -> tuple[list, dict]:
    split_path = base / config["split_path"]
    aligned, split_hash, split_count = _align_examples(split_path, run, predictions)
    metric = config["metric"]
    if metric not in {"test_suite_accuracy", "execution_accuracy"}:
        raise ValueError("Spider evaluation metric must be test_suite_accuracy or execution_accuracy")
    timeout = config["timeout_seconds"]
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("evaluation.timeout_seconds must be positive and finite")
    upstream = (base / config["upstream_dir"]).resolve()
    dependencies = _verify_upstream(upstream)
    database_dir = (base / config["database_dir"]).resolve()
    databases = {}
    for db_id in sorted({row["db_id"] for _, row, _ in aligned}):
        paths = sorted((database_dir / db_id).glob("*.sqlite"))
        if metric == "execution_accuracy":
            paths = [database_dir / db_id / f"{db_id}.sqlite"]
        elif len(paths) < 2:
            raise ValueError(f"{db_id}: test_suite_accuracy requires multiple SQLite instances")
        databases[db_id] = {str(path): _hash_database(path) for path in paths}

    results = []
    for example_id, row, prediction in aligned:
        result = _run_example({
            "upstream_dir": str(upstream),
            "databases": list(databases[row["db_id"]]),
            "reference": row["query"],
            "reference_ast": row.get("sql"),
            "prediction": prediction.get("sql"),
            "generation_error": prediction.get("error"),
            "timeout_seconds": timeout,
        }, timeout)
        results.append({"id": example_id, "db_id": row["db_id"], **result})

    return results, {
        "evaluator_revision": _UPSTREAM_REVISION,
        "dependencies": dependencies,
        "python_version": sys.version.split()[0],
        "sqlite_version": sqlite3.sqlite_version,
        "generation_commit": run.get("commit"),
        "split_sha256": split_hash,
        "split_example_count": split_count,
        "is_full_split": len(aligned) == split_count,
        "keep_distinct": True,
        "plug_value": False,
        "timeout_seconds": timeout,
        "database_sha256": {
            db_id: {Path(path).name: digest for path, digest in files.items()}
            for db_id, files in databases.items()
        },
    }
