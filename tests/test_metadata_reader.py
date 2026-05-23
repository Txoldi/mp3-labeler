from __future__ import annotations

from pathlib import Path

import pytest
from mutagen.id3 import ID3, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TPOS, TRCK, TYER

from mp3_labeler.infrastructure.metadata_reader import MetadataReader


def save_id3_file(path: Path, *frames) -> None:
    tags = ID3()
    for frame in frames:
        tags.add(frame)
    tags.save(path)


def test_read_track_extracts_common_id3_metadata(tmp_path) -> None:
    track_path = tmp_path / "01 - Track.mp3"
    save_id3_file(
        track_path,
        TIT2(encoding=3, text=["Track Title"]),
        TPE1(encoding=3, text=["Track Artist"]),
        TPE2(encoding=3, text=["Album Artist"]),
        TALB(encoding=3, text=["Album Title"]),
        TRCK(encoding=3, text=["1/9"]),
        TPOS(encoding=3, text=["2/3"]),
        TDRC(encoding=3, text=["1995-02-01"]),
        TCON(encoding=3, text=["Death Metal"]),
    )

    metadata = MetadataReader().read_track(track_path)

    assert metadata.path == track_path
    assert metadata.title == "Track Title"
    assert metadata.artist == "Track Artist"
    assert metadata.album_artist == "Album Artist"
    assert metadata.album == "Album Title"
    assert metadata.track_number == 1
    assert metadata.disc_number == 2
    assert metadata.year == 1995
    assert metadata.existing_genre == "Death Metal"
    assert metadata.duration_seconds is None


def test_read_track_returns_empty_metadata_for_file_without_id3_header(tmp_path) -> None:
    track_path = tmp_path / "untagged.mp3"
    track_path.write_bytes(b"not an actual mp3")

    metadata = MetadataReader().read_track(track_path)

    assert metadata.path == track_path
    assert metadata.title is None
    assert metadata.artist is None
    assert metadata.album_artist is None
    assert metadata.album is None
    assert metadata.track_number is None
    assert metadata.disc_number is None
    assert metadata.year is None
    assert metadata.duration_seconds is None
    assert metadata.existing_genre is None


def test_read_track_uses_legacy_year_frame_when_recording_time_is_absent(tmp_path) -> None:
    track_path = tmp_path / "legacy-year.mp3"
    save_id3_file(track_path, TYER(encoding=3, text=["1988"]))

    metadata = MetadataReader().read_track(track_path)

    assert metadata.year == 1988


def test_read_track_returns_none_for_unparseable_track_disc_and_year_values(tmp_path) -> None:
    track_path = tmp_path / "messy-tags.mp3"
    save_id3_file(
        track_path,
        TRCK(encoding=3, text=["side a"]),
        TPOS(encoding=3, text=["disc x"]),
        TDRC(encoding=3, text=["unknown"]),
    )

    metadata = MetadataReader().read_track(track_path)

    assert metadata.track_number is None
    assert metadata.disc_number is None
    assert metadata.year is None


def test_read_track_joins_multiple_genre_values(tmp_path) -> None:
    track_path = tmp_path / "multi-genre.mp3"
    save_id3_file(track_path, TCON(encoding=3, text=["Black Metal", "Symphonic Black Metal"]))

    metadata = MetadataReader().read_track(track_path)

    assert metadata.existing_genre == "Black Metal; Symphonic Black Metal"


def test_read_track_raises_for_missing_file(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        MetadataReader().read_track(tmp_path / "missing.mp3")


def test_read_track_raises_for_directory_path(tmp_path) -> None:
    directory = tmp_path / "album"
    directory.mkdir()

    with pytest.raises(IsADirectoryError):
        MetadataReader().read_track(directory)
