from __future__ import annotations

from pathlib import Path

import pytest

from mp3_labeler.domain.models import AlbumMetadata, ManualOverride
from mp3_labeler.domain.taxonomy import Taxonomy, TaxonomyNode
from mp3_labeler.config.taxonomy_loader import TaxonomyLoader
from mp3_labeler.services.override_service import OverrideService, OverrideValidationError


def taxonomy() -> Taxonomy:
    return Taxonomy(
        nodes=(
            TaxonomyNode(id="metal", name="Metal", folder_path="Metal"),
            TaxonomyNode(id="death-metal", name="Death Metal", folder_path="Metal/Death Metal", parent_id="metal"),
            TaxonomyNode(id="hardcore", name="Hardcore", folder_path="Hardcore"),
        )
    )


def metadata(
    *,
    artist: str | None = "Artist",
    album_artist: str | None = None,
    album: str | None = "Album",
) -> AlbumMetadata:
    return AlbumMetadata(
        artist=artist,
        album=album,
        album_artist=album_artist,
        year=None,
        tracks=(),
        confidence=1.0,
        source="track_metadata",
    )


def write_overrides(tmp_path: Path, contents: str) -> Path:
    path = tmp_path / "overrides.toml"
    path.write_text(contents, encoding="utf-8")
    return path


def test_load_and_find_artist_album_override_using_normalized_metadata(tmp_path) -> None:
    path = write_overrides(
        tmp_path,
        """
[[overrides]]
match_type = "artist_album"
artist = "Class Traitor"
album = "The Images Aren't Mine"
taxonomy_node_id = "hardcore"
notes = "Manually verified."

[overrides.metadata_corrections]
genre = "Hardcore"
""",
    )

    service = OverrideService.load(path, taxonomy())
    override = service.find_override(metadata(album_artist="  CLASS  TRAITOR ", album="the images aren't mine"))

    assert override is not None
    assert override.taxonomy_node_id == "hardcore"
    assert override.notes == "Manually verified."
    assert override.metadata_corrections == {"genre": "Hardcore"}


def test_artist_album_override_has_precedence_over_artist_wide_override() -> None:
    service = OverrideService(
        (
            ManualOverride(match_type="artist", artist="Artist", taxonomy_node_id="hardcore"),
            ManualOverride(
                match_type="artist_album",
                artist="Artist",
                album="Special Album",
                taxonomy_node_id="death-metal",
            ),
        ),
        taxonomy(),
    )

    override = service.find_override(metadata(album="Special Album"))

    assert override is not None
    assert override.taxonomy_node_id == "death-metal"


def test_folder_hash_override_matches_when_hash_is_supplied() -> None:
    service = OverrideService(
        (ManualOverride(match_type="folder_hash", folder_hash="ABCD1234", taxonomy_node_id="death-metal"),),
        taxonomy(),
    )

    assert service.find_override(metadata(artist=None, album=None), folder_hash="abcd1234") is not None
    assert service.find_override(metadata(artist=None, album=None)) is None


def test_find_override_prefers_album_artist_over_track_artist() -> None:
    service = OverrideService(
        (ManualOverride(match_type="artist", artist="Album Artist", taxonomy_node_id="hardcore"),),
        taxonomy(),
    )

    override = service.find_override(metadata(artist="Guest Artist", album_artist="Album Artist"))

    assert override is not None


def test_load_empty_configuration_has_no_matches(tmp_path) -> None:
    service = OverrideService.load(write_overrides(tmp_path, ""), taxonomy())

    assert service.find_override(metadata()) is None


def test_load_accepts_example_overrides_configuration() -> None:
    project_root = Path(__file__).parent.parent
    configured_taxonomy = TaxonomyLoader().load(project_root / "config" / "taxonomy.example.toml")

    service = OverrideService.load(project_root / "config" / "overrides.example.toml", configured_taxonomy)

    assert service.find_override(metadata(artist="Example Artist", album="Example Album")) is not None


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        (
            '[[overrides]]\nmatch_type = "unknown"\ntaxonomy_node_id = "death-metal"\n',
            "match_type",
        ),
        (
            '[[overrides]]\nmatch_type = "artist_album"\nartist = "Artist"\n'
            'taxonomy_node_id = "death-metal"\n',
            "requires artist and album",
        ),
        (
            '[[overrides]]\nmatch_type = "artist"\nartist = "Artist"\n'
            'taxonomy_node_id = "does-not-exist"\n',
            "unknown taxonomy_node_id",
        ),
        (
            '[[overrides]]\nmatch_type = "artist"\nartist = "Artist"\n'
            'taxonomy_node_id = "hardcore"\nmetadata_corrections = "not a table"\n',
            "metadata_corrections",
        ),
    ],
)
def test_load_rejects_invalid_overrides(tmp_path, contents: str, message: str) -> None:
    with pytest.raises(OverrideValidationError, match=message):
        OverrideService.load(write_overrides(tmp_path, contents), taxonomy())


def test_service_rejects_duplicate_normalized_matches() -> None:
    with pytest.raises(OverrideValidationError, match="Duplicate"):
        OverrideService(
            (
                ManualOverride(match_type="artist", artist="Class Traitor", taxonomy_node_id="hardcore"),
                ManualOverride(match_type="artist", artist=" class  traitor ", taxonomy_node_id="death-metal"),
            ),
            taxonomy(),
        )


def test_service_rejects_invalid_programmatic_override() -> None:
    with pytest.raises(OverrideValidationError, match="requires artist"):
        OverrideService((ManualOverride(match_type="artist", taxonomy_node_id="hardcore"),), taxonomy())


def test_load_raises_for_missing_file_and_directory_path(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        OverrideService.load(tmp_path / "missing.toml", taxonomy())
    with pytest.raises(IsADirectoryError):
        OverrideService.load(tmp_path, taxonomy())
