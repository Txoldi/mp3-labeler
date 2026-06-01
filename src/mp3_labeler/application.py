from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection

from mp3_labeler.config.taxonomy_loader import TaxonomyLoader
from mp3_labeler.domain.models import AlbumFolder, AlbumMetadata, ExistingGenreEvidence, LastFmTag, ManualOverride
from mp3_labeler.domain.scoring import ClassificationResult
from mp3_labeler.domain.taxonomy import Taxonomy
from mp3_labeler.infrastructure.db import open_connection
from mp3_labeler.infrastructure.lastfm_client import LastFmClient, LastFmClientError
from mp3_labeler.infrastructure.metadata_reader import MetadataReader
from mp3_labeler.infrastructure.repositories import DecisionRepository, LastFmCacheRepository
from mp3_labeler.services.album_metadata_builder import AlbumMetadataBuilder
from mp3_labeler.services.apply_preflight import ApplyPreflightValidator
from mp3_labeler.services.classifier import AlbumClassifier
from mp3_labeler.services.lastfm_lookup import InsufficientMetadataError, LastFmLookup
from mp3_labeler.services.organizer import AlbumOrganizer
from mp3_labeler.services.override_service import OverrideFileStore, OverrideService
from mp3_labeler.services.scanner import InboxScanner
from mp3_labeler.services.tag_writer import TagWriter


@dataclass(frozen=True, slots=True)
class AlbumAnalysis:
    folder: AlbumFolder
    metadata: AlbumMetadata
    existing_genre: ExistingGenreEvidence
    lastfm_tags: tuple[LastFmTag, ...]
    lastfm_note: str | None
    classification: ClassificationResult | None
    override: ManualOverride | None

    @property
    def proposed_node_id(self) -> str | None:
        if self.override is not None:
            return self.override.taxonomy_node_id
        if self.classification is not None and self.classification.winner is not None:
            return self.classification.winner.taxonomy_node_id
        return None


@dataclass(frozen=True, slots=True)
class ScanOptions:
    inbox: Path
    taxonomy_path: Path
    override_path: Path
    use_lastfm: bool = False
    refresh_lastfm: bool = False


@dataclass(frozen=True, slots=True)
class ApplyOptions:
    inbox: Path
    taxonomy_path: Path
    override_path: Path
    database_path: Path
    use_lastfm: bool = False
    refresh_lastfm: bool = False


@dataclass(frozen=True, slots=True)
class ScanResult:
    taxonomy: Taxonomy
    analyses: tuple[AlbumAnalysis, ...]


@dataclass(frozen=True, slots=True)
class ApplyContext:
    taxonomy: Taxonomy
    analyses: tuple[AlbumAnalysis, ...]
    connection: Connection
    organizer: AlbumOrganizer
    tag_writer: TagWriter
    history: DecisionRepository
    override_store: OverrideFileStore
    preflight: ApplyPreflightValidator


class LabelerApplication:
    def __init__(
        self,
        *,
        lastfm_client_factory: Callable[..., LastFmClient] = LastFmClient,
        taxonomy_loader: TaxonomyLoader | None = None,
    ) -> None:
        self.lastfm_client_factory = lastfm_client_factory
        self.taxonomy_loader = taxonomy_loader or TaxonomyLoader()

    def scan(self, options: ScanOptions) -> ScanResult:
        taxonomy = self.taxonomy_loader.load(options.taxonomy_path)
        overrides = self._load_overrides(options.override_path, taxonomy)
        lookup = self._build_lastfm_lookup(cache=None) if options.use_lastfm else None
        analyses = self._analyze(
            options.inbox,
            taxonomy,
            overrides,
            lookup,
            refresh_lastfm=options.refresh_lastfm,
        )
        return ScanResult(taxonomy=taxonomy, analyses=analyses)

    def prepare_apply(self, options: ApplyOptions) -> ApplyContext:
        preflight = ApplyPreflightValidator()
        preflight.validate_database_path(options.database_path)
        taxonomy = self.taxonomy_loader.load(options.taxonomy_path)
        overrides = self._load_overrides(options.override_path, taxonomy)
        connection = open_connection(options.database_path)
        lookup = (
            self._build_lastfm_lookup(cache=LastFmCacheRepository(connection))
            if options.use_lastfm
            else None
        )
        analyses = self._analyze(
            options.inbox,
            taxonomy,
            overrides,
            lookup,
            refresh_lastfm=options.refresh_lastfm,
        )
        return ApplyContext(
            taxonomy=taxonomy,
            analyses=analyses,
            connection=connection,
            organizer=AlbumOrganizer(),
            tag_writer=TagWriter(),
            history=DecisionRepository(connection),
            override_store=OverrideFileStore(taxonomy),
            preflight=preflight,
        )

    def _analyze(
        self,
        inbox: Path,
        taxonomy: Taxonomy,
        overrides: OverrideService,
        lookup: LastFmLookup | None,
        *,
        refresh_lastfm: bool,
    ) -> tuple[AlbumAnalysis, ...]:
        reader = MetadataReader()
        builder = AlbumMetadataBuilder()
        classifier = AlbumClassifier()
        results: list[AlbumAnalysis] = []
        for folder in InboxScanner().scan(inbox):
            tracks = tuple(reader.read_track(path) for path in folder.audio_files)
            built = builder.build(tracks, taxonomy)
            metadata = built.album_metadata
            override = overrides.find_override(metadata)
            if override is not None:
                results.append(AlbumAnalysis(folder, metadata, built.existing_genre_evidence, (), None, None, override))
                continue
            tags, lastfm_note = (
                self._get_lastfm_evidence(lookup, metadata, refresh=refresh_lastfm)
                if lookup is not None
                else ((), None)
            )
            classification = classifier.classify(metadata, tags, taxonomy, built.existing_genre_evidence)
            results.append(
                AlbumAnalysis(folder, metadata, built.existing_genre_evidence, tags, lastfm_note, classification, None)
            )
        return tuple(results)

    def _build_lastfm_lookup(self, cache: LastFmCacheRepository | None) -> LastFmLookup:
        api_key = os.environ.get("LASTFM_API_KEY", "").strip()
        if not api_key:
            raise SystemExit("Set LASTFM_API_KEY before running with --lastfm.")
        return LastFmLookup(
            self.lastfm_client_factory(api_key=api_key, api_secret=os.environ.get("LASTFM_API_SECRET")),
            cache=cache,
        )

    @staticmethod
    def _load_overrides(path: Path, taxonomy: Taxonomy) -> OverrideService:
        return OverrideService.load(path, taxonomy) if path.exists() else OverrideService((), taxonomy)

    @staticmethod
    def _get_lastfm_evidence(
        lookup: LastFmLookup, metadata: AlbumMetadata, *, refresh: bool = False
    ) -> tuple[tuple[LastFmTag, ...], str | None]:
        try:
            tags = lookup.get_tags(metadata, refresh=refresh)
        except InsufficientMetadataError as error:
            return (), f"Last.fm: skipped ({error})"
        except LastFmClientError as error:
            return (), f"Last.fm: failed ({error})"
        return tags, None if tags else "Last.fm tags: (none)"


__all__ = [
    "AlbumAnalysis",
    "ApplyContext",
    "ApplyOptions",
    "LabelerApplication",
    "ScanOptions",
    "ScanResult",
]
