from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from mp3_labeler.domain.models import AlbumFolder, Decision, DecisionAction
from mp3_labeler.services.apply_preflight import ApplyPreflightValidator


def album_folder(path: Path) -> AlbumFolder:
    path.mkdir(parents=True)
    track = path / "01.mp3"
    track.write_bytes(b"track")
    return AlbumFolder(path, (track,), datetime(2026, 6, 1))


def decision_for(album: AlbumFolder, destination: Path) -> Decision:
    return Decision(
        album_folder=album,
        action=DecisionAction.MOVE,
        reason="test",
        destination_path=destination,
        dry_run=False,
    )


def test_preflight_creates_destination_parent_without_creating_album_folder(tmp_path) -> None:
    album = album_folder(tmp_path / "inbox" / "Artist - Album")
    destination = tmp_path / "library" / "Metal" / "Death Metal" / "Artist - Album"

    ApplyPreflightValidator().validate_decision(decision_for(album, destination), write_tags=True)

    assert destination.parent.exists()
    assert not destination.exists()


def test_preflight_rejects_unwritable_audio_file(tmp_path, monkeypatch) -> None:
    album = album_folder(tmp_path / "inbox" / "Artist - Album")
    destination = tmp_path / "library" / "Metal" / "Death Metal" / "Artist - Album"

    def deny_audio_writes(path: Path, mode: int) -> bool:
        return path != album.audio_files[0]

    monkeypatch.setattr("mp3_labeler.services.apply_preflight.os.access", deny_audio_writes)

    with pytest.raises(PermissionError, match="Audio file is not writable"):
        ApplyPreflightValidator().validate_decision(decision_for(album, destination), write_tags=True)


def test_preflight_skips_audio_writability_when_tags_are_not_written(tmp_path, monkeypatch) -> None:
    album = album_folder(tmp_path / "inbox" / "Artist - Album")
    destination = tmp_path / "library" / "Metal" / "Death Metal" / "Artist - Album"

    def deny_audio_writes(path: Path, mode: int) -> bool:
        return path != album.audio_files[0]

    monkeypatch.setattr("mp3_labeler.services.apply_preflight.os.access", deny_audio_writes)

    ApplyPreflightValidator().validate_decision(decision_for(album, destination), write_tags=False)


def test_preflight_validates_database_parent(tmp_path) -> None:
    database_path = tmp_path / "data" / "mp3-labeler.sqlite3"

    ApplyPreflightValidator().validate_database_path(database_path)

    assert database_path.parent.exists()
