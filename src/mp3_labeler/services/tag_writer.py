from __future__ import annotations

from pathlib import Path


class TagWriter:
    def write_genre(self, files: tuple[Path, ...], genre: str, dry_run: bool = True) -> None:
        raise NotImplementedError

