from __future__ import annotations

from pathlib import Path


class FileSystem:
    def move_album(self, source: Path, destination: Path, dry_run: bool = True) -> None:
        raise NotImplementedError

