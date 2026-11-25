"""Select a dataset adapter by its configured format."""

from pathlib import Path

from ..dataset import LoadedDataset, load_jsonl
from .spider import load_spider

_LOADERS = {"jsonl": load_jsonl, "spider": load_spider}


def load_dataset(path: Path, dataset_format: str) -> LoadedDataset:
    if dataset_format not in _LOADERS:
        available = ", ".join(sorted(_LOADERS))
        raise ValueError(f"unknown dataset.format {dataset_format!r}; expected one of: {available}")
    return _LOADERS[dataset_format](path)
