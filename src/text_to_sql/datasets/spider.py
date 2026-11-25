"""Adapt a native Spider 1.0 split and its SQLite databases."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from ..dataset import LoadedDataset


def read_schema(path: Path) -> str:
    try:
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as db:
            definitions = db.execute(
                """
                SELECT sql
                FROM sqlite_schema
                WHERE type IN ('table', 'view')
                  AND substr(name, 1, 7) <> 'sqlite_'
                  AND sql IS NOT NULL
                ORDER BY type, name
                """
            ).fetchall()
    except sqlite3.Error as exc:
        raise ValueError(f"cannot read Spider schema from {path}: {exc}") from exc
    if not definitions:
        raise ValueError(f"{path}: no table or view definitions found")
    return "\n\n".join(statement.rstrip().removesuffix(";") + ";" for (statement,) in definitions)


def load_spider(path: Path) -> LoadedDataset:
    data = path.read_bytes()
    rows = json.loads(data)
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{path}: expected a nonempty Spider split array")

    schemas = {}
    examples = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"{path}: example {index} must be an object")
        db_id = row.get("db_id")
        question = row.get("question")
        if (
            not isinstance(db_id, str)
            or not db_id.strip()
            or db_id in {".", ".."}
            or any(char in db_id for char in "/\\\0")
            or not isinstance(question, str)
            or not question.strip()
        ):
            raise ValueError(f"{path}: example {index} requires a valid db_id and question")
        if db_id not in schemas:
            schemas[db_id] = read_schema(path.parent / "database" / db_id / f"{db_id}.sqlite")
        examples.append({
            "id": f"{path.stem}:{index:04d}",
            "db_id": db_id,
            "question": question,
            "schema": schemas[db_id],
        })

    return LoadedDataset(
        examples=examples,
        sha256=hashlib.sha256(data).hexdigest(),
        schema_sha256={
            db_id: hashlib.sha256(schema.encode("utf-8")).hexdigest()
            for db_id, schema in sorted(schemas.items())
        },
    )
