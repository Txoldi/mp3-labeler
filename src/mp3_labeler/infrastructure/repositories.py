from __future__ import annotations

from mp3_labeler.domain.models import Decision


class DecisionRepository:
    def save(self, decision: Decision) -> None:
        raise NotImplementedError

