from __future__ import annotations

from mp3_labeler.domain.models import AlbumMetadata, ArtistCandidate, LastFmTag


class LastFmLookup:
    def find_artist_candidates(self, metadata: AlbumMetadata) -> tuple[ArtistCandidate, ...]:
        raise NotImplementedError

    def get_album_tags(self, metadata: AlbumMetadata) -> tuple[LastFmTag, ...]:
        raise NotImplementedError

