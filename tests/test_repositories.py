from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mp3_labeler.domain.models import (
    ArtistCandidate,
    LastFmAlbumLookupResult,
    LastFmArtistLookupResult,
    LastFmLookupStatus,
    LastFmTag,
)
from mp3_labeler.infrastructure.db import open_connection
from mp3_labeler.infrastructure.repositories import LastFmCacheRepository


def test_open_connection_initializes_lastfm_cache_schema(tmp_path) -> None:
    connection = open_connection(tmp_path / "nested" / "cache.sqlite3")
    names = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'lastfm_%'"
        )
    }

    assert names == {
        "lastfm_album_lookup",
        "lastfm_album_tag",
        "lastfm_artist_lookup",
        "lastfm_artist_tag",
    }


def test_album_cache_round_trips_tags_using_normalized_query_keys(tmp_path) -> None:
    now = datetime(2026, 5, 26, tzinfo=timezone.utc)
    repository = LastFmCacheRepository(open_connection(tmp_path / "cache.sqlite3"))
    repository.save_album(
        LastFmAlbumLookupResult(
            artist_query="Class  Traitor",
            album_query="The Images Aren't Mine",
            status=LastFmLookupStatus.FOUND,
            tags=(
                LastFmTag("metalcore", 100.0, "album"),
                LastFmTag("hardcore", 75.0, "album"),
            ),
        ),
        fetched_at=now,
        expires_at=now + timedelta(days=30),
    )

    cached = repository.get_album(" class traitor ", "THE IMAGES AREN'T MINE", at=now)

    assert cached is not None
    assert cached.result.artist_query == "Class  Traitor"
    assert [tag.name for tag in cached.result.tags] == ["metalcore", "hardcore"]


def test_artist_cache_round_trips_candidate_details_and_tags(tmp_path) -> None:
    now = datetime(2026, 5, 26, tzinfo=timezone.utc)
    repository = LastFmCacheRepository(open_connection(tmp_path / "cache.sqlite3"))
    candidate = ArtistCandidate(
        name="Remote Artist",
        url="https://last.fm/artist",
        mbid="mbid",
        listeners=42,
        playcount=100,
        tags=(LastFmTag("punk", 50.0, "artist"),),
        similar_artists=("Peer Band",),
    )
    repository.save_artist(
        LastFmArtistLookupResult("Artist", LastFmLookupStatus.FOUND, candidate),
        fetched_at=now,
        expires_at=now + timedelta(days=30),
    )

    cached = repository.get_artist("artist", at=now)

    assert cached is not None
    assert cached.result.candidate == candidate


def test_expired_repository_result_is_not_returned(tmp_path) -> None:
    now = datetime(2026, 5, 26, tzinfo=timezone.utc)
    repository = LastFmCacheRepository(open_connection(tmp_path / "cache.sqlite3"))
    repository.save_artist(
        LastFmArtistLookupResult("Missing", LastFmLookupStatus.NOT_FOUND),
        fetched_at=now - timedelta(days=8),
        expires_at=now - timedelta(days=1),
    )

    assert repository.get_artist("Missing", at=now) is None
