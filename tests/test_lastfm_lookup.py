from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mp3_labeler.domain.models import (
    AlbumMetadata,
    ArtistCandidate,
    LastFmAlbumLookupResult,
    LastFmArtistLookupResult,
    LastFmLookupStatus,
    LastFmTag,
)
from mp3_labeler.infrastructure.db import open_connection
from mp3_labeler.infrastructure.lastfm_client import LastFmConnectionError
from mp3_labeler.infrastructure.repositories import LastFmCacheRepository
from mp3_labeler.services.lastfm_lookup import InsufficientMetadataError, LastFmLookup


class FakeLastFmClient:
    def __init__(
        self,
        *,
        album_result: LastFmAlbumLookupResult | None = None,
        artist_result: LastFmArtistLookupResult | None = None,
    ) -> None:
        self.album_result = album_result or LastFmAlbumLookupResult(
            artist_query="Artist",
            album_query="Album",
            status=LastFmLookupStatus.FOUND,
        )
        self.artist_result = artist_result or LastFmArtistLookupResult(
            artist_query="Artist",
            status=LastFmLookupStatus.NOT_FOUND,
        )
        self.album_queries: list[tuple[str, str]] = []
        self.artist_queries: list[str] = []

    def lookup_album(self, artist: str, album: str) -> LastFmAlbumLookupResult:
        self.album_queries.append((artist, album))
        return LastFmAlbumLookupResult(
            artist_query=artist,
            album_query=album,
            status=self.album_result.status,
            tags=self.album_result.tags,
        )

    def lookup_artist(self, artist_name: str) -> LastFmArtistLookupResult:
        self.artist_queries.append(artist_name)
        return LastFmArtistLookupResult(
            artist_query=artist_name,
            status=self.artist_result.status,
            candidate=self.artist_result.candidate,
        )


def album_metadata(
    *,
    artist: str | None = "Artist",
    album_artist: str | None = None,
    album: str | None = "Album",
) -> AlbumMetadata:
    return AlbumMetadata(
        artist=artist,
        album=album,
        album_artist=album_artist,
        year=None,
        tracks=(),
        confidence=1.0,
        source="track_metadata",
    )


def test_get_album_tags_queries_with_album_artist_when_available() -> None:
    tag = LastFmTag(name="death metal", weight=100.0, source="album")
    client = FakeLastFmClient(
        album_result=LastFmAlbumLookupResult("x", "x", LastFmLookupStatus.FOUND, (tag,))
    )

    tags = LastFmLookup(client).get_album_tags(
        album_metadata(artist="Track Artist", album_artist="Album Artist", album="Record")
    )

    assert tags == (tag,)
    assert client.album_queries == [("Album Artist", "Record")]


def test_find_artist_candidates_returns_single_lastfm_candidate() -> None:
    candidate = ArtistCandidate(name="Artist", tags=(LastFmTag("hardcore", 80.0, "artist"),))
    client = FakeLastFmClient(
        artist_result=LastFmArtistLookupResult("Artist", LastFmLookupStatus.FOUND, candidate)
    )

    candidates = LastFmLookup(client).find_artist_candidates(album_metadata())

    assert candidates == (candidate,)
    assert client.artist_queries == ["Artist"]


def test_find_artist_candidates_returns_empty_when_client_has_no_match() -> None:
    assert LastFmLookup(FakeLastFmClient()).find_artist_candidates(album_metadata()) == ()


def test_get_tags_preserves_album_and_artist_tag_sources() -> None:
    album_tag = LastFmTag(name="metalcore", weight=100.0, source="album")
    artist_tag = LastFmTag(name="hardcore", weight=75.0, source="artist")
    client = FakeLastFmClient(
        album_result=LastFmAlbumLookupResult("Artist", "Album", LastFmLookupStatus.FOUND, (album_tag,)),
        artist_result=LastFmArtistLookupResult(
            "Artist",
            LastFmLookupStatus.FOUND,
            ArtistCandidate(name="Artist", tags=(artist_tag,)),
        ),
    )

    tags = LastFmLookup(client).get_tags(album_metadata())

    assert tags == (album_tag, artist_tag)


def test_artist_lookup_requires_artist_identity() -> None:
    with pytest.raises(InsufficientMetadataError, match="artist"):
        LastFmLookup(FakeLastFmClient()).find_artist_candidates(album_metadata(artist=None))


def test_album_lookup_requires_album_identity() -> None:
    with pytest.raises(InsufficientMetadataError, match="album title"):
        LastFmLookup(FakeLastFmClient()).get_album_tags(album_metadata(album=None))


def test_lookup_uses_fresh_cache_without_calling_client(tmp_path) -> None:
    now = datetime(2026, 5, 26, tzinfo=timezone.utc)
    cache = LastFmCacheRepository(open_connection(tmp_path / "cache.sqlite3"))
    cached_tag = LastFmTag("cached metal", 99.0, "album")
    cache.save_album(
        LastFmAlbumLookupResult("Artist", "Album", LastFmLookupStatus.FOUND, (cached_tag,)),
        fetched_at=now,
        expires_at=now + timedelta(days=30),
    )
    client = FakeLastFmClient()

    tags = LastFmLookup(client, cache=cache, clock=lambda: now).get_album_tags(album_metadata())

    assert tags == (cached_tag,)
    assert client.album_queries == []


def test_expired_cache_is_replaced_from_client(tmp_path) -> None:
    now = datetime(2026, 5, 26, tzinfo=timezone.utc)
    cache = LastFmCacheRepository(open_connection(tmp_path / "cache.sqlite3"))
    cache.save_album(
        LastFmAlbumLookupResult(
            "Artist",
            "Album",
            LastFmLookupStatus.FOUND,
            (LastFmTag("stale", 1.0, "album"),),
        ),
        fetched_at=now - timedelta(days=31),
        expires_at=now - timedelta(days=1),
    )
    fresh_tag = LastFmTag("fresh", 100.0, "album")
    client = FakeLastFmClient(
        album_result=LastFmAlbumLookupResult("Artist", "Album", LastFmLookupStatus.FOUND, (fresh_tag,))
    )

    tags = LastFmLookup(client, cache=cache, clock=lambda: now).get_album_tags(album_metadata())

    assert tags == (fresh_tag,)
    assert client.album_queries == [("Artist", "Album")]
    assert cache.get_album("Artist", "Album", at=now).result.tags == (fresh_tag,)


def test_not_found_results_are_cached_for_seven_days(tmp_path) -> None:
    now = datetime(2026, 5, 26, tzinfo=timezone.utc)
    cache = LastFmCacheRepository(open_connection(tmp_path / "cache.sqlite3"))
    client = FakeLastFmClient(
        album_result=LastFmAlbumLookupResult("Artist", "Album", LastFmLookupStatus.NOT_FOUND)
    )
    lookup = LastFmLookup(client, cache=cache, clock=lambda: now)

    assert lookup.get_album_tags(album_metadata()) == ()
    saved = cache.get_album("Artist", "Album", at=now + timedelta(days=6))

    assert saved is not None
    assert saved.result.status is LastFmLookupStatus.NOT_FOUND
    assert saved.expires_at == now + timedelta(days=7)


def test_refresh_bypasses_fresh_cache_and_replaces_it(tmp_path) -> None:
    now = datetime(2026, 5, 26, tzinfo=timezone.utc)
    cache = LastFmCacheRepository(open_connection(tmp_path / "cache.sqlite3"))
    cache.save_album(
        LastFmAlbumLookupResult(
            "Artist",
            "Album",
            LastFmLookupStatus.FOUND,
            (LastFmTag("cached", 1.0, "album"),),
        ),
        fetched_at=now,
        expires_at=now + timedelta(days=30),
    )
    client = FakeLastFmClient(
        album_result=LastFmAlbumLookupResult(
            "Artist",
            "Album",
            LastFmLookupStatus.FOUND,
            (LastFmTag("refreshed", 100.0, "album"),),
        )
    )

    tags = LastFmLookup(client, cache=cache, clock=lambda: now).get_album_tags(
        album_metadata(), refresh=True
    )

    assert tags[0].name == "refreshed"
    assert client.album_queries == [("Artist", "Album")]


def test_connection_errors_are_not_cached_as_missing_results(tmp_path) -> None:
    now = datetime(2026, 5, 26, tzinfo=timezone.utc)
    cache = LastFmCacheRepository(open_connection(tmp_path / "cache.sqlite3"))

    class FailingClient(FakeLastFmClient):
        def lookup_album(self, artist: str, album: str) -> LastFmAlbumLookupResult:
            raise LastFmConnectionError("offline")

    with pytest.raises(LastFmConnectionError):
        LastFmLookup(FailingClient(), cache=cache, clock=lambda: now).get_album_tags(album_metadata())

    assert cache.get_album("Artist", "Album", at=now) is None
