from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from sqlite3 import Connection

from mp3_labeler.domain.models import (
    ArtistCandidate,
    Decision,
    LastFmAlbumLookupResult,
    LastFmArtistLookupResult,
    LastFmLookupStatus,
    LastFmTag,
)


@dataclass(frozen=True, slots=True)
class CachedAlbumLookup:
    result: LastFmAlbumLookupResult
    fetched_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class CachedArtistLookup:
    result: LastFmArtistLookupResult
    fetched_at: datetime
    expires_at: datetime


class LastFmCacheRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def get_album(
        self, artist_query: str, album_query: str, *, at: datetime | None = None
    ) -> CachedAlbumLookup | None:
        artist_key = self._query_key(artist_query)
        album_key = self._query_key(album_query)
        row = self.connection.execute(
            """
            SELECT artist_query, album_query, status, fetched_at, expires_at
            FROM lastfm_album_lookup
            WHERE artist_key = ? AND album_key = ?
            """,
            (artist_key, album_key),
        ).fetchone()
        if row is None:
            return None

        expires_at = self._datetime(row["expires_at"])
        if expires_at <= (at or datetime.now(timezone.utc)):
            return None

        tags = tuple(
            LastFmTag(name=tag["tag_name"], weight=tag["weight"], source="album")
            for tag in self.connection.execute(
                """
                SELECT tag_name, weight FROM lastfm_album_tag
                WHERE artist_key = ? AND album_key = ?
                ORDER BY position
                """,
                (artist_key, album_key),
            )
        )
        result = LastFmAlbumLookupResult(
            artist_query=row["artist_query"],
            album_query=row["album_query"],
            status=LastFmLookupStatus(row["status"]),
            tags=tags,
        )
        return CachedAlbumLookup(
            result=result,
            fetched_at=self._datetime(row["fetched_at"]),
            expires_at=expires_at,
        )

    def save_album(self, result: LastFmAlbumLookupResult, *, fetched_at: datetime, expires_at: datetime) -> None:
        artist_key = self._query_key(result.artist_query)
        album_key = self._query_key(result.album_query)
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO lastfm_album_lookup (
                    artist_key, album_key, artist_query, album_query, status, fetched_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (artist_key, album_key) DO UPDATE SET
                    artist_query = excluded.artist_query,
                    album_query = excluded.album_query,
                    status = excluded.status,
                    fetched_at = excluded.fetched_at,
                    expires_at = excluded.expires_at
                """,
                (
                    artist_key,
                    album_key,
                    result.artist_query,
                    result.album_query,
                    result.status.value,
                    self._timestamp(fetched_at),
                    self._timestamp(expires_at),
                ),
            )
            self.connection.execute(
                "DELETE FROM lastfm_album_tag WHERE artist_key = ? AND album_key = ?",
                (artist_key, album_key),
            )
            self.connection.executemany(
                """
                INSERT INTO lastfm_album_tag (artist_key, album_key, position, tag_name, weight)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (artist_key, album_key, position, tag.name, tag.weight)
                    for position, tag in enumerate(result.tags)
                ],
            )

    def get_artist(self, artist_query: str, *, at: datetime | None = None) -> CachedArtistLookup | None:
        artist_key = self._query_key(artist_query)
        row = self.connection.execute(
            """
            SELECT artist_query, status, resolved_name, url, mbid, listeners, playcount,
                   similar_artists, fetched_at, expires_at
            FROM lastfm_artist_lookup
            WHERE artist_key = ?
            """,
            (artist_key,),
        ).fetchone()
        if row is None:
            return None

        expires_at = self._datetime(row["expires_at"])
        if expires_at <= (at or datetime.now(timezone.utc)):
            return None

        status = LastFmLookupStatus(row["status"])
        candidate = None
        if status is LastFmLookupStatus.FOUND:
            tags = tuple(
                LastFmTag(name=tag["tag_name"], weight=tag["weight"], source="artist")
                for tag in self.connection.execute(
                    """
                    SELECT tag_name, weight FROM lastfm_artist_tag
                    WHERE artist_key = ?
                    ORDER BY position
                    """,
                    (artist_key,),
                )
            )
            candidate = ArtistCandidate(
                name=row["resolved_name"],
                url=row["url"],
                mbid=row["mbid"],
                listeners=row["listeners"],
                playcount=row["playcount"],
                tags=tags,
                similar_artists=tuple(json.loads(row["similar_artists"])),
            )
        result = LastFmArtistLookupResult(
            artist_query=row["artist_query"],
            status=status,
            candidate=candidate,
        )
        return CachedArtistLookup(
            result=result,
            fetched_at=self._datetime(row["fetched_at"]),
            expires_at=expires_at,
        )

    def save_artist(self, result: LastFmArtistLookupResult, *, fetched_at: datetime, expires_at: datetime) -> None:
        artist_key = self._query_key(result.artist_query)
        candidate = result.candidate
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO lastfm_artist_lookup (
                    artist_key, artist_query, status, resolved_name, url, mbid,
                    listeners, playcount, similar_artists, fetched_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (artist_key) DO UPDATE SET
                    artist_query = excluded.artist_query,
                    status = excluded.status,
                    resolved_name = excluded.resolved_name,
                    url = excluded.url,
                    mbid = excluded.mbid,
                    listeners = excluded.listeners,
                    playcount = excluded.playcount,
                    similar_artists = excluded.similar_artists,
                    fetched_at = excluded.fetched_at,
                    expires_at = excluded.expires_at
                """,
                (
                    artist_key,
                    result.artist_query,
                    result.status.value,
                    candidate.name if candidate is not None else None,
                    candidate.url if candidate is not None else None,
                    candidate.mbid if candidate is not None else None,
                    candidate.listeners if candidate is not None else None,
                    candidate.playcount if candidate is not None else None,
                    json.dumps(candidate.similar_artists if candidate is not None else ()),
                    self._timestamp(fetched_at),
                    self._timestamp(expires_at),
                ),
            )
            self.connection.execute("DELETE FROM lastfm_artist_tag WHERE artist_key = ?", (artist_key,))
            self.connection.executemany(
                """
                INSERT INTO lastfm_artist_tag (artist_key, position, tag_name, weight)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (artist_key, position, tag.name, tag.weight)
                    for position, tag in enumerate(candidate.tags if candidate is not None else ())
                ],
            )

    @staticmethod
    def _query_key(value: str) -> str:
        return " ".join(value.casefold().split())

    @staticmethod
    def _timestamp(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _datetime(value: str) -> datetime:
        return datetime.fromisoformat(value)


class DecisionRepository:
    def save(self, decision: Decision) -> None:
        raise NotImplementedError


__all__ = [
    "CachedAlbumLookup",
    "CachedArtistLookup",
    "DecisionRepository",
    "LastFmCacheRepository",
]
