from __future__ import annotations

from pathlib import Path

import pytest

from mp3_labeler.domain.models import TrackMetadata
from mp3_labeler.domain.taxonomy import Taxonomy, TaxonomyNode
from mp3_labeler.services.album_metadata_builder import AlbumMetadataBuilder


def track(
    filename: str,
    *,
    artist: str | None = None,
    album_artist: str | None = None,
    album: str | None = None,
    year: int | None = None,
    genre: str | None = None,
) -> TrackMetadata:
    return TrackMetadata(
        path=Path(filename),
        artist=artist,
        album_artist=album_artist,
        album=album,
        year=year,
        existing_genre=genre,
    )


def taxonomy() -> Taxonomy:
    return Taxonomy(
        nodes=(
            TaxonomyNode(id="death-metal", name="Death Metal", folder_path="Metal/Death Metal"),
            TaxonomyNode(id="black-metal", name="Black Metal", folder_path="Metal/Black Metal"),
            TaxonomyNode(
                id="symphonic-black-metal",
                name="Symphonic Black Metal",
                folder_path="Metal/Black Metal/Symphonic Black Metal",
                aliases=("Orchestral Black Metal",),
            ),
        )
    )


def test_build_derives_album_metadata_from_track_metadata() -> None:
    tracks = (
        track(
            "01.mp3",
            artist="Track Artist",
            album_artist="Album Artist",
            album="Album Title",
            year=2026,
            genre="Death Metal",
        ),
        track(
            "02.mp3",
            artist="Other Track Artist",
            album_artist="Album Artist",
            album="Album Title",
            year=2026,
            genre="Death Metal",
        ),
    )

    result = AlbumMetadataBuilder().build(tracks)

    assert result.album_metadata.artist == "Album Artist"
    assert result.album_metadata.album_artist == "Album Artist"
    assert result.album_metadata.album == "Album Title"
    assert result.album_metadata.year == 2026
    assert result.album_metadata.tracks == tracks
    assert result.album_metadata.source == "track_metadata"
    assert result.album_metadata.confidence == pytest.approx(1.0)


def test_build_falls_back_to_dominant_track_artist_when_album_artist_is_missing() -> None:
    tracks = (
        track("01.mp3", artist="Dominant Artist", album="Album"),
        track("02.mp3", artist="Dominant Artist", album="Album"),
        track("03.mp3", artist="Guest Artist", album="Album"),
    )

    result = AlbumMetadataBuilder().build(tracks)

    assert result.album_metadata.artist == "Dominant Artist"
    assert result.album_metadata.album_artist is None
    assert result.album_metadata.confidence == pytest.approx(5 / 6)


def test_build_raises_without_tracks() -> None:
    with pytest.raises(ValueError):
        AlbumMetadataBuilder().build(())


def test_derive_existing_genre_evidence_normalizes_deduplicates_and_maps_taxonomy_ids() -> None:
    tracks = (
        track("01.mp3", genre="Death Metal"),
        track("02.mp3", genre="death-metal"),
        track("03.mp3", genre="Death_Metal"),
    )

    evidence = AlbumMetadataBuilder().derive_existing_genre_evidence(tracks, taxonomy())

    assert evidence.raw_values == ("Death Metal", "death-metal", "Death_Metal")
    assert evidence.normalized_values == ("death metal",)
    assert evidence.matched_taxonomy_node_ids == ("death-metal",)
    assert evidence.consistency_ratio == pytest.approx(1.0)
    assert evidence.source_tracks_count == 3


def test_derive_existing_genre_evidence_splits_semicolon_separated_values() -> None:
    tracks = (
        track("01.mp3", genre="Black Metal; Symphonic Black Metal"),
        track("02.mp3", genre="Black Metal"),
    )

    evidence = AlbumMetadataBuilder().derive_existing_genre_evidence(tracks, taxonomy())

    assert evidence.raw_values == ("Black Metal", "Symphonic Black Metal")
    assert evidence.normalized_values == ("black metal", "symphonic black metal")
    assert evidence.matched_taxonomy_node_ids == ("black-metal", "symphonic-black-metal")
    assert evidence.consistency_ratio == pytest.approx(1.0)
    assert evidence.source_tracks_count == 2


def test_derive_existing_genre_evidence_matches_configured_aliases() -> None:
    tracks = (track("01.mp3", genre="orchestral-black-metal"),)

    evidence = AlbumMetadataBuilder().derive_existing_genre_evidence(tracks, taxonomy())

    assert evidence.normalized_values == ("orchestral black metal",)
    assert evidence.matched_taxonomy_node_ids == ("symphonic-black-metal",)


def test_derive_existing_genre_evidence_does_not_invent_taxonomy_ids() -> None:
    tracks = (track("01.mp3", genre="Atmospheric Death Doom"),)

    evidence = AlbumMetadataBuilder().derive_existing_genre_evidence(tracks, taxonomy())

    assert evidence.normalized_values == ("atmospheric death doom",)
    assert evidence.matched_taxonomy_node_ids == ()


def test_derive_existing_genre_evidence_requires_taxonomy_to_map_nodes() -> None:
    tracks = (track("01.mp3", genre="Death Metal"),)

    evidence = AlbumMetadataBuilder().derive_existing_genre_evidence(tracks)

    assert evidence.normalized_values == ("death metal",)
    assert evidence.matched_taxonomy_node_ids == ()


def test_derive_existing_genre_evidence_reports_partial_consistency() -> None:
    tracks = (
        track("01.mp3", genre="Death Metal"),
        track("02.mp3", genre="Death Metal"),
        track("03.mp3", genre="Black Metal"),
        track("04.mp3"),
    )

    evidence = AlbumMetadataBuilder().derive_existing_genre_evidence(tracks, taxonomy())

    assert evidence.normalized_values == ("death metal", "black metal")
    assert evidence.consistency_ratio == pytest.approx(2 / 3)
    assert evidence.source_tracks_count == 3


def test_derive_existing_genre_evidence_is_empty_when_no_tracks_have_genre_tags() -> None:
    evidence = AlbumMetadataBuilder().derive_existing_genre_evidence((track("01.mp3"), track("02.mp3")))

    assert evidence.raw_values == ()
    assert evidence.normalized_values == ()
    assert evidence.matched_taxonomy_node_ids == ()
    assert evidence.consistency_ratio == 0.0
    assert evidence.source_tracks_count == 0
