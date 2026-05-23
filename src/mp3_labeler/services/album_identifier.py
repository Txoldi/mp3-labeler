from __future__ import annotations

from mp3_labeler.domain.models import AlbumMetadata, ArtistCandidate


class AlbumIdentifier:
    def identify(self, metadata: AlbumMetadata) -> tuple[ArtistCandidate, ...]:
        raise NotImplementedError

