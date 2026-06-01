from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from mp3_labeler.domain.models import AlbumMetadata, ExistingGenreEvidence
from mp3_labeler.domain.scoring import ClassificationResult, ReviewStatus, ScoreEvidence, TaxonomyScore
from mp3_labeler.infrastructure.db import open_connection
from mp3_labeler.infrastructure.repositories import ReviewRepository
from mp3_labeler.services.review_queue import ReviewQueue


def test_add_persists_classification_evidence_as_pending_review(tmp_path) -> None:
    now = datetime(2026, 5, 27, tzinfo=timezone.utc)
    queue = ReviewQueue(ReviewRepository(open_connection(tmp_path / "db.sqlite3")), clock=lambda: now)
    metadata = AlbumMetadata("Artist", "Album", "Artist", 2026, (), 1.0, "track_metadata")
    existing = ExistingGenreEvidence(("Metal",), ("metal",), ("metal",), 1.0, 2)
    score = TaxonomyScore(
        "metal",
        1.05,
        1.0,
        (ScoreEvidence("existing_genre", "existing genre matches Metal", 1.05),),
        (),
    )

    item = queue.add(
        Path("inbox/Artist - Album"),
        metadata,
        existing,
        ClassificationResult(score, (), True, "broad top-level category"),
    )

    assert item.id is not None
    assert item.status is ReviewStatus.PENDING
    assert item.proposed_node_id == "metal"
    assert item.evidence == score.evidence
    assert queue.get(item.id) == item
    queue.remove(item.id)
    assert queue.get(item.id) is None
