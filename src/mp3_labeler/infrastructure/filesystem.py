from __future__ import annotations

from pathlib import Path
import shutil


class FileSystem:
    def validate_album_move(self, source: Path, destination: Path) -> None:
        if not source.exists():
            raise FileNotFoundError(f"Album source does not exist: {source}")
        if not source.is_dir():
            raise NotADirectoryError(f"Album source is not a directory: {source}")
        if destination.exists():
            raise FileExistsError(f"Destination album folder already exists: {destination}")

        resolved_source = source.resolve()
        resolved_destination = destination.resolve()
        if resolved_source == resolved_destination:
            raise ValueError("Source and destination album folders are the same")
        if resolved_destination.is_relative_to(resolved_source):
            raise ValueError("Destination album folder cannot be inside the source album folder")

    def move_album(self, source: Path, destination: Path, dry_run: bool = True) -> None:
        self.validate_album_move(source, destination)
        if dry_run:
            return

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))


__all__ = ["FileSystem"]
