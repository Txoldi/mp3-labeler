from __future__ import annotations

import os
from pathlib import Path

from mp3_labeler.domain.models import Decision


class ApplyPreflightValidator:
    def validate_database_path(self, database_path: Path) -> None:
        parent = database_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        self._require_writable_directory(parent, "Database parent directory")
        if database_path.exists():
            self._require_writable_file(database_path, "SQLite database")

    def validate_decision(self, decision: Decision, *, write_tags: bool) -> None:
        if decision.destination_path is None:
            raise ValueError("A move decision requires a destination path")
        if write_tags:
            for path in decision.album_folder.audio_files:
                self._require_writable_file(path, "Audio file")

        destination_parent = decision.destination_path.parent
        destination_parent.mkdir(parents=True, exist_ok=True)
        self._require_writable_directory(destination_parent, "Destination parent directory")

    def _require_writable_file(self, path: Path, label: str) -> None:
        if not path.exists():
            raise FileNotFoundError(f"{label} does not exist: {path}")
        if not path.is_file():
            raise IsADirectoryError(f"{label} is not a file: {path}")
        if not os.access(path, os.W_OK):
            raise PermissionError(f"{label} is not writable: {path}")
        with path.open("r+b"):
            pass

    def _require_writable_directory(self, path: Path, label: str) -> None:
        if not path.exists():
            raise FileNotFoundError(f"{label} does not exist: {path}")
        if not path.is_dir():
            raise NotADirectoryError(f"{label} is not a directory: {path}")
        if not os.access(path, os.W_OK):
            raise PermissionError(f"{label} is not writable: {path}")

        probe = path / ".mp3-labeler-write-test"
        counter = 0
        while probe.exists():
            counter += 1
            probe = path / f".mp3-labeler-write-test-{counter}"
        try:
            probe.write_text("", encoding="utf-8")
        finally:
            if probe.exists():
                probe.unlink()


__all__ = ["ApplyPreflightValidator"]
