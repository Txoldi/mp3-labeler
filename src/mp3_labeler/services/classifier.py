from __future__ import annotations

from mp3_labeler.domain.models import AlbumMetadata, ExistingGenreEvidence, LastFmTag
from mp3_labeler.domain.scoring import ClassificationResult
from mp3_labeler.domain.taxonomy import Taxonomy


class AlbumClassifier:
    def classify(
        self,
        metadata: AlbumMetadata,
        tags: tuple[LastFmTag, ...],
        taxonomy: Taxonomy,
        existing_genre: ExistingGenreEvidence | None = None,
    ) -> ClassificationResult:
        raise NotImplementedError

