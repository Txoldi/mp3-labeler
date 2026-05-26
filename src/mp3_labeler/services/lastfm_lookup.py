from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Protocol

from mp3_labeler.domain.models import (
    AlbumMetadata,
    ArtistCandidate,
    LastFmAlbumLookupResult,
    LastFmArtistLookupResult,
    LastFmLookupStatus,
    LastFmTag,
)
from mp3_labeler.infrastructure.repositories import CachedAlbumLookup, CachedArtistLookup


class InsufficientMetadataError(ValueError):
    """Raised when local tags do not identify an item well enough to query."""


class LastFmClientProtocol(Protocol):
    def lookup_album(self, artist: str, album: str) -> LastFmAlbumLookupResult: ...

    def lookup_artist(self, artist_name: str) -> LastFmArtistLookupResult: ...


class LastFmCacheProtocol(Protocol):
    def get_album(
        self, artist_query: str, album_query: str, *, at: datetime | None = None
    ) -> CachedAlbumLookup | None: ...

    def save_album(self, result: LastFmAlbumLookupResult, *, fetched_at: datetime, expires_at: datetime) -> None: ...

    def get_artist(self, artist_query: str, *, at: datetime | None = None) -> CachedArtistLookup | None: ...

    def save_artist(
        self, result: LastFmArtistLookupResult, *, fetched_at: datetime, expires_at: datetime
    ) -> None: ...


class LastFmLookup:
    def __init__(
        self,
        client: LastFmClientProtocol,
        *,
        cache: LastFmCacheProtocol | None = None,
        clock: Callable[[], datetime] | None = None,
        success_ttl: timedelta = timedelta(days=30),
        not_found_ttl: timedelta = timedelta(days=7),
    ) -> None:
        self.client = client
        self.cache = cache
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.success_ttl = success_ttl
        self.not_found_ttl = not_found_ttl

    def find_artist_candidates(
        self, metadata: AlbumMetadata, *, refresh: bool = False
    ) -> tuple[ArtistCandidate, ...]:
        artist = self._required_artist(metadata)
        result = self._lookup_artist(artist, refresh=refresh)
        return () if result.candidate is None else (result.candidate,)

    def get_album_tags(self, metadata: AlbumMetadata, *, refresh: bool = False) -> tuple[LastFmTag, ...]:
        artist = self._required_artist(metadata)
        album = self._required_album(metadata)
        return self._lookup_album(artist, album, refresh=refresh).tags

    def get_artist_tags(self, metadata: AlbumMetadata, *, refresh: bool = False) -> tuple[LastFmTag, ...]:
        candidates = self.find_artist_candidates(metadata, refresh=refresh)
        return () if not candidates else candidates[0].tags

    def get_tags(self, metadata: AlbumMetadata, *, refresh: bool = False) -> tuple[LastFmTag, ...]:
        return self.get_album_tags(metadata, refresh=refresh) + self.get_artist_tags(metadata, refresh=refresh)

    def _lookup_album(self, artist: str, album: str, *, refresh: bool) -> LastFmAlbumLookupResult:
        now = self.clock()
        if self.cache is not None and not refresh:
            cached = self.cache.get_album(artist, album, at=now)
            if cached is not None:
                return cached.result

        result = self.client.lookup_album(artist, album)
        if self.cache is not None:
            self.cache.save_album(result, fetched_at=now, expires_at=now + self._ttl_for(result.status))
        return result

    def _lookup_artist(self, artist: str, *, refresh: bool) -> LastFmArtistLookupResult:
        now = self.clock()
        if self.cache is not None and not refresh:
            cached = self.cache.get_artist(artist, at=now)
            if cached is not None:
                return cached.result

        result = self.client.lookup_artist(artist)
        if self.cache is not None:
            self.cache.save_artist(result, fetched_at=now, expires_at=now + self._ttl_for(result.status))
        return result

    def _ttl_for(self, status: LastFmLookupStatus) -> timedelta:
        return self.success_ttl if status is LastFmLookupStatus.FOUND else self.not_found_ttl

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
