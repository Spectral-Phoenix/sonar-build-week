"""Validated, atomic persistence for dashboard-edited benchmark definitions."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import yaml

from charwatch.domain.models import Dimension

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def save_dimension(directory: Path, dimension: Dimension, *, create: bool) -> None:
    """Persist one validated dimension without exposing arbitrary filesystem paths."""
    if not _KEY_PATTERN.fullmatch(dimension.key):
        raise ValueError(
            "behavior key must start with a letter and contain only lowercase letters, "
            "numbers, and underscores"
        )
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{dimension.key}.yaml"
    if create and destination.exists():
        raise FileExistsError(f"behavior {dimension.key!r} already exists")
    if not create and not destination.exists():
        raise FileNotFoundError(f"behavior {dimension.key!r} does not exist")

    content = yaml.safe_dump(
        dimension.model_dump(mode="json"),
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=directory,
            prefix=f".{dimension.key}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        Path(temporary_name).replace(destination)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
