from __future__ import annotations

from collections import namedtuple

import pylast
import pytest

from mp3_labeler.infrastructure.lastfm_client import LastFmApiError, LastFmClient, LastFmConnectionError


TopTag = namedtuple("TopTag", ["item", "weight"])


class FakeTag:
    def __init__(self, name: str) -> None:
        self.name = name

    def get_name(self) -> str:
        return self.name


class FakeAlbum:
    def __init__(self, tags=(), error: Exception | None = None) -> None:
        self.tags = tags
        self.error = error
        self.received_limit: int | None = None

    def get_top_tags(self, limit: int | None = None):
        if self.error is not None:
            raise self.error
        self.received_limit = limit
        return self.tags


class FakeArtist(FakeAlbum):
    def get_name(self) -> str:
        return "Remote Artist"

    def get_url(self) -> str:
        return "https://www.last.fm/music/Remote+Artist"

    def get_mbid(self) -> str:
        return "mbid-value"


class FakeNetwork:
    def __init__(self, *, album: FakeAlbum | None = None, artist: FakeArtist | None = None) -> None:
        self.album = album or FakeAlbum()
        self.artist = artist or FakeArtist()
        self.album_queries: list[tuple[str, str]] = []
        self.artist_queries: list[str] = []

    def get_album(self, artist: str, album: str) -> FakeAlbum:
        self.album_queries.append((artist, album))
        return self.album

    def get_artist(self, artist_name: str) -> FakeArtist:
        self.artist_queries.append(artist_name)
        return self.artist


def test_get_album_tags_translates_weighted_pylast_tags() -> None:
    album = FakeAlbum(tags=(TopTag(FakeTag("Death Metal"), "100"), TopTag(FakeTag(""), "2")))
    client = LastFmClient("key", network=FakeNetwork(album=album), tag_limit=25)

    tags = client.get_album_tags("Artist", "Album")

    assert len(tags) == 1
    assert tags[0].name == "Death Metal"
    assert tags[0].weight == pytest.approx(100.0)
    assert tags[0].source == "album"
    assert album.received_limit == 25


def test_get_artist_candidate_includes_remote_identity_and_tags() -> None:
    artist = FakeArtist(tags=(TopTag(FakeTag("Hardcore"), 80),))
    client = LastFmClient("key", network=FakeNetwork(artist=artist))

    candidate = client.get_artist_candidate("Artist")

    assert candidate is not None
    assert candidate.name == "Remote Artist"
    assert candidate.url == "https://www.last.fm/music/Remote+Artist"
    assert candidate.mbid == "mbid-value"
    assert candidate.tags[0].source == "artist"


def test_missing_lastfm_resource_returns_no_evidence() -> None:
    missing = pylast.WSError(None, pylast.STATUS_INVALID_RESOURCE, "not found")
    client = LastFmClient("key", network=FakeNetwork(album=FakeAlbum(error=missing), artist=FakeArtist(error=missing)))

    assert client.get_album_tags("Artist", "Missing") == ()
    assert client.get_artist_candidate("Missing") is None


def test_api_failures_are_not_interpreted_as_missing_tags() -> None:
    failure = pylast.WSError(None, pylast.STATUS_INVALID_API_KEY, "invalid key")
    client = LastFmClient("key", network=FakeNetwork(album=FakeAlbum(error=failure)))

    with pytest.raises(LastFmApiError, match="album tag lookup"):
        client.get_album_tags("Artist", "Album")


def test_network_failures_are_exposed_explicitly() -> None:
    failure = pylast.NetworkError(None, OSError("offline"))
    client = LastFmClient("key", network=FakeNetwork(album=FakeAlbum(error=failure)))

    with pytest.raises(LastFmConnectionError):
        client.get_album_tags("Artist", "Album")


def test_client_requires_api_key_when_not_supplied_a_network() -> None:
    with pytest.raises(ValueError, match="API key"):
        LastFmClient("")
