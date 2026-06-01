from __future__ import annotations

from pathlib import Path

from mutagen.id3 import ID3, ID3NoHeaderError, TCON


class MetadataWriter:
    def read_genres(self, path: Path) -> tuple[str, ...]:
        filename = str(path)
        try:
            tags = ID3(filename)
        except ID3NoHeaderError:
            return ()
        frame = tags.get("TCON")
        return tuple(str(value).strip() for value in getattr(frame, "text", ()) if str(value).strip())

    def write_genres(self, path: Path, genres: tuple[str, ...]) -> None:
        filename = str(path)
        try:
            tags = ID3(filename)
        except ID3NoHeaderError:
            tags = ID3()
        tags.delall("TCON")
        if genres:
            tags.add(TCON(encoding=3, text=list(genres)))
        tags.save(filename, v1=0)

    def write_genre(self, path: Path, genre: str) -> None:
        self.write_genres(path, (genre,))


__all__ = ["MetadataWriter"]
