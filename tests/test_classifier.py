from __future__ import annotations

from mp3_labeler.config.settings import Settings
from mp3_labeler.domain.models import AlbumMetadata, ExistingGenreEvidence, LastFmTag
from mp3_labeler.domain.taxonomy import Taxonomy, TaxonomyNode
from mp3_labeler.services.classifier import AlbumClassifier


def taxonomy() -> Taxonomy:
    return Taxonomy(
        nodes=(
            TaxonomyNode(
                id="metal",
                name="Metal",
                folder_path="Metal",
                positive_tags=("metal",),
                broad_tags=("metal",),
                auto_accept_threshold=0.85,
            ),
            TaxonomyNode(
                id="death-metal",
                name="Death Metal",
                parent_id="metal",
                folder_path="Metal/Death Metal",
                positive_tags=("death metal",),
                negative_tags=("metalcore",),
                required_tags=("death metal",),
            ),
            TaxonomyNode(
                id="melodic-death-metal",
                name="Melodic Death Metal",
                parent_id="death-metal",
                folder_path="Metal/Death Metal/Melodic Death Metal",
                positive_tags=("melodic death metal",),
                required_tags=("death metal",),
            ),
            TaxonomyNode(
                id="black-metal",
                name="Black Metal",
                parent_id="metal",
                folder_path="Metal/Black Metal",
                positive_tags=("black metal",),
                required_tags=("black metal",),
            ),
        )
    )


def metadata(confidence: float = 1.0) -> AlbumMetadata:
    return AlbumMetadata(
        artist="Artist",
        album="Album",
        album_artist="Artist",
        year=None,
        tracks=(),
        confidence=confidence,
        source="track_metadata",
    )


def existing_genre(node_id: str, consistency: float = 1.0) -> ExistingGenreEvidence:
    return ExistingGenreEvidence(
        raw_values=(node_id,),
        normalized_values=(node_id,),
        matched_taxonomy_node_ids=(node_id,),
        consistency_ratio=consistency,
        source_tracks_count=3,
    )


def test_classify_accepts_specific_album_tag_with_confident_local_identity() -> None:
    result = AlbumClassifier().classify(
        metadata(),
        (LastFmTag("death metal", 100, "album"),),
        taxonomy(),
    )

    assert result.winner is not None
    assert result.winner.taxonomy_node_id == "death-metal"
    assert result.winner.confidence == 1.0
    assert result.requires_review is False
    assert result.winner.evidence[0].source == "lastfm_album"


def test_classify_does_not_accept_artist_tag_alone_as_automatic_evidence() -> None:
    result = AlbumClassifier().classify(
        metadata(),
        (LastFmTag("death metal", 100, "artist"),),
        taxonomy(),
    )

    assert result.winner is not None
    assert result.winner.taxonomy_node_id == "death-metal"
    assert result.requires_review is True
    assert "below" in result.reason


def test_classify_does_not_accept_broad_parent_tag_alone() -> None:
    result = AlbumClassifier().classify(metadata(), (LastFmTag("metal", 100, "album"),), taxonomy())

    assert result.winner is not None
    assert result.winner.taxonomy_node_id == "metal"
    assert result.winner.confidence == 0.0
    assert result.requires_review is True
    assert "top-level" in result.reason


def test_classify_reviews_top_level_node_even_with_reliable_local_genre() -> None:
    result = AlbumClassifier().classify(metadata(), (), taxonomy(), existing_genre("metal"))

    assert result.winner is not None
    assert result.winner.taxonomy_node_id == "metal"
    assert result.winner.confidence == 1.0
    assert result.requires_review is True
    assert "top-level" in result.reason


def test_classify_chooses_deeper_subgenre_when_required_parent_evidence_exists() -> None:
    result = AlbumClassifier().classify(
        metadata(),
        (
            LastFmTag("death metal", 100, "album"),
            LastFmTag("melodic death metal", 100, "album"),
        ),
        taxonomy(),
    )

    assert result.winner is not None
    assert result.winner.taxonomy_node_id == "melodic-death-metal"
    assert result.requires_review is False


def test_classify_reviews_deep_subgenre_when_required_evidence_is_missing() -> None:
    result = AlbumClassifier().classify(
        metadata(),
        (LastFmTag("melodic death metal", 100, "album"),),
        taxonomy(),
    )

    assert result.winner is not None
    assert result.winner.taxonomy_node_id == "melodic-death-metal"
    assert result.requires_review is True
    assert "Required evidence missing" in result.reason


def test_classify_uses_consistent_existing_genre_as_strong_evidence() -> None:
    result = AlbumClassifier().classify(metadata(), (), taxonomy(), existing_genre("death-metal"))

    assert result.winner is not None
    assert result.winner.taxonomy_node_id == "death-metal"
    assert result.requires_review is False
    assert result.winner.evidence[0].source == "existing_genre"


def test_classify_treats_reliable_specific_local_genre_as_support_for_its_parent_path() -> None:
    result = AlbumClassifier().classify(
        metadata(),
        (),
        taxonomy(),
        existing_genre("melodic-death-metal"),
    )

    assert result.winner is not None
    assert result.winner.taxonomy_node_id == "melodic-death-metal"
    assert result.requires_review is False


def test_classify_reviews_remote_proposal_that_conflicts_with_reliable_local_genre() -> None:
    result = AlbumClassifier().classify(
        metadata(),
        (LastFmTag("black metal", 100, "album"),),
        taxonomy(),
        existing_genre("death-metal"),
    )

    assert result.winner is not None
    assert result.requires_review is True
    assert any("conflicts with existing MP3 genre" in conflict for conflict in result.winner.conflicts)


def test_classify_ignores_unreliable_local_genre_for_conflict_gate() -> None:
    result = AlbumClassifier().classify(
        metadata(),
        (LastFmTag("black metal", 100, "album"),),
        taxonomy(),
        existing_genre("death-metal", consistency=0.5),
    )

    assert result.winner is not None
    assert result.winner.taxonomy_node_id == "black-metal"
    assert result.requires_review is False


def test_classify_reviews_close_incompatible_candidates() -> None:
    result = AlbumClassifier().classify(
        metadata(),
        (
            LastFmTag("death metal", 100, "album"),
            LastFmTag("black metal", 95, "album"),
        ),
        taxonomy(),
    )

    assert result.winner is not None
    assert result.requires_review is True
    assert "too close" in result.reason


def test_classify_reviews_when_local_album_identity_is_weak() -> None:
    result = AlbumClassifier().classify(
        metadata(confidence=0.5),
        (LastFmTag("death metal", 100, "album"),),
        taxonomy(),
    )

    assert result.winner is not None
    assert result.requires_review is True
    assert "identity" in result.reason


def test_classify_supports_configurable_acceptance_threshold() -> None:
    settings = Settings(taxonomy_confidence_threshold=0.5)
    result = AlbumClassifier(settings=settings).classify(
        metadata(),
        (LastFmTag("death metal", 60, "album"),),
        taxonomy(),
    )

    assert result.winner is not None
    assert result.requires_review is True  # The taxonomy node's stricter 0.9 threshold remains authoritative.
