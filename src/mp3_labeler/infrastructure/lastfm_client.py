from __future__ import annotations

from typing import Any

import pylast

from mp3_labeler.domain.models import ArtistCandidate, LastFmTag


class LastFmClientError(RuntimeError):
    """Base error for a Last.fm operation that could not be completed."""


class LastFmApiError(LastFmClientError):
    """Last.fm rejected a request or reported a service failure."""


class LastFmConnectionError(LastFmClientError):
    """A Last.fm request could not reach the remote service."""


class LastFmClient:
    def __init__(
        self,
        api_key: str,
        api_secret: str | None = None,
        *,
        network: Any | None = None,
        tag_limit: int | None = 50,
    ) -> None:
        if not api_key.strip() and network is None:
            raise ValueError("Last.fm API key cannot be empty")
        if tag_limit is not None and tag_limit < 1:
            raise ValueError("Last.fm tag limit must be positive or None")

        self.network = network or pylast.LastFMNetwork(api_key=api_key, api_secret=api_secret or "")
        self.tag_limit = tag_limit

    def get_album_tags(self, artist: str, album: str) -> tuple[LastFmTag, ...]:
        try:
            lastfm_album = self.network.get_album(artist, album)
            return self._tags_from_item(lastfm_album, source="album")
        except pylast.WSError as error:
            if self._is_not_found(error):
                return ()
            raise LastFmApiError(f"Last.fm album tag lookup failed for '{artist} - {album}': {error}") from error
        except pylast.NetworkError as error:
            raise LastFmConnectionError(f"Could not connect to Last.fm for album '{artist} - {album}'") from error

    def get_artist_candidate(self, artist_name: str) -> ArtistCandidate | None:
        try:
            artist = self.network.get_artist(artist_name)
            tags = self._tags_from_item(artist, source="artist")
            mbid = artist.get_mbid() or None
            return ArtistCandidate(
                name=artist.get_name() or artist_name,
                url=artist.get_url() or None,
                mbid=mbid,
                tags=tags,
            )
        except pylast.WSError as error:
            if self._is_not_found(error):
                return None
            raise LastFmApiError(f"Last.fm artist lookup failed for '{artist_name}': {error}") from error
        except pylast.NetworkError as error:
            raise LastFmConnectionError(f"Could not connect to Last.fm for artist '{artist_name}'") from error

    def _tags_from_item(self, item: Any, *, source: str) -> tuple[LastFmTag, ...]:
        top_tags = item.get_top_tags(limit=self.tag_limit)
        return tuple(
            LastFmTag(
                name=top_tag.item.get_name().strip(),
                weight=float(top_tag.weight),
                source=source,
            )
            for top_tag in top_tags
            if top_tag.item.get_name().strip()
        )

    @staticmethod
    def _is_not_found(error: pylast.WSError) -> bool:
        return error.get_id() in {pylast.STATUS_INVALID_PARAMS, pylast.STATUS_INVALID_RESOURCE}


__all__ = [
    "LastFmApiError",
    "LastFmClient",
    "LastFmClientError",
    "LastFmConnectionError",
]
