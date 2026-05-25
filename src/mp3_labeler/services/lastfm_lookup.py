from __future__ import annotations

from typing import Protocol

from mp3_labeler.domain.models import AlbumMetadata, ArtistCandidate, LastFmTag


class InsufficientMetadataError(ValueError):
    """Raised when local tags do not identify an item well enough to query."""


class LastFmClientProtocol(Protocol):
    def get_album_tags(self, artist: str, album: str) -> tuple[LastFmTag, ...]: ...

    def get_artist_candidate(self, artist_name: str) -> ArtistCandidate | None: ...


class LastFmLookup:
    def __init__(self, client: LastFmClientProtocol) -> None:
        self.client = client

    def find_artist_candidates(self, metadata: AlbumMetadata) -> tuple[ArtistCandidate, ...]:
        artist = self._required_artist(metadata)
        candidate = self.client.get_artist_candidate(artist)
        return () if candidate is None else (candidate,)

    def get_album_tags(self, metadata: AlbumMetadata) -> tuple[LastFmTag, ...]:
        artist = self._required_artist(metadata)
        album = self._required_album(metadata)
        return self.client.get_album_tags(artist, album)

    def get_artist_tags(self, metadata: AlbumMetadata) -> tuple[LastFmTag, ...]:
        candidates = self.find_artist_candidates(metadata)
        return () if not candidates else candidates[0].tags

    def get_tags(self, metadata: AlbumMetadata) -> tuple[LastFmTag, ...]:
        return self.get_album_tags(metadata) + self.get_artist_tags(metadata)

    @staticmethod
    def _required_artist(metadata: AlbumMetadata) -> str:
        artist = (metadata.album_artist or metadata.artist or "").strip()
        if not artist:
            raise InsufficientMetadataError("Last.fm lookup requires an album artist or artist")
        return artist

    @staticmethod
    def _required_album(metadata: AlbumMetadata) -> str:
        album = (metadata.album or "").strip()
        if not album:
            raise InsufficientMetadataError("Last.fm album lookup requires an album title")
        return album


__all__ = ["InsufficientMetadataError", "LastFmLookup"]
