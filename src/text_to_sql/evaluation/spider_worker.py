"""Execute one Spider example in a subprocess with read-only SQLite connections."""

import json
import random
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from time import monotonic

_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE}


def authorize(action, first, second, database, source):
    if action in _ALLOWED_ACTIONS or (
        action == sqlite3.SQLITE_FUNCTION and second.lower() != "load_extension"
    ):
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def execute(path: str, query: str, timeout: float) -> list[tuple]:
    uri = Path(path).as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=timeout)) as db:
        db.execute("PRAGMA query_only = ON")
        db.execute("PRAGMA trusted_schema = OFF")
        db.execute("PRAGMA temp_store = MEMORY")
        db.text_factory = lambda value: value.decode(errors="ignore")
        db.set_authorizer(authorize)
        deadline = monotonic() + timeout
        db.set_progress_handler(lambda: int(monotonic() >= deadline), 1000)
        return db.execute(query).fetchall()


def evaluate(payload: dict) -> dict:
    sys.path.insert(0, payload["upstream_dir"])
    from evaluation import Evaluator
    from exec_eval import postprocess, replace_cur_year, result_eq

    def prepare(query: str) -> str:
        return replace_cur_year(postprocess(query))

    difficulty = Evaluator().eval_hardness(payload["reference_ast"]) if payload["reference_ast"] else None
    reference = prepare(payload["reference"])
    order_matters = "order by" in postprocess(payload["reference"]).lower()
    prediction = payload["prediction"]
    timeout = payload["timeout_seconds"]
    status, error, failing_database = "correct", None, None
    if payload["generation_error"] or not prediction or not prediction.strip():
        status = "generation_error"
        error = payload["generation_error"] or "no SQL prediction"
    else:
        prediction = prepare(prediction)

    random.seed(0)
    for database in payload["databases"]:
        try:
            expected = execute(database, reference, timeout)
        except (sqlite3.Error, OverflowError, ValueError) as exc:
            status, error, failing_database = "gold_error", str(exc), Path(database).name
            break
        if status != "correct":
            continue
        try:
            actual = execute(database, prediction, timeout)
        except (sqlite3.Error, OverflowError, ValueError) as exc:
            status, error, failing_database = "prediction_error", str(exc), Path(database).name
            continue
        if not result_eq(expected, actual, order_matters=order_matters):
            status, failing_database = "incorrect", Path(database).name

    return {
        "status": status, "difficulty": difficulty, "error": error,
        "failing_database": failing_database,
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(json.load(sys.stdin))))
