from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from mp3_labeler.domain.models import AlbumMetadata, ExistingGenreEvidence
from mp3_labeler.domain.scoring import ClassificationResult, ReviewItem, ReviewStatus


class ReviewRepositoryProtocol(Protocol):
    def save_pending(self, item: ReviewItem, *, at: datetime) -> ReviewItem: ...

    def list(self, status: ReviewStatus | None = ReviewStatus.PENDING) -> tuple[ReviewItem, ...]: ...

    def get(self, item_id: int) -> ReviewItem | None: ...

    def set_status(self, item_id: int, status: ReviewStatus, *, at: datetime) -> ReviewItem: ...

    def delete(self, item_id: int) -> None: ...


class ReviewQueue:
    def __init__(
        self,
        repository: ReviewRepositoryProtocol,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def add(
        self,
        album_path: Path,
        metadata: AlbumMetadata,
        existing_genre: ExistingGenreEvidence,
        classification: ClassificationResult,
    ) -> ReviewItem:
        winner = classification.winner
        item = ReviewItem(
            id=None,
            album_path=album_path,
            artist=metadata.album_artist or metadata.artist,
            album=metadata.album,
            year=metadata.year,
            existing_genres=existing_genre.raw_values,
            matched_taxonomy_node_ids=existing_genre.matched_taxonomy_node_ids,
            proposed_node_id=winner.taxonomy_node_id if winner is not None else None,
            score=winner.score if winner is not None else None,
            confidence=winner.confidence if winner is not None else None,
            reason=classification.reason,
            conflicts=winner.conflicts if winner is not None else (),
            evidence=winner.evidence if winner is not None else (),
        )
        return self.repository.save_pending(item, at=self.clock())

    def list(self, status: ReviewStatus | None = ReviewStatus.PENDING) -> tuple[ReviewItem, ...]:
        return self.repository.list(status)

    def get(self, item_id: int) -> ReviewItem | None:
        return self.repository.get(item_id)

    def resolve(self, item_id: int, status: ReviewStatus) -> ReviewItem:
        return self.repository.set_status(item_id, status, at=self.clock())

    def remove(self, item_id: int) -> None:
        self.repository.delete(item_id)


__all__ = ["ReviewQueue"]
