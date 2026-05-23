from __future__ import annotations

from pathlib import Path

from mp3_labeler.domain.models import AlbumFolder


class InboxScanner:
    def scan(self, inbox: Path) -> tuple[AlbumFolder, ...]:
        raise NotImplementedError

