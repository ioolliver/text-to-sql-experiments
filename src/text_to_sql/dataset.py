"""Load examples with their complete SQL schemas."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LoadedDataset:
    examples: list[dict[str, str]]
    sha256: str
    schema_sha256: dict[str, str] | None = None


def load_examples(path: Path) -> tuple[list[dict[str, str]], str]:
    data = path.read_bytes()
    examples = []
    seen_ids = set()
    for line_number, line in enumerate(data.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            example = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(example, dict) or any(
            not isinstance(example.get(field), str) or not example[field].strip()
            for field in ("id", "question", "schema")
        ):
            raise ValueError(f"{path}:{line_number}: expected nonempty id, question and schema")
        if example["id"] in seen_ids:
            raise ValueError(f"{path}:{line_number}: duplicate id {example['id']!r}")
        seen_ids.add(example["id"])
        examples.append(example)
    if not examples:
        raise ValueError(f"{path}: no examples found")
    return examples, hashlib.sha256(data).hexdigest()


def load_jsonl(path: Path) -> LoadedDataset:
    examples, sha256 = load_examples(path)
    return LoadedDataset(examples=examples, sha256=sha256)
