from __future__ import annotations

from mp3_labeler.domain.models import Decision


class AlbumOrganizer:
    def apply(self, decision: Decision) -> None:
        raise NotImplementedError

