from __future__ import annotations

from mp3_labeler.domain.models import Decision


class ReviewQueue:
    def add(self, decision: Decision) -> None:
        raise NotImplementedError

