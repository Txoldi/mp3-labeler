from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from mp3_labeler.domain.models import AlbumFolder


class InboxScanner:
    def __init__(
        self,
        *,
        supported_extensions: frozenset[str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.supported_extensions = supported_extensions or frozenset({".mp3"})
        self.clock = clock or datetime.now

    def scan(self, inbox: Path) -> tuple[AlbumFolder, ...]:
        if not inbox.exists():
            raise FileNotFoundError(f"Inbox folder does not exist: {inbox}")
        if not inbox.is_dir():
            raise NotADirectoryError(f"Inbox path is not a folder: {inbox}")

        albums: list[AlbumFolder] = []
        for child in sorted(inbox.iterdir(), key=lambda path: path.name.casefold()):
            if not child.is_dir() or self._should_ignore_path(child):
                continue

            audio_files = self._find_audio_files(child)
            if not audio_files:
                continue

            albums.append(
                AlbumFolder(
                    path=child,
                    audio_files=audio_files,
                    discovered_at=self.clock(),
                )
            )

        return tuple(albums)

    def _find_audio_files(self, album_path: Path) -> tuple[Path, ...]:
        audio_files = [
            path
            for path in album_path.rglob("*")
            if path.is_file()
            and not self._is_inside_ignored_directory(path, album_path)
            and not self._should_ignore_path(path)
            and path.suffix.casefold() in self.supported_extensions
        ]
        return tuple(sorted(audio_files, key=lambda path: str(path).casefold()))

    @staticmethod
    def _is_inside_ignored_directory(path: Path, root: Path) -> bool:
        relative_parts = path.relative_to(root).parts[:-1]
        return any(InboxScanner._should_ignore_name(part) for part in relative_parts)

    @staticmethod
    def _should_ignore_path(path: Path) -> bool:
        return InboxScanner._should_ignore_name(path.name)

    @staticmethod
    def _should_ignore_name(name: str) -> bool:
        lowered = name.casefold()
        return (
            lowered.startswith(".")
            or lowered.endswith(".tmp")
            or lowered.endswith(".temp")
            or lowered.endswith(".part")
            or lowered.endswith(".crdownload")
            or lowered in {"tmp", "temp", "__macosx"}
        )
