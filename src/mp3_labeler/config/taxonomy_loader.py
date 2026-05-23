from __future__ import annotations

from pathlib import Path

from mp3_labeler.domain.taxonomy import Taxonomy


class TaxonomyLoader:
    def load(self, path: Path) -> Taxonomy:
        raise NotImplementedError

