from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    dry_run: bool = True
    genre_depth: int = 1
    identity_confidence_threshold: float = 0.9
    taxonomy_confidence_threshold: float = 0.9
    winner_margin_threshold: float = 0.15
    existing_genre_consistency_threshold: float = 0.7

