from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    inbox: Path
    library: Path
    cache_db: Path
    taxonomy_file: Path
    overrides_file: Path | None = None

