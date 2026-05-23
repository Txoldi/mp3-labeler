from __future__ import annotations

from pathlib import Path


class MetadataWriter:
    def write_genre(self, path: Path, genre: str) -> None:
        raise NotImplementedError

