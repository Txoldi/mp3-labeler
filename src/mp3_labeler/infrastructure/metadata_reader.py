from __future__ import annotations

from pathlib import Path

from mp3_labeler.domain.models import TrackMetadata


class MetadataReader:
    def read_track(self, path: Path) -> TrackMetadata:
        raise NotImplementedError

