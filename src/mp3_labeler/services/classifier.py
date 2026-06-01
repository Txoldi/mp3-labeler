from __future__ import annotations

from dataclasses import dataclass

from mp3_labeler.config.settings import Settings
from mp3_labeler.domain.models import AlbumMetadata, ExistingGenreEvidence, LastFmTag
from mp3_labeler.domain.scoring import ClassificationResult, ScoreEvidence, TaxonomyScore
from mp3_labeler.domain.taxonomy import Taxonomy, TaxonomyNode

# This class defines how trusted each source of evidence is by applying a multiplier to the weight of the evidence.
# Album tags are trusted more than artist tags, and track tags are trusted less than artist tags.
# Broad tags are such as "metal" are penalized, and local genres are trusted more than remote genres.
# Negative tags are heavily penalized to make sure not to include them.
# The local genre is trusted more than the remote genre.
# A deep node receives a small bonus when its required parent evidence is present.
@dataclass(frozen=True, slots=True)
class EvidenceWeights:
    album_tag: float = 1.0
    artist_tag: float = 0.6
    track_tag: float = 0.4
    local_genre: float = 1.05
    top_level_local_genre_multiplier: float = 0.1
    broad_tag_multiplier: float = 0.25
    negative_tag_penalty: float = 1.0
    supporting_required_tag_bonus: float = 0.2


class AlbumClassifier:
    def __init__(
        self,
        settings: Settings | None = None,
        weights: EvidenceWeights | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.weights = weights or EvidenceWeights()

    def classify(
        self,
        metadata: AlbumMetadata,
        tags: tuple[LastFmTag, ...],
        taxonomy: Taxonomy,
        existing_genre: ExistingGenreEvidence | None = None,
    ) -> ClassificationResult:
        if not taxonomy.nodes:
            return ClassificationResult(None, (), True, "Taxonomy is empty")

        scores = tuple(
            score
            for node in taxonomy.nodes
            if (score := self._score_node(node, tags, taxonomy, existing_genre)).score > 0
        )
        ordered_scores = tuple(sorted(scores, key=lambda score: self._sort_key(score, taxonomy), reverse=True))
        if not ordered_scores:
            return ClassificationResult(None, (), True, "No taxonomy node matched the available evidence")

        winner = self._first_specific_score(ordered_scores, taxonomy)
        if winner is None:
            return ClassificationResult(
                None,
                ordered_scores,
                True,
                "Only broad top-level taxonomy evidence matched; a more specific classification is required",
            )
        alternatives = tuple(score for score in ordered_scores if score.taxonomy_node_id != winner.taxonomy_node_id)
        node = taxonomy.by_id()[winner.taxonomy_node_id]

        if metadata.confidence < self.settings.identity_confidence_threshold:
            return ClassificationResult(
                winner,
                alternatives,
                True,
                "Local album identity confidence is below the automatic classification threshold",
            )
        if winner.conflicts:
            return ClassificationResult(winner, alternatives, True, winner.conflicts[0])
        if len(self._lineage(node.id, taxonomy)) == 1:
            return ClassificationResult(
                winner,
                alternatives,
                True,
                "Winning taxonomy node is a broad top-level category and requires a more specific classification",
            )
        if winner.confidence < max(self.settings.taxonomy_confidence_threshold, node.auto_accept_threshold):
            return ClassificationResult(
                winner,
                alternatives,
                True,
                "Winning taxonomy score is below the automatic classification threshold",
            )
        if alternatives and winner.score - alternatives[0].score < self.settings.winner_margin_threshold:
            return ClassificationResult(
                winner,
                alternatives,
                True,
                "Winning taxonomy node is too close to an alternative",
            )

        return ClassificationResult(winner, alternatives, False, "Classification meets automatic confidence gates")

    def _score_node(
        self,
        node: TaxonomyNode,
        tags: tuple[LastFmTag, ...],
        taxonomy: Taxonomy,
        existing_genre: ExistingGenreEvidence | None,
    ) -> TaxonomyScore:
        positive_labels = {
            Taxonomy.normalize_label(value)
            for value in (node.name, *node.aliases, *node.positive_tags)
        }
        negative_labels = {Taxonomy.normalize_label(value) for value in node.negative_tags}
        broad_labels = {Taxonomy.normalize_label(value) for value in node.broad_tags}
        evidence: list[ScoreEvidence] = []
        conflicts: list[str] = []
        score = 0.0
        specific_score = 0.0

        for tag in tags:
            normalized_tag = Taxonomy.normalize_label(tag.name)
            tag_strength = self._tag_strength(tag)
            if normalized_tag in positive_labels:
                multiplier = self.weights.broad_tag_multiplier if normalized_tag in broad_labels else 1.0
                contribution = tag_strength * multiplier
                score += contribution
                if normalized_tag not in broad_labels:
                    specific_score += contribution
                evidence.append(
                    ScoreEvidence(
                        source=f"lastfm_{tag.source}",
                        description=f"matched tag '{tag.name}'",
                        weight=contribution,
                    )
                )
            if normalized_tag in negative_labels:
                penalty = tag_strength * self.weights.negative_tag_penalty
                score -= penalty
                conflicts.append(f"Negative tag '{tag.name}' conflicts with '{node.name}'")
                evidence.append(
                    ScoreEvidence(
                        source=f"lastfm_{tag.source}",
                        description=f"negative tag '{tag.name}'",
                        weight=-penalty,
                    )
                )

        reliable_local_ids = self._reliable_local_ids(existing_genre)
        if node.id in reliable_local_ids and existing_genre is not None:
            contribution = self.weights.local_genre * existing_genre.consistency_ratio
            if self._is_top_level_node(node):
                contribution *= self.weights.top_level_local_genre_multiplier
            score += contribution
            if not self._is_top_level_node(node):
                specific_score += contribution
            evidence.append(
                ScoreEvidence(
                    source="existing_genre",
                    description=f"existing MP3 genre matches '{node.name}'",
                    weight=contribution,
                )
            )
            if self._has_strong_incompatible_remote_match(node.id, tags, taxonomy):
                conflicts.append(f"Strong Last.fm evidence conflicts with existing MP3 genre '{node.name}'")
        elif reliable_local_ids and not any(
            self._nodes_related(node.id, local_id, taxonomy) for local_id in reliable_local_ids
        ):
            conflicts.append(f"Existing MP3 genre conflicts with proposed node '{node.name}'")

        missing_required = self._missing_required_tags(node, tags, reliable_local_ids, taxonomy)
        if missing_required:
            conflicts.append(
                f"Required evidence missing for '{node.name}': {', '.join(missing_required)}"
            )
        elif specific_score > 0:
            supporting_required_tags = tuple(
                required
                for required in node.required_tags
                if Taxonomy.normalize_label(required) not in positive_labels
            )
            if supporting_required_tags:
                score += self.weights.supporting_required_tag_bonus
                evidence.append(
                    ScoreEvidence(
                        source="required_evidence",
                        description=f"supporting required tags present: {', '.join(supporting_required_tags)}",
                        weight=self.weights.supporting_required_tag_bonus,
                    )
                )

        score = max(0.0, score)
        confidence = min(1.0, specific_score)
        if missing_required or (specific_score == 0 and score > 0):
            confidence = 0.0

        return TaxonomyScore(
            taxonomy_node_id=node.id,
            score=score,
            confidence=confidence,
            evidence=tuple(evidence),
            conflicts=tuple(conflicts),
        )

    def _missing_required_tags(
        self,
        node: TaxonomyNode,
        tags: tuple[LastFmTag, ...],
        reliable_local_ids: tuple[str, ...],
        taxonomy: Taxonomy,
    ) -> tuple[str, ...]:
        observed_remote = {Taxonomy.normalize_label(tag.name) for tag in tags if tag.weight > 0}
        observed_local = {
            Taxonomy.normalize_label(taxonomy.by_id()[lineage_id].name)
            for node_id in reliable_local_ids
            for lineage_id in self._lineage(node_id, taxonomy)
            if lineage_id in taxonomy.by_id()
        }
        observed = observed_remote | observed_local
        return tuple(
            required
            for required in node.required_tags
            if Taxonomy.normalize_label(required) not in observed
        )

    def _tag_strength(self, tag: LastFmTag) -> float:
        source_weight = {
            "album": self.weights.album_tag,
            "artist": self.weights.artist_tag,
            "track": self.weights.track_tag,
        }.get(tag.source, self.weights.track_tag)
        normalized_weight = min(max(tag.weight, 0.0), 100.0) / 100.0
        return source_weight * normalized_weight

    def _reliable_local_ids(self, existing_genre: ExistingGenreEvidence | None) -> tuple[str, ...]:
        if (
            existing_genre is None
            or existing_genre.source_tracks_count == 0
            or existing_genre.consistency_ratio < self.settings.existing_genre_consistency_threshold
        ):
            return ()
        return existing_genre.matched_taxonomy_node_ids

    def _has_strong_incompatible_remote_match(
        self,
        local_node_id: str,
        tags: tuple[LastFmTag, ...],
        taxonomy: Taxonomy,
    ) -> bool:
        for tag in tags:
            if self._tag_strength(tag) < self.settings.taxonomy_confidence_threshold:
                continue
            for remote_node_id in taxonomy.match_genre_node_ids(tag.name):
                if not self._nodes_related(local_node_id, remote_node_id, taxonomy):
                    return True
        return False

    @staticmethod
    def _nodes_related(first_id: str, second_id: str, taxonomy: Taxonomy) -> bool:
        return first_id in AlbumClassifier._lineage(second_id, taxonomy) or second_id in AlbumClassifier._lineage(
            first_id, taxonomy
        )

    @staticmethod
    def _lineage(node_id: str, taxonomy: Taxonomy) -> tuple[str, ...]:
        by_id = taxonomy.by_id()
        lineage: list[str] = []
        current_id: str | None = node_id
        while current_id is not None and current_id in by_id:
            lineage.append(current_id)
            current_id = by_id[current_id].parent_id
        return tuple(lineage)

    @staticmethod
    def _sort_key(score: TaxonomyScore, taxonomy: Taxonomy) -> tuple[float, float, int, int]:
        node = taxonomy.by_id()[score.taxonomy_node_id]
        depth = len(AlbumClassifier._lineage(node.id, taxonomy))
        return (score.score, score.confidence, node.priority, depth)

    @staticmethod
    def _first_specific_score(scores: tuple[TaxonomyScore, ...], taxonomy: Taxonomy) -> TaxonomyScore | None:
        by_id = taxonomy.by_id()
        for score in scores:
            node = by_id[score.taxonomy_node_id]
            if not AlbumClassifier._is_top_level_node(node):
                return score
        return None

    @staticmethod
    def _is_top_level_node(node: TaxonomyNode) -> bool:
        return node.parent_id is None


__all__ = ["AlbumClassifier", "EvidenceWeights"]
