from __future__ import annotations

from mp3_labeler.domain.models import AlbumMetadata, ArtistCandidate, LastFmTag
from mp3_labeler.services.lastfm_lookup import InsufficientMetadataError, LastFmLookup

import pytest


class FakeLastFmClient:
    def __init__(
        self,
        *,
        album_tags: tuple[LastFmTag, ...] = (),
        artist_candidate: ArtistCandidate | None = None,
    ) -> None:
        self.album_tags = album_tags
        self.artist_candidate = artist_candidate
        self.album_queries: list[tuple[str, str]] = []
        self.artist_queries: list[str] = []

    def get_album_tags(self, artist: str, album: str) -> tuple[LastFmTag, ...]:
        self.album_queries.append((artist, album))
        return self.album_tags

    def get_artist_candidate(self, artist_name: str) -> ArtistCandidate | None:
        self.artist_queries.append(artist_name)
        return self.artist_candidate


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
    client = FakeLastFmClient(album_tags=(tag,))

    tags = LastFmLookup(client).get_album_tags(
        album_metadata(artist="Track Artist", album_artist="Album Artist", album="Record")
    )

    assert tags == (tag,)
    assert client.album_queries == [("Album Artist", "Record")]


def test_find_artist_candidates_returns_single_lastfm_candidate() -> None:
    candidate = ArtistCandidate(name="Artist", tags=(LastFmTag("hardcore", 80.0, "artist"),))
    client = FakeLastFmClient(artist_candidate=candidate)

    candidates = LastFmLookup(client).find_artist_candidates(album_metadata())

    assert candidates == (candidate,)
    assert client.artist_queries == ["Artist"]


def test_find_artist_candidates_returns_empty_when_client_has_no_match() -> None:
    assert LastFmLookup(FakeLastFmClient()).find_artist_candidates(album_metadata()) == ()


def test_get_tags_preserves_album_and_artist_tag_sources() -> None:
    album_tag = LastFmTag(name="metalcore", weight=100.0, source="album")
    artist_tag = LastFmTag(name="hardcore", weight=75.0, source="artist")
    client = FakeLastFmClient(
        album_tags=(album_tag,),
        artist_candidate=ArtistCandidate(name="Artist", tags=(artist_tag,)),
    )

    tags = LastFmLookup(client).get_tags(album_metadata())

    assert tags == (album_tag, artist_tag)


def test_artist_lookup_requires_artist_identity() -> None:
    with pytest.raises(InsufficientMetadataError, match="artist"):
        LastFmLookup(FakeLastFmClient()).find_artist_candidates(album_metadata(artist=None))


def test_album_lookup_requires_album_identity() -> None:
    with pytest.raises(InsufficientMetadataError, match="album title"):
        LastFmLookup(FakeLastFmClient()).get_album_tags(album_metadata(album=None))
