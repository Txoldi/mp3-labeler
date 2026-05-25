from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from mp3_labeler.domain.models import AlbumMetadata, ExistingGenreEvidence, TrackMetadata
from mp3_labeler.domain.taxonomy import Taxonomy


@dataclass(frozen=True, slots=True)
class AlbumMetadataBuildResult:
    album_metadata: AlbumMetadata
    existing_genre_evidence: ExistingGenreEvidence


class AlbumMetadataBuilder:
    def build(self, tracks: tuple[TrackMetadata, ...], taxonomy: Taxonomy | None = None) -> AlbumMetadataBuildResult:
        if not tracks:
            raise ValueError("Cannot build album metadata without tracks")

        album_artist = self._dominant_value(track.album_artist for track in tracks)
        artist = album_artist or self._dominant_value(track.artist for track in tracks)
        album = self._dominant_value(track.album for track in tracks)
        year = self._dominant_int(track.year for track in tracks)

        album_metadata = AlbumMetadata(
            artist=artist,
            album=album,
            album_artist=album_artist,
            year=year,
            tracks=tracks,
            confidence=self._metadata_confidence(tracks, artist=artist, album=album),
            source="track_metadata",
        )

        return AlbumMetadataBuildResult(
            album_metadata=album_metadata,
            existing_genre_evidence=self.derive_existing_genre_evidence(tracks, taxonomy),
        )

    def derive_existing_genre_evidence(
        self, tracks: tuple[TrackMetadata, ...], taxonomy: Taxonomy | None = None
    ) -> ExistingGenreEvidence:
        raw_values = tuple(
            genre.strip()
            for track in tracks
            if track.existing_genre is not None
            for genre in track.existing_genre.split(";")
            if genre.strip()
        )
        normalized_values = tuple(dict.fromkeys(Taxonomy.normalize_label(value) for value in raw_values))

        if not raw_values:
            return ExistingGenreEvidence(
                raw_values=(),
                normalized_values=(),
                matched_taxonomy_node_ids=(),
                consistency_ratio=0.0,
                source_tracks_count=0,
            )

        per_track_normalized = tuple(
            tuple(
                Taxonomy.normalize_label(genre)
                for genre in track.existing_genre.split(";")
                if genre.strip()
            )
            for track in tracks
            if track.existing_genre is not None and track.existing_genre.strip()
        )
        genre_counts = Counter(genre for genres in per_track_normalized for genre in set(genres))
        most_common_count = genre_counts.most_common(1)[0][1]

        matched_node_ids = (
            ()
            if taxonomy is None
            else tuple(
                dict.fromkeys(
                    node_id
                    for value in normalized_values
                    for node_id in taxonomy.match_genre_node_ids(value)
                )
            )
        )

        return ExistingGenreEvidence(
            raw_values=tuple(dict.fromkeys(raw_values)),
            normalized_values=normalized_values,
            matched_taxonomy_node_ids=matched_node_ids,
            consistency_ratio=most_common_count / len(per_track_normalized),
            source_tracks_count=len(per_track_normalized),
        )

    @classmethod
    def _metadata_confidence(cls, tracks: tuple[TrackMetadata, ...], *, artist: str | None, album: str | None) -> float:
        populated_fields = 0
        total_fields = 2

        if artist is not None:
            populated_fields += cls._dominance_score(
                tuple(track.album_artist or track.artist for track in tracks if track.album_artist or track.artist)
            )
        if album is not None:
            populated_fields += cls._dominance_score(tuple(track.album for track in tracks if track.album))

        return populated_fields / total_fields

    @staticmethod
    def _dominant_value(values) -> str | None:
        cleaned_values = tuple(str(value).strip() for value in values if value is not None and str(value).strip())
        if not cleaned_values:
            return None

        return Counter(cleaned_values).most_common(1)[0][0]

    @staticmethod
    def _dominant_int(values) -> int | None:
        cleaned_values = tuple(value for value in values if value is not None)
        if not cleaned_values:
            return None

        return Counter(cleaned_values).most_common(1)[0][0]

    @staticmethod
    def _dominance_score(values: tuple[str, ...]) -> float:
        if not values:
            return 0.0

        return Counter(values).most_common(1)[0][1] / len(values)

__all__ = ["AlbumMetadataBuilder", "AlbumMetadataBuildResult"]
