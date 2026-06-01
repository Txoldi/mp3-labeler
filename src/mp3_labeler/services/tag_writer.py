from __future__ import annotations

from pathlib import Path

from mp3_labeler.infrastructure.metadata_writer import MetadataWriter


class TagWriter:
    def __init__(self, writer: MetadataWriter | None = None) -> None:
        self.writer = writer or MetadataWriter()

    def write_genres(self, files: tuple[Path, ...], genres: tuple[str, ...]) -> None:
        previous = tuple((path, self.writer.read_genres(path)) for path in files)
        try:
            for path in files:
                self.writer.write_genres(path, genres)
                if self.writer.read_genres(path) != genres:
                    raise RuntimeError(f"Genre tag verification failed for: {path}")
        except Exception as write_error:
            rollback_errors: list[Exception] = []
            for path, old_genres in previous:
                try:
                    self.writer.write_genres(path, old_genres)
                except Exception as rollback_error:
                    rollback_errors.append(rollback_error)
            if rollback_errors:
                raise RuntimeError(
                    "Genre tag write failed, and restoring previous genre tags also failed"
                ) from write_error
            raise

    def restore_genres(self, previous: tuple[tuple[Path, tuple[str, ...]], ...]) -> None:
        for path, genres in previous:
            self.writer.write_genres(path, genres)

    def capture_genres(self, files: tuple[Path, ...]) -> tuple[tuple[Path, tuple[str, ...]], ...]:
        return tuple((path, self.writer.read_genres(path)) for path in files)

    def write_genre(self, files: tuple[Path, ...], genre: str, dry_run: bool = True) -> None:
        if not dry_run:
            self.write_genres(files, (genre,))


__all__ = ["TagWriter"]
