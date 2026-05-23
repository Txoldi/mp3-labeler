from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime
from pathlib import Path

import pytest

from mp3_labeler.domain.models import (
    AlbumFolder,
    AlbumMetadata,
    ArtistCandidate,
    Decision,
    DecisionAction,
    ExistingGenreEvidence,
    LastFmTag,
    ManualOverride,
    TrackMetadata,
)
from mp3_labeler.domain.scoring import ClassificationResult, ScoreEvidence, TaxonomyScore
from mp3_labeler.domain.taxonomy import Taxonomy, TaxonomyNode


def test_track_metadata_defaults_to_unknown_optional_values() -> None:
    track = TrackMetadata(path=Path("album/01-song.mp3"))

    assert track.path == Path("album/01-song.mp3")
    assert track.title is None
    assert track.artist is None
    assert track.album_artist is None
    assert track.album is None
    assert track.track_number is None
    assert track.disc_number is None
    assert track.year is None
    assert track.duration_seconds is None
    assert track.existing_genre is None


def test_album_metadata_groups_track_metadata_with_source_confidence() -> None:
    track = TrackMetadata(
        path=Path("album/01.mp3"),
        title="Song",
        artist="Artist",
        album_artist="Artist",
        album="Album",
        existing_genre="Death Metal",
    )

    album = AlbumMetadata(
        artist="Artist",
        album="Album",
        album_artist="Artist",
        year=1993,
        tracks=(track,),
        confidence=0.95,
        source="id3",
    )

    assert album.tracks == (track,)
    assert album.confidence == pytest.approx(0.95)
    assert album.source == "id3"


def test_album_folder_records_audio_files_and_discovery_time() -> None:
    discovered_at = datetime(2026, 5, 23, 12, 0, 0)
    folder = AlbumFolder(
        path=Path("inbox/Artist - Album"),
        audio_files=(Path("inbox/Artist - Album/01.mp3"),),
        discovered_at=discovered_at,
    )

    assert folder.path == Path("inbox/Artist - Album")
    assert folder.audio_files == (Path("inbox/Artist - Album/01.mp3"),)
    assert folder.discovered_at == discovered_at


def test_artist_candidate_defaults_to_no_optional_lastfm_data() -> None:
    candidate = ArtistCandidate(name="Ambiguous Name")

    assert candidate.name == "Ambiguous Name"
    assert candidate.url is None
    assert candidate.mbid is None
    assert candidate.listeners is None
    assert candidate.playcount is None
    assert candidate.tags == ()
    assert candidate.similar_artists == ()
    assert candidate.confidence == 0.0


def test_artist_candidate_can_hold_lastfm_evidence() -> None:
    tag = LastFmTag(name="black metal", weight=100.0, source="artist")
    candidate = ArtistCandidate(
        name="Artist",
        url="https://last.fm/music/Artist",
        mbid="example-mbid",
        listeners=1000,
        playcount=5000,
        tags=(tag,),
        similar_artists=("Similar Artist",),
        confidence=0.91,
    )

    assert candidate.tags == (tag,)
    assert candidate.similar_artists == ("Similar Artist",)
    assert candidate.confidence == pytest.approx(0.91)


def test_existing_genre_evidence_preserves_normalized_matches_and_consistency() -> None:
    evidence = ExistingGenreEvidence(
        raw_values=("Death Metal", "death metal"),
        normalized_values=("death metal",),
        matched_taxonomy_node_ids=("death-metal",),
        consistency_ratio=1.0,
        source_tracks_count=2,
    )

    assert evidence.normalized_values == ("death metal",)
    assert evidence.matched_taxonomy_node_ids == ("death-metal",)
    assert evidence.consistency_ratio == pytest.approx(1.0)
    assert evidence.source_tracks_count == 2


def test_manual_override_uses_independent_metadata_correction_dicts() -> None:
    first = ManualOverride(match_type="artist_album", taxonomy_node_id="death-metal")
    second = ManualOverride(match_type="artist_album", taxonomy_node_id="black-metal")

    first.metadata_corrections["album"] = "Corrected Album"

    assert first.metadata_corrections == {"album": "Corrected Album"}
    assert second.metadata_corrections == {}


def test_decision_defaults_to_dry_run_without_destination() -> None:
    folder = AlbumFolder(
        path=Path("inbox/Album"),
        audio_files=(Path("inbox/Album/01.mp3"),),
        discovered_at=datetime(2026, 5, 23, 12, 0, 0),
    )

    decision = Decision(album_folder=folder, action=DecisionAction.REVIEW, reason="ambiguous artist")

    assert decision.album_folder == folder
    assert decision.action is DecisionAction.REVIEW
    assert decision.reason == "ambiguous artist"
    assert decision.destination_path is None
    assert decision.dry_run is True
    assert decision.created_at is None


def test_frozen_models_prevent_attribute_reassignment() -> None:
    tag = LastFmTag(name="metalcore", weight=80.0, source="album")

    with pytest.raises(FrozenInstanceError):
        tag.weight = 50.0  # type: ignore[misc]


def test_taxonomy_node_defaults_are_conservative() -> None:
    node = TaxonomyNode(id="black-metal", name="Black Metal", folder_path="Metal/Black Metal")

    assert node.parent_id is None
    assert node.aliases == ()
    assert node.positive_tags == ()
    assert node.negative_tags == ()
    assert node.required_tags == ()
    assert node.broad_tags == ()
    assert node.priority == 0
    assert node.auto_accept_threshold == pytest.approx(0.9)


def test_taxonomy_builds_lookup_by_node_id() -> None:
    metal = TaxonomyNode(id="metal", name="Metal", folder_path="Metal")
    black_metal = TaxonomyNode(
        id="black-metal",
        name="Black Metal",
        parent_id="metal",
        folder_path="Metal/Black Metal",
    )

    taxonomy = Taxonomy(nodes=(metal, black_metal))

    assert taxonomy.by_id() == {
        "metal": metal,
        "black-metal": black_metal,
    }


def test_taxonomy_scoring_models_capture_evidence_conflicts_and_review_state() -> None:
    evidence = ScoreEvidence(source="lastfm_album", description="matched death metal", weight=1.0)
    winner = TaxonomyScore(
        taxonomy_node_id="death-metal",
        score=0.94,
        confidence=0.92,
        evidence=(evidence,),
        conflicts=("local genre mismatch",),
    )
    result = ClassificationResult(
        winner=winner,
        alternatives=(),
        requires_review=True,
        reason="conflicting local and remote evidence",
    )

    assert result.winner == winner
    assert result.winner.evidence == (evidence,)
    assert result.winner.conflicts == ("local genre mismatch",)
    assert result.alternatives == ()
    assert result.requires_review is True
    assert result.reason == "conflicting local and remote evidence"
