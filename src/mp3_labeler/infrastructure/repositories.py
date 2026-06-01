from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from sqlite3 import Connection

from mp3_labeler.domain.models import (
    AppliedAlbumDecision,
    ArtistCandidate,
    LastFmAlbumLookupResult,
    LastFmArtistLookupResult,
    LastFmLookupStatus,
    LastFmTag,
    ManualOverride,
)
from mp3_labeler.domain.scoring import ReviewItem, ReviewStatus, ScoreEvidence


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


class ReviewRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def save_pending(self, item: ReviewItem, *, at: datetime) -> ReviewItem:
        timestamp = self._timestamp(at)
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO review_item (
                    album_path, artist, album, year, existing_genres, matched_taxonomy_node_ids,
                    proposed_node_id, score, confidence, reason, conflicts, evidence,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                ON CONFLICT (album_path) DO UPDATE SET
                    artist = excluded.artist,
                    album = excluded.album,
                    year = excluded.year,
                    existing_genres = excluded.existing_genres,
                    matched_taxonomy_node_ids = excluded.matched_taxonomy_node_ids,
                    proposed_node_id = excluded.proposed_node_id,
                    score = excluded.score,
                    confidence = excluded.confidence,
                    reason = excluded.reason,
                    conflicts = excluded.conflicts,
                    evidence = excluded.evidence,
                    status = 'pending',
                    updated_at = excluded.updated_at
                """,
                (
                    str(item.album_path),
                    item.artist,
                    item.album,
                    item.year,
                    json.dumps(item.existing_genres),
                    json.dumps(item.matched_taxonomy_node_ids),
                    item.proposed_node_id,
                    item.score,
                    item.confidence,
                    item.reason,
                    json.dumps(item.conflicts),
                    json.dumps(
                        [
                            {"source": evidence.source, "description": evidence.description, "weight": evidence.weight}
                            for evidence in item.evidence
                        ]
                    ),
                    timestamp,
                    timestamp,
                ),
            )
        return self.get_by_path(item.album_path)

    def list(self, status: ReviewStatus | None = ReviewStatus.PENDING) -> tuple[ReviewItem, ...]:
        if status is None:
            rows = self.connection.execute("SELECT * FROM review_item ORDER BY updated_at DESC, id DESC").fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM review_item WHERE status = ? ORDER BY updated_at DESC, id DESC",
                (status.value,),
            ).fetchall()
        return tuple(self._item(row) for row in rows)

    def get(self, item_id: int) -> ReviewItem | None:
        row = self.connection.execute("SELECT * FROM review_item WHERE id = ?", (item_id,)).fetchone()
        return None if row is None else self._item(row)

    def get_by_path(self, album_path: Path) -> ReviewItem:
        row = self.connection.execute("SELECT * FROM review_item WHERE album_path = ?", (str(album_path),)).fetchone()
        if row is None:
            raise LookupError(f"No review item exists for '{album_path}'")
        return self._item(row)

    def set_status(self, item_id: int, status: ReviewStatus, *, at: datetime) -> ReviewItem:
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE review_item SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, self._timestamp(at), item_id),
            )
        if cursor.rowcount == 0:
            raise LookupError(f"Review item {item_id} does not exist")
        item = self.get(item_id)
        assert item is not None
        return item

    def delete(self, item_id: int) -> None:
        with self.connection:
            cursor = self.connection.execute("DELETE FROM review_item WHERE id = ?", (item_id,))
        if cursor.rowcount == 0:
            raise LookupError(f"Review item {item_id} does not exist")

    @staticmethod
    def _item(row) -> ReviewItem:
        return ReviewItem(
            id=row["id"],
            album_path=Path(row["album_path"]),
            artist=row["artist"],
            album=row["album"],
            year=row["year"],
            existing_genres=tuple(json.loads(row["existing_genres"])),
            matched_taxonomy_node_ids=tuple(json.loads(row["matched_taxonomy_node_ids"])),
            proposed_node_id=row["proposed_node_id"],
            score=row["score"],
            confidence=row["confidence"],
            reason=row["reason"],
            conflicts=tuple(json.loads(row["conflicts"])),
            evidence=tuple(ScoreEvidence(**value) for value in json.loads(row["evidence"])),
            status=ReviewStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _timestamp(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()


class ManualOverrideRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def list(self) -> tuple[ManualOverride, ...]:
        rows = self.connection.execute(
            "SELECT * FROM manual_override ORDER BY updated_at DESC, id DESC"
        ).fetchall()
        return tuple(
            ManualOverride(
                match_type=row["match_type"],
                artist=row["artist"],
                album=row["album"],
                folder_hash=row["folder_hash"],
                taxonomy_node_id=row["taxonomy_node_id"],
                metadata_corrections=dict(json.loads(row["metadata_corrections"])),
                notes=row["notes"],
            )
            for row in rows
        )

    def save(self, override: ManualOverride, *, at: datetime) -> None:
        timestamp = at.astimezone(timezone.utc).isoformat()
        where_clause, values = self._identity(override)
        existing = self.connection.execute(
            f"SELECT id, created_at FROM manual_override WHERE {where_clause}",
            values,
        ).fetchone()
        with self.connection:
            if existing is None:
                self.connection.execute(
                    """
                    INSERT INTO manual_override (
                        match_type, artist, album, folder_hash, taxonomy_node_id,
                        metadata_corrections, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        override.match_type,
                        override.artist,
                        override.album,
                        override.folder_hash,
                        override.taxonomy_node_id,
                        json.dumps(override.metadata_corrections),
                        override.notes,
                        timestamp,
                        timestamp,
                    ),
                )
            else:
                self.connection.execute(
                    """
                    UPDATE manual_override
                    SET taxonomy_node_id = ?, metadata_corrections = ?, notes = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        override.taxonomy_node_id,
                        json.dumps(override.metadata_corrections),
                        override.notes,
                        timestamp,
                        existing["id"],
                    ),
                )

    @staticmethod
    def _identity(override: ManualOverride) -> tuple[str, tuple[str, ...]]:
        if override.match_type == "artist_album":
            return (
                "match_type = 'artist_album' AND lower(trim(artist)) = lower(trim(?)) "
                "AND lower(trim(album)) = lower(trim(?))",
                (override.artist or "", override.album or ""),
            )
        if override.match_type == "artist":
            return ("match_type = 'artist' AND lower(trim(artist)) = lower(trim(?))", (override.artist or "",))
        return (
            "match_type = 'folder_hash' AND lower(trim(folder_hash)) = lower(trim(?))",
            (override.folder_hash or "",),
        )


class DecisionRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def save_applied(self, decision: AppliedAlbumDecision) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO applied_album_decision (
                    source_path, destination_path, artist, album, taxonomy_node_id,
                    genres_written, decision_source, applied_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(decision.source_path),
                    str(decision.destination_path),
                    decision.artist,
                    decision.album,
                    decision.taxonomy_node_id,
                    json.dumps(decision.genres_written),
                    decision.decision_source,
                    decision.applied_at.astimezone(timezone.utc).isoformat(),
                ),
            )

    def list_applied(self) -> tuple[AppliedAlbumDecision, ...]:
        rows = self.connection.execute(
            "SELECT * FROM applied_album_decision ORDER BY applied_at, id"
        ).fetchall()
        return tuple(
            AppliedAlbumDecision(
                source_path=Path(row["source_path"]),
                destination_path=Path(row["destination_path"]),
                artist=row["artist"],
                album=row["album"],
                taxonomy_node_id=row["taxonomy_node_id"],
                genres_written=tuple(json.loads(row["genres_written"])),
                decision_source=row["decision_source"],
                applied_at=datetime.fromisoformat(row["applied_at"]),
            )
            for row in rows
        )


__all__ = [
    "CachedAlbumLookup",
    "CachedArtistLookup",
    "DecisionRepository",
    "LastFmCacheRepository",
    "ManualOverrideRepository",
    "ReviewRepository",
]
