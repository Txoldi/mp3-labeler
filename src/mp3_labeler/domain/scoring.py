from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ScoreEvidence:
    source: str
    description: str
    weight: float


@dataclass(frozen=True, slots=True)
class TaxonomyScore:
    taxonomy_node_id: str
    score: float
    confidence: float
    evidence: tuple[ScoreEvidence, ...] = ()
    conflicts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    winner: TaxonomyScore | None
    alternatives: tuple[TaxonomyScore, ...]
    requires_review: bool
    reason: str


class ReviewStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    OVERRIDDEN = "overridden"
    DISMISSED = "dismissed"


@dataclass(frozen=True, slots=True)
class ReviewItem:
    id: int | None
    album_path: Path
    artist: str | None
    album: str | None
    year: int | None
    existing_genres: tuple[str, ...]
    matched_taxonomy_node_ids: tuple[str, ...]
    proposed_node_id: str | None
    score: float | None
    confidence: float | None
    reason: str
    conflicts: tuple[str, ...] = ()
    evidence: tuple[ScoreEvidence, ...] = ()
    status: ReviewStatus = ReviewStatus.PENDING
    created_at: datetime | None = None
    updated_at: datetime | None = None
