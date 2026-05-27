from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import tomllib

from mp3_labeler.domain.models import AlbumMetadata, ManualOverride
from mp3_labeler.domain.taxonomy import Taxonomy


class OverrideValidationError(ValueError):
    """Raised when manual overrides cannot be interpreted safely."""


class OverrideService:
    _MATCH_PRECEDENCE = {"artist_album": 0, "folder_hash": 1, "artist": 2}

    def __init__(self, overrides: tuple[ManualOverride, ...], taxonomy: Taxonomy) -> None:
        self.taxonomy = taxonomy
        self.overrides = self._validate_overrides(overrides)

    @classmethod
    def load(cls, path: Path, taxonomy: Taxonomy) -> OverrideService:
        if not path.exists():
            raise FileNotFoundError(f"Overrides file does not exist: {path}")
        if not path.is_file():
            raise IsADirectoryError(f"Overrides path is not a file: {path}")

        with path.open("rb") as file:
            try:
                data = tomllib.load(file)
            except tomllib.TOMLDecodeError as error:
                raise OverrideValidationError(f"Invalid overrides TOML: {error}") from error

        values = data.get("overrides", [])
        if not isinstance(values, list):
            raise OverrideValidationError("Overrides configuration field 'overrides' must be a list")
        overrides = tuple(cls._parse_override(value, index) for index, value in enumerate(values, start=1))
        return cls(overrides, taxonomy)

    def find_override(self, metadata: AlbumMetadata, *, folder_hash: str | None = None) -> ManualOverride | None:
        artist = self._normalize_text(metadata.album_artist or metadata.artist)
        album = self._normalize_text(metadata.album)
        normalized_hash = self._normalize_hash(folder_hash)

        for override in self.overrides:
            if override.match_type == "artist_album":
                if artist == self._normalize_text(override.artist) and album == self._normalize_text(override.album):
                    return override
            elif override.match_type == "folder_hash":
                if normalized_hash is not None and normalized_hash == self._normalize_hash(override.folder_hash):
                    return override
            elif override.match_type == "artist":
                if artist == self._normalize_text(override.artist):
                    return override
        return None

    def _validate_overrides(self, overrides: tuple[ManualOverride, ...]) -> tuple[ManualOverride, ...]:
        known_node_ids = set(self.taxonomy.by_id())
        identities: set[tuple[str, ...]] = set()
        validated: list[ManualOverride] = []

        for override in overrides:
            if override.taxonomy_node_id not in known_node_ids:
                raise OverrideValidationError(
                    f"Override refers to unknown taxonomy_node_id '{override.taxonomy_node_id}'"
                )
            identity = self._match_identity(override)
            if identity in identities:
                raise OverrideValidationError(f"Duplicate manual override match: {identity[0]}")
            identities.add(identity)
            validated.append(override)

        return tuple(sorted(validated, key=lambda override: self._MATCH_PRECEDENCE[override.match_type]))

    @classmethod
    def _parse_override(cls, data: Any, index: int) -> ManualOverride:
        if not isinstance(data, Mapping):
            raise OverrideValidationError(f"Override {index} must be a TOML table")

        match_type = cls._required_text(data, "match_type", index)
        if match_type not in cls._MATCH_PRECEDENCE:
            raise OverrideValidationError(
                f"Override {index} match_type must be one of: artist_album, folder_hash, artist"
            )
        taxonomy_node_id = cls._required_text(data, "taxonomy_node_id", index)
        artist = cls._optional_text(data, "artist", index)
        album = cls._optional_text(data, "album", index)
        folder_hash = cls._optional_text(data, "folder_hash", index)

        if match_type == "artist_album" and (artist is None or album is None):
            raise OverrideValidationError(f"Override {index} with match_type 'artist_album' requires artist and album")
        if match_type == "artist" and artist is None:
            raise OverrideValidationError(f"Override {index} with match_type 'artist' requires artist")
        if match_type == "folder_hash" and folder_hash is None:
            raise OverrideValidationError(f"Override {index} with match_type 'folder_hash' requires folder_hash")

        metadata_corrections = data.get("metadata_corrections", {})
        if not isinstance(metadata_corrections, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in metadata_corrections.items()
        ):
            raise OverrideValidationError(
                f"Override {index} metadata_corrections must be a table containing text values"
            )

        return ManualOverride(
            match_type=match_type,
            taxonomy_node_id=taxonomy_node_id,
            artist=artist,
            album=album,
            folder_hash=folder_hash,
            metadata_corrections=dict(metadata_corrections),
            notes=cls._optional_text(data, "notes", index),
        )

    @classmethod
    def _match_identity(cls, override: ManualOverride) -> tuple[str, ...]:
        if override.match_type == "artist_album":
            if not cls._normalize_text(override.artist) or not cls._normalize_text(override.album):
                raise OverrideValidationError("An artist_album override requires artist and album")
            return (
                "artist_album",
                cls._normalize_text(override.artist) or "",
                cls._normalize_text(override.album) or "",
            )
        if override.match_type == "folder_hash":
            if not cls._normalize_hash(override.folder_hash):
                raise OverrideValidationError("A folder_hash override requires folder_hash")
            return ("folder_hash", cls._normalize_hash(override.folder_hash) or "")
        if override.match_type == "artist":
            if not cls._normalize_text(override.artist):
                raise OverrideValidationError("An artist override requires artist")
            return ("artist", cls._normalize_text(override.artist) or "")
        raise OverrideValidationError(f"Unsupported manual override match_type '{override.match_type}'")

    @staticmethod
    def _required_text(data: Mapping[str, Any], field: str, index: int) -> str:
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            raise OverrideValidationError(f"Override {index} requires non-empty text field '{field}'")
        return value.strip()

    @staticmethod
    def _optional_text(data: Mapping[str, Any], field: str, index: int) -> str | None:
        value = data.get(field)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise OverrideValidationError(f"Override {index} field '{field}' must be non-empty text")
        return value.strip()

    @staticmethod
    def _normalize_text(value: str | None) -> str | None:
        if value is None:
            return None
        return " ".join(value.casefold().split())

    @staticmethod
    def _normalize_hash(value: str | None) -> str | None:
        return value.strip().casefold() if value is not None else None


__all__ = ["OverrideService", "OverrideValidationError"]
