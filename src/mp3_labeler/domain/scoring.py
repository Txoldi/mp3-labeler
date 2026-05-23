from __future__ import annotations

from dataclasses import dataclass


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

