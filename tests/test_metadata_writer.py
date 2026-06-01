from pathlib import Path

from mutagen.id3 import ID3, TALB, TCON

from mp3_labeler.infrastructure.metadata_writer import MetadataWriter
from mp3_labeler.services.tag_writer import TagWriter


def tagged_file(path: Path) -> None:
    tags = ID3()
    tags.add(TALB(encoding=3, text=["Album"]))
    tags.add(TCON(encoding=3, text=["Old Genre"]))
    tags.save(path)


def test_metadata_writer_replaces_genres_without_losing_other_id3_frames(tmp_path) -> None:
    path = tmp_path / "track.mp3"
    tagged_file(path)

    MetadataWriter().write_genres(path, ("Black Metal", "Melodic Black Metal"))

    tags = ID3(path)
    assert tuple(tags["TCON"].text) == ("Black Metal", "Melodic Black Metal")
    assert tuple(tags["TALB"].text) == ("Album",)


def test_tag_writer_writes_genres_to_each_track_and_can_restore_original_values(tmp_path) -> None:
    first = tmp_path / "01.mp3"
    second = tmp_path / "02.mp3"
    tagged_file(first)
    tagged_file(second)
    writer = TagWriter()
    previous = writer.capture_genres((first, second))

    writer.write_genres((first, second), ("Death Metal",))
    writer.restore_genres(previous)

    assert MetadataWriter().read_genres(first) == ("Old Genre",)
    assert MetadataWriter().read_genres(second) == ("Old Genre",)


def test_metadata_writer_handles_windows_like_special_characters_in_paths(tmp_path) -> None:
    album = tmp_path / "Class Traitor - The Images Aren't Mine (2026)"
    album.mkdir()
    path = album / "03 - High and Plenty Intersection.mp3"
    tagged_file(path)

    MetadataWriter().write_genres(path, ("Post-Hardcore",))

    assert MetadataWriter().read_genres(path) == ("Post-Hardcore",)


def test_tag_writer_does_not_report_a_second_restore_attempt_when_initial_write_fails() -> None:
    class FailingWriter:
        def read_genres(self, path: Path) -> tuple[str, ...]:
            return ("Old Genre",)

        def write_genres(self, path: Path, genres: tuple[str, ...]) -> None:
            raise OSError(9, "Bad file descriptor")

    writer = TagWriter(FailingWriter())  # type: ignore[arg-type]

    try:
        writer.write_genres((Path("01.mp3"),), ("Black Metal", "Melodic Black Metal"))
    except RuntimeError as error:
        assert "restoring previous genre tags also failed" in str(error)
        assert isinstance(error.__cause__, OSError)
    else:
        raise AssertionError("Expected tag write failure")
