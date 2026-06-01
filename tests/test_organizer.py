from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from mp3_labeler.domain.models import AlbumFolder, ManualOverride
from mp3_labeler.domain.taxonomy import Taxonomy, TaxonomyNode
from mp3_labeler.services.organizer import AlbumOrganizer


def album_folder(path: Path) -> AlbumFolder:
    path.mkdir(parents=True)
    track = path / "01.mp3"
    track.write_bytes(b"track")
    return AlbumFolder(path, (track,), datetime(2026, 5, 27))


def taxonomy() -> Taxonomy:
    return Taxonomy(
        (
            TaxonomyNode("metal", "Metal", "Metal"),
            TaxonomyNode("black-metal", "Black Metal", "Metal/Black Metal", parent_id="metal"),
            TaxonomyNode(
                "melodic-black-metal",
                "Melodic Black Metal",
                "Metal/Black Metal/Melodic Black Metal",
                parent_id="black-metal",
            ),
        )
    )


def test_override_decision_targets_taxonomy_folder_and_preserves_album_directory_name(tmp_path) -> None:
    source = album_folder(tmp_path / "inbox" / "Artist - Album")
    organizer = AlbumOrganizer()

    decision = organizer.decision_for_override(
        source,
        ManualOverride("artist_album", "black-metal", artist="Artist", album="Album"),
        taxonomy(),
        tmp_path / "library",
    )

    assert decision.destination_path == tmp_path / "library" / "Metal" / "Black Metal" / "_Albums" / "Artist - Album"
    assert decision.dry_run is True


def test_leaf_taxonomy_node_targets_taxonomy_folder_directly(tmp_path) -> None:
    source = album_folder(tmp_path / "inbox" / "Artist - Album")
    organizer = AlbumOrganizer()

    decision = organizer.decision_for_node(
        source,
        "melodic-black-metal",
        taxonomy(),
        tmp_path / "library",
    )

    assert (
        decision.destination_path
        == tmp_path / "library" / "Metal" / "Black Metal" / "Melodic Black Metal" / "Artist - Album"
    )


def test_apply_moves_album_when_decision_is_not_a_dry_run(tmp_path) -> None:
    source = album_folder(tmp_path / "inbox" / "Artist - Album")
    organizer = AlbumOrganizer()
    decision = organizer.decision_for_override(
        source,
        ManualOverride("artist_album", "black-metal", artist="Artist", album="Album"),
        taxonomy(),
        tmp_path / "library",
        dry_run=False,
    )

    organizer.apply(decision)

    assert not source.path.exists()
    assert (decision.destination_path / "01.mp3").exists()  # type: ignore[operator]


def test_apply_refuses_to_merge_with_existing_destination(tmp_path) -> None:
    source = album_folder(tmp_path / "inbox" / "Artist - Album")
    organizer = AlbumOrganizer()
    decision = organizer.decision_for_override(
        source,
        ManualOverride("artist_album", "black-metal", artist="Artist", album="Album"),
        taxonomy(),
        tmp_path / "library",
        dry_run=False,
    )
    assert decision.destination_path is not None
    decision.destination_path.mkdir(parents=True)

    with pytest.raises(FileExistsError):
        organizer.apply(decision)

    assert source.path.exists()
