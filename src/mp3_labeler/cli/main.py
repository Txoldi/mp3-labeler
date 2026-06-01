from __future__ import annotations

import argparse
import contextlib
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from sqlite3 import Connection
from typing import Callable, TextIO

from mp3_labeler.config.taxonomy_loader import TaxonomyLoader
from mp3_labeler.domain.models import (
    AlbumFolder,
    AlbumMetadata,
    AppliedAlbumDecision,
    ExistingGenreEvidence,
    LastFmTag,
    ManualOverride,
)
from mp3_labeler.domain.scoring import ClassificationResult
from mp3_labeler.domain.taxonomy import Taxonomy
from mp3_labeler.infrastructure.db import open_connection
from mp3_labeler.infrastructure.lastfm_client import LastFmClient, LastFmClientError
from mp3_labeler.infrastructure.metadata_reader import MetadataReader
from mp3_labeler.infrastructure.repositories import DecisionRepository, LastFmCacheRepository
from mp3_labeler.services.album_metadata_builder import AlbumMetadataBuilder
from mp3_labeler.services.classifier import AlbumClassifier
from mp3_labeler.services.lastfm_lookup import InsufficientMetadataError, LastFmLookup
from mp3_labeler.services.organizer import AlbumOrganizer, album_destination
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mp3-labeler",
        description="Analyze or apply music album organization using a user-controlled taxonomy.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    scan_parser = commands.add_parser("scan", help="Analyze the inbox without modifying files or state.")
    _add_pipeline_arguments(scan_parser, include_database=False)

    apply_parser = commands.add_parser("apply", help="Analyze, confirm, tag, move, and record albums.")
    _add_pipeline_arguments(apply_parser, include_database=True)
    apply_parser.add_argument(
        "--accept-automatic-tags",
        action="store_true",
        help="Apply classifications meeting automatic confidence gates without prompting.",
    )
    apply_parser.add_argument(
        "--save-overrides",
        action="store_true",
        help="Automatically save applied classifications as permanent TOML overrides.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.genre_depth < 0:
        parser.error("--genre-depth must be zero or greater")
    if args.refresh_lastfm and not args.lastfm:
        parser.error("--refresh-lastfm requires --lastfm")

    if args.command == "scan":
        return _run_with_optional_log(
            args.log,
            args.command,
            lambda: scan_inbox(
                args.inbox,
                args.library,
                args.taxonomy,
                override_path=args.override,
                use_lastfm=args.lastfm,
                refresh_lastfm=args.refresh_lastfm,
                genre_depth=args.genre_depth,
            ),
        )
    if args.command == "apply":
        return _run_with_optional_log(
            args.log,
            args.command,
            lambda: apply_inbox(
                args.inbox,
                args.library,
                args.taxonomy,
                override_path=args.override,
                database_path=args.db,
                use_lastfm=args.lastfm,
                refresh_lastfm=args.refresh_lastfm,
                genre_depth=args.genre_depth,
                accept_automatic_tags=args.accept_automatic_tags,
                save_overrides=args.save_overrides,
            ),
        )
    parser.error(f"unknown command: {args.command}")
    return 2


def scan_inbox(
    inbox: Path,
    library: Path,
    taxonomy_path: Path,
    *,
    override_path: Path,
    use_lastfm: bool = False,
    refresh_lastfm: bool = False,
    genre_depth: int = 1,
) -> int:
    taxonomy = TaxonomyLoader().load(taxonomy_path)
    overrides = _load_overrides(override_path, taxonomy)
    lookup = _build_lastfm_lookup(cache=None) if use_lastfm else None
    analyses = _analyze(inbox, taxonomy, overrides, lookup, refresh_lastfm=refresh_lastfm)
    print(f"Inbox: {inbox}")
    print(f"Library: {library}")
    print("Mode: scan (read-only)")
    print(f"Albums found: {len(analyses)}")
    for analysis in analyses:
        _print_analysis(analysis, taxonomy, library, genre_depth)
    return 0


def apply_inbox(
    inbox: Path,
    library: Path,
    taxonomy_path: Path,
    *,
    override_path: Path,
    database_path: Path,
    use_lastfm: bool = False,
    refresh_lastfm: bool = False,
    genre_depth: int = 1,
    accept_automatic_tags: bool = False,
    save_overrides: bool = False,
) -> int:
    taxonomy = TaxonomyLoader().load(taxonomy_path)
    overrides = _load_overrides(override_path, taxonomy)
    connection = open_connection(database_path)
    lookup = _build_lastfm_lookup(cache=LastFmCacheRepository(connection)) if use_lastfm else None
    analyses = _analyze(inbox, taxonomy, overrides, lookup, refresh_lastfm=refresh_lastfm)
    organizer = AlbumOrganizer()
    tag_writer = TagWriter()
    history = DecisionRepository(connection)
    override_store = OverrideFileStore(taxonomy)
    failures = 0

    print(f"Inbox: {inbox}")
    print(f"Library: {library}")
    print("Mode: apply")
    print(f"Albums found: {len(analyses)}")
    for analysis in analyses:
        _print_analysis(analysis, taxonomy, library, genre_depth)
        selection = _select_for_apply(analysis, taxonomy, accept_automatic_tags)
        if selection is None:
            print("Action: skipped; files unchanged.")
            continue
        node_id, decision_source = selection
        genres = _genre_values(node_id, taxonomy, genre_depth)
        decision = organizer.decision_for_node(
            analysis.folder,
            node_id,
            taxonomy,
            library,
            dry_run=False,
            reason=decision_source,
        )
        assert decision.destination_path is not None
        try:
            organizer.validate(decision)
        except (FileExistsError, FileNotFoundError, NotADirectoryError, ValueError) as error:
            failures += 1
            print(f"Action blocked: {error}")
            continue

        persist_override = _should_save_override(
            analysis,
            decision_source,
            save_overrides=save_overrides,
        )
        prior_genres = tag_writer.capture_genres(analysis.folder.audio_files)
        tags_written = False
        try:
            if genre_depth > 0:
                tag_writer.write_genres(analysis.folder.audio_files, genres)
                tags_written = True
            organizer.apply(decision)
        except Exception as error:
            if tags_written and analysis.folder.path.exists():
                tag_writer.restore_genres(prior_genres)
            failures += 1
            print(f"Action failed: {error}")
            continue

        history.save_applied(
            AppliedAlbumDecision(
                source_path=analysis.folder.path,
                destination_path=decision.destination_path,
                artist=analysis.metadata.album_artist or analysis.metadata.artist,
                album=analysis.metadata.album,
                taxonomy_node_id=node_id,
                genres_written=genres if genre_depth > 0 else (),
                decision_source=decision_source,
                applied_at=datetime.now(timezone.utc),
            )
        )
        if persist_override:
            override = _override_for_analysis(analysis, node_id)
            if override is None:
                print("Permanent override not saved: album artist and album metadata are required.")
            else:
                override_store.save(override_path, override)
                print(f"Permanent override saved: {override_path}")
        print(f"Applied tags: {', '.join(genres) if genre_depth > 0 else '(unchanged)'}")
        print(f"Moved: {analysis.folder.path} -> {decision.destination_path}")
    return 1 if failures else 0


def _analyze(
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
            _get_lastfm_evidence(lookup, metadata, refresh=refresh_lastfm)
            if lookup is not None
            else ((), None)
        )
        classification = classifier.classify(metadata, tags, taxonomy, built.existing_genre_evidence)
        results.append(AlbumAnalysis(folder, metadata, built.existing_genre_evidence, tags, lastfm_note, classification, None))
    return tuple(results)


def _print_analysis(analysis: AlbumAnalysis, taxonomy: Taxonomy, library: Path, genre_depth: int) -> None:
    metadata = analysis.metadata
    evidence = analysis.existing_genre
    print()
    print(f"Folder: {analysis.folder.path}")
    print(f"Artist: {metadata.album_artist or metadata.artist or '(unknown)'}")
    print(f"Album: {metadata.album or '(unknown)'}")
    print(f"Year: {metadata.year if metadata.year is not None else '(unknown)'}")
    print(f"Existing genres: {', '.join(evidence.raw_values) or '(none)'}")
    print(f"Matched taxonomy nodes: {', '.join(evidence.matched_taxonomy_node_ids) or '(none)'}")
    if analysis.lastfm_tags:
        print("Last.fm tags:")
        for tag in analysis.lastfm_tags:
            print(f"  {tag.source}: {tag.name} ({tag.weight:g})")
    elif analysis.lastfm_note is not None:
        print(analysis.lastfm_note)
    if analysis.override is not None:
        node = taxonomy.by_id()[analysis.override.taxonomy_node_id]
        print(f"Proposed node: {node.name} [{node.id}]")
        print("Decision: permanent override")
        print(f"Reason: matched {analysis.override.match_type} override")
    else:
        assert analysis.classification is not None
        _print_classification(analysis.classification, taxonomy)
    node_id = analysis.proposed_node_id
    if node_id is not None:
        node = taxonomy.by_id()[node_id]
        genres = _genre_values(node_id, taxonomy, genre_depth)
        print(f"Proposed genre tags: {', '.join(genres) if genre_depth > 0 else '(unchanged)'}")
        print(f"Proposed destination: {album_destination(analysis.folder, node.id, taxonomy, library)}")


def _print_classification(result: ClassificationResult, taxonomy: Taxonomy) -> None:
    if result.winner is None:
        print("Proposed node: (none)")
        print("Decision: review required")
        print(f"Reason: {result.reason}")
        return
    node = taxonomy.by_id()[result.winner.taxonomy_node_id]
    decision = "review required" if result.requires_review else "meets automatic confidence gates"
    print(f"Proposed node: {node.name} [{node.id}]")
    print(f"Score: {result.winner.score:.2f}")
    print(f"Confidence: {result.winner.confidence:.2f}")
    print(f"Decision: {decision}")
    print(f"Reason: {result.reason}")
    if result.winner.evidence:
        print("Evidence:")
        for evidence in result.winner.evidence:
            print(f"  {evidence.source}: {evidence.description} ({evidence.weight:+.2f})")
    if result.winner.conflicts:
        print("Conflicts:")
        for conflict in result.winner.conflicts:
            print(f"  {conflict}")
    if result.alternatives:
        print("Alternatives:")
        for alternative in result.alternatives[:3]:
            node = taxonomy.by_id()[alternative.taxonomy_node_id]
            print(f"  {node.name} [{node.id}]: score={alternative.score:.2f}, confidence={alternative.confidence:.2f}")


def _select_for_apply(
    analysis: AlbumAnalysis, taxonomy: Taxonomy, accept_automatic_tags: bool
) -> tuple[str, str] | None:
    if analysis.override is not None:
        return analysis.override.taxonomy_node_id, "permanent_override"
    assert analysis.classification is not None
    proposed = analysis.proposed_node_id
    is_automatic = not analysis.classification.requires_review and proposed is not None
    if is_automatic and accept_automatic_tags:
        print("Action: automatic classification accepted by --accept-automatic-tags.")
        return proposed, "automatic"
    selected = _prompt_for_node(proposed, taxonomy)
    if selected is None:
        return None
    return selected, "confirmed_automatic" if is_automatic and selected == proposed else "manual"


def _prompt_for_node(proposed: str | None, taxonomy: Taxonomy) -> str | None:
    while True:
        prompt = (
            f"Press Enter to accept '{proposed}', type a taxonomy node/name, or s to skip: "
            if proposed is not None
            else "Type a taxonomy node/name, or s to skip: "
        )
        answer = input(prompt).strip()
        if answer.casefold() in {"s", "skip", "q", "quit"}:
            return None
        if not answer and proposed is not None:
            if proposed in taxonomy.by_id():
                return proposed
            print(f"Proposed taxonomy node '{proposed}' no longer exists.")
            continue
        node_id = _resolve_taxonomy_node(answer, taxonomy)
        if node_id is not None:
            return node_id
        print(f"Unknown or ambiguous taxonomy node '{answer}'. Enter a configured node id or name.")


def _should_save_override(
    analysis: AlbumAnalysis,
    decision_source: str,
    *,
    save_overrides: bool,
) -> bool:
    if analysis.override is not None:
        return False
    if save_overrides:
        return True
    return _ask_yes_no("Save this classification as a permanent override? [y/N]: ")


def _ask_yes_no(prompt: str) -> bool:
    return input(prompt).strip().casefold() in {"y", "yes"}


def _override_for_analysis(analysis: AlbumAnalysis, node_id: str) -> ManualOverride | None:
    artist = analysis.metadata.album_artist or analysis.metadata.artist
    album = analysis.metadata.album
    if not artist or not album:
        return None
    return ManualOverride(
        match_type="artist_album",
        artist=artist,
        album=album,
        taxonomy_node_id=node_id,
        notes="Saved during apply.",
    )


def _genre_values(node_id: str, taxonomy: Taxonomy, genre_depth: int) -> tuple[str, ...]:
    if genre_depth == 0:
        return ()
    nodes = taxonomy.by_id()
    lineage = []
    node = nodes[node_id]
    while True:
        lineage.append(node)
        if node.parent_id is None:
            break
        node = nodes[node.parent_id]
    lineage.reverse()
    selectable = lineage[1:] if len(lineage) > 1 else lineage
    return tuple(node.name for node in selectable[-genre_depth:])


def _load_overrides(path: Path, taxonomy: Taxonomy) -> OverrideService:
    return OverrideService.load(path, taxonomy) if path.exists() else OverrideService((), taxonomy)


def _build_lastfm_lookup(cache: LastFmCacheRepository | None) -> LastFmLookup:
    api_key = os.environ.get("LASTFM_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Set LASTFM_API_KEY before running with --lastfm.")
    return LastFmLookup(
        LastFmClient(api_key=api_key, api_secret=os.environ.get("LASTFM_API_SECRET")),
        cache=cache,
    )


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


def _resolve_taxonomy_node(value: str, taxonomy: Taxonomy) -> str | None:
    if value in taxonomy.by_id():
        return value
    matched_ids = taxonomy.match_genre_node_ids(value)
    return matched_ids[0] if len(matched_ids) == 1 else None


class _Tee:
    def __init__(self, *streams: TextIO) -> None:
        self.streams = streams

    def write(self, value: str) -> int:
        for stream in self.streams:
            stream.write(value)
        return len(value)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def _run_with_optional_log(log_path: Path | None, command: str, action: Callable[[], int]) -> int:
    if log_path is None:
        return action()

    resolved_path = _resolve_log_path(log_path, command)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    with resolved_path.open("w", encoding="utf-8") as log_file:
        with contextlib.redirect_stdout(_Tee(sys.stdout, log_file)):
            print(f"Log: {resolved_path}")
            return action()


def _resolve_log_path(path: Path, command: str) -> Path:
    if path.suffix:
        return path
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return path / f"{command}-{timestamp}.log"


def _add_pipeline_arguments(parser: argparse.ArgumentParser, *, include_database: bool) -> None:
    parser.add_argument("--inbox", required=True, type=Path, help="Folder containing incoming album folders.")
    parser.add_argument("--library", required=True, type=Path, help="Root folder for organized music.")
    parser.add_argument(
        "--taxonomy",
        type=Path,
        default=Path("config/taxonomy.example.toml"),
        help="TOML file defining the user-controlled taxonomy.",
    )
    parser.add_argument(
        "--override",
        type=Path,
        default=Path("config/overrides.toml"),
        help="TOML file containing permanent manual override rules.",
    )
    if include_database:
        parser.add_argument(
            "--db",
            type=Path,
            default=Path(".mp3-labeler.sqlite3"),
            help="SQLite file for Last.fm cache and applied-decision history.",
        )
    parser.add_argument("--lastfm", action="store_true", help="Fetch Last.fm evidence using LASTFM_API_KEY.")
    parser.add_argument("--refresh-lastfm", action="store_true", help="Bypass cached Last.fm evidence.")
    parser.add_argument(
        "--log",
        nargs="?",
        const=Path("logs"),
        type=Path,
        help="Write console output to a log file. If no path is provided, writes under ./logs/.",
    )
    parser.add_argument(
        "--genre-depth",
        type=int,
        default=1,
        help="Number of most-specific subgenre values proposed or written to MP3 genre tags.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
