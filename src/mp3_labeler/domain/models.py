from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class DecisionAction(str, Enum):
    MOVE = "move"
    REVIEW = "review"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class AlbumFolder:
    path: Path
    audio_files: tuple[Path, ...]
    discovered_at: datetime


@dataclass(frozen=True, slots=True)
class TrackMetadata:
    path: Path
    title: str | None = None
    artist: str | None = None
    album_artist: str | None = None
    album: str | None = None
    track_number: int | None = None
    disc_number: int | None = None
    year: int | None = None
    duration_seconds: float | None = None
    existing_genre: str | None = None


@dataclass(frozen=True, slots=True)
class AlbumMetadata:
    artist: str | None
    album: str | None
    album_artist: str | None
    year: int | None
    tracks: tuple[TrackMetadata, ...]
    confidence: float
    source: str


@dataclass(frozen=True, slots=True)
class LastFmTag:
    name: str
    weight: float
    source: str


@dataclass(frozen=True, slots=True)
class ArtistCandidate:
    name: str
    url: str | None = None
    mbid: str | None = None
    listeners: int | None = None
    playcount: int | None = None
    tags: tuple[LastFmTag, ...] = ()
    similar_artists: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class ExistingGenreEvidence:
    raw_values: tuple[str, ...]
    normalized_values: tuple[str, ...]
    matched_taxonomy_node_ids: tuple[str, ...]
    consistency_ratio: float
    source_tracks_count: int


@dataclass(frozen=True, slots=True)
class ManualOverride:
    match_type: str
    taxonomy_node_id: str
    artist: str | None = None
    album: str | None = None
    folder_hash: str | None = None
    metadata_corrections: dict[str, str] = field(default_factory=dict)
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class Decision:
    album_folder: AlbumFolder
    action: DecisionAction
    reason: str
    destination_path: Path | None = None
    dry_run: bool = True
    created_at: datetime | None = None
