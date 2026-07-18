"""Load behavioral dimensions from YAML into validated domain objects."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from charwatch.domain.models import BenchmarkSuite, Dimension


class BenchmarkLoadError(RuntimeError):
    """Raised when a benchmark file is missing, malformed, or inconsistent."""


def load_dimension(path: Path) -> Dimension:
    """Parse and validate a single dimension YAML file."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise BenchmarkLoadError(f"could not read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise BenchmarkLoadError(f"{path} must contain a mapping at the top level")
    try:
        dimension = Dimension.model_validate(raw)
    except ValidationError as exc:
        raise BenchmarkLoadError(f"invalid dimension in {path}:\n{exc}") from exc

    case_ids = dimension.case_ids()
    duplicates = {cid for cid in case_ids if case_ids.count(cid) > 1}
    if duplicates:
        raise BenchmarkLoadError(f"{path} has duplicate case ids: {sorted(duplicates)}")
    return dimension


def load_suite(directory: Path) -> BenchmarkSuite:
    """Load every ``*.yaml`` dimension in ``directory`` into a validated suite."""
    if not directory.is_dir():
        raise BenchmarkLoadError(f"benchmarks directory not found: {directory}")
    paths = sorted(directory.glob("*.yaml"))
    if not paths:
        raise BenchmarkLoadError(f"no benchmark files found in {directory}")

    dimensions = [load_dimension(path) for path in paths]
    keys = [d.key for d in dimensions]
    duplicates = {k for k in keys if keys.count(k) > 1}
    if duplicates:
        raise BenchmarkLoadError(f"duplicate dimension keys across files: {sorted(duplicates)}")
    return BenchmarkSuite(dimensions=dimensions)
