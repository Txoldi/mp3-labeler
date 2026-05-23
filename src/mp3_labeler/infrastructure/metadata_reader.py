from __future__ import annotations

from pathlib import Path

from mutagen import MutagenError
from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.mp3 import MP3, HeaderNotFoundError

from mp3_labeler.domain.models import TrackMetadata


class MetadataReader:
    def read_track(self, path: Path) -> TrackMetadata:
        if not path.exists():
            raise FileNotFoundError(f"Audio file does not exist: {path}")
        if not path.is_file():
            raise IsADirectoryError(f"Audio path is not a file: {path}")

        tags = self._read_id3(path)
        return TrackMetadata(
            path=path,
            title=self._first_text(tags, "TIT2"),
            artist=self._first_text(tags, "TPE1"),
            album_artist=self._first_text(tags, "TPE2"),
            album=self._first_text(tags, "TALB"),
            track_number=self._first_int(tags, "TRCK"),
            disc_number=self._first_int(tags, "TPOS"),
            year=self._year(tags),
            duration_seconds=self._duration_seconds(path),
            existing_genre=self._joined_text(tags, "TCON"),
        )

    @staticmethod
    def _read_id3(path: Path) -> ID3:
        try:
            return ID3(path)
        except ID3NoHeaderError:
            return ID3()

    @staticmethod
    def _duration_seconds(path: Path) -> float | None:
        try:
            return float(MP3(path).info.length)
        except (HeaderNotFoundError, MutagenError):
            return None

    @staticmethod
    def _first_text(tags: ID3, frame_id: str) -> str | None:
        frame = tags.get(frame_id)
        if frame is None:
            return None

        values = getattr(frame, "text", ())
        if not values:
            return None

        value = str(values[0]).strip()
        return value or None

    @classmethod
    def _joined_text(cls, tags: ID3, frame_id: str) -> str | None:
        frame = tags.get(frame_id)
        if frame is None:
            return None

        values = getattr(frame, "text", ())
        cleaned_values = tuple(str(value).strip() for value in values if str(value).strip())
        if not cleaned_values:
            return None

        return "; ".join(cleaned_values)

    @classmethod
    def _first_int(cls, tags: ID3, frame_id: str) -> int | None:
        value = cls._first_text(tags, frame_id)
        if value is None:
            return None

        first_part = value.split("/", maxsplit=1)[0].strip()
        try:
            return int(first_part)
        except ValueError:
            return None

    @classmethod
    def _year(cls, tags: ID3) -> int | None:
        value = cls._first_text(tags, "TDRC") or cls._first_text(tags, "TYER")
        if value is None:
            return None

        year_text = value.strip()[:4]
        try:
            return int(year_text)
        except ValueError:
            return None


__all__ = ["MetadataReader"]
