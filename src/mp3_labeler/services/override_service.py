from __future__ import annotations

from mp3_labeler.domain.models import AlbumMetadata, ManualOverride


class OverrideService:
    def find_override(self, metadata: AlbumMetadata) -> ManualOverride | None:
        raise NotImplementedError

