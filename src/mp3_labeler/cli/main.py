from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from mp3_labeler.config.taxonomy_loader import TaxonomyLoader
from mp3_labeler.domain.models import AlbumMetadata, LastFmTag
from mp3_labeler.domain.scoring import ClassificationResult
from mp3_labeler.domain.taxonomy import Taxonomy
from mp3_labeler.infrastructure.db import open_connection
from mp3_labeler.infrastructure.lastfm_client import LastFmClient, LastFmClientError
from mp3_labeler.infrastructure.metadata_reader import MetadataReader
from mp3_labeler.infrastructure.repositories import LastFmCacheRepository
from mp3_labeler.services.album_metadata_builder import AlbumMetadataBuilder
from mp3_labeler.services.classifier import AlbumClassifier
from mp3_labeler.services.lastfm_lookup import InsufficientMetadataError, LastFmLookup
from mp3_labeler.services.scanner import InboxScanner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mp3-labeler",
        description="Organize MP3 album folders using a user-controlled genre taxonomy.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Scan an inbox and propose safe organization decisions.")
    scan_parser.add_argument("--inbox", required=True, help="Folder containing incoming album folders.")
    scan_parser.add_argument("--library", required=True, help="Root folder for the organized music library.")
    scan_parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    scan_parser.add_argument(
        "--genre-depth",
        type=int,
        default=1,
        help="Number of taxonomy levels to write to MP3 genre tags. Use 0 to leave genre tags unchanged.",
    )

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Read album metadata and genre evidence without modifying files.",
    )
    inspect_parser.add_argument("--inbox", required=True, type=Path, help="Folder containing incoming album folders.")
    inspect_parser.add_argument(
        "--taxonomy",
        type=Path,
        default=Path("config/taxonomy.example.toml"),
        help="TOML file defining the user-controlled taxonomy.",
    )
    inspect_parser.add_argument(
        "--lastfm",
        action="store_true",
        help="Fetch Last.fm evidence using the LASTFM_API_KEY environment variable.",
    )
    inspect_parser.add_argument(
        "--cache-db",
        type=Path,
        default=Path(".mp3-labeler-cache.sqlite3"),
        help="SQLite cache file used for Last.fm responses.",
    )
    inspect_parser.add_argument(
        "--refresh-lastfm",
        action="store_true",
        help="Bypass cached Last.fm responses and replace them with fresh lookups.",
    )

    subparsers.add_parser("review", help="Review albums that could not be classified safely.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        print(
            "scan is scaffolded only: "
            f"inbox={args.inbox}, library={args.library}, dry_run={args.dry_run}, "
            f"genre_depth={args.genre_depth}"
        )
        return 0

    if args.command == "inspect":
        if args.refresh_lastfm and not args.lastfm:
            parser.error("--refresh-lastfm requires --lastfm")
        return inspect_inbox(
            args.inbox,
            args.taxonomy,
            use_lastfm=args.lastfm,
            cache_db=args.cache_db,
            refresh_lastfm=args.refresh_lastfm,
        )

    if args.command == "review":
        print("review is scaffolded only")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def inspect_inbox(
    inbox: Path,
    taxonomy_path: Path,
    *,
    use_lastfm: bool = False,
    cache_db: Path = Path(".mp3-labeler-cache.sqlite3"),
    refresh_lastfm: bool = False,
) -> int:
    taxonomy = TaxonomyLoader().load(taxonomy_path)
    albums = InboxScanner().scan(inbox)
    reader = MetadataReader()
    builder = AlbumMetadataBuilder()
    classifier = AlbumClassifier()
    lookup = _build_lastfm_lookup(cache_db) if use_lastfm else None

    print(f"Inbox: {inbox}")
    print(f"Albums found: {len(albums)}")

    for album_folder in albums:
        tracks = tuple(reader.read_track(path) for path in album_folder.audio_files)
        result = builder.build(tracks, taxonomy)
        metadata = result.album_metadata
        evidence = result.existing_genre_evidence

        print()
        print(f"Folder: {album_folder.path}")
        print(f"Artist: {metadata.album_artist or metadata.artist or '(unknown)'}")
        print(f"Album: {metadata.album or '(unknown)'}")
        print(f"Year: {metadata.year if metadata.year is not None else '(unknown)'}")
        print(f"Tracks: {len(metadata.tracks)}")
        print(f"Local metadata confidence: {metadata.confidence:.2f}")
        print(f"Existing genres: {', '.join(evidence.raw_values) or '(none)'}")
        print(f"Matched taxonomy nodes: {', '.join(evidence.matched_taxonomy_node_ids) or '(none)'}")
        print(f"Genre consistency: {evidence.consistency_ratio:.2f}")

        lastfm_tags = _get_lastfm_evidence(lookup, metadata, refresh=refresh_lastfm) if lookup is not None else ()
        classification = classifier.classify(metadata, lastfm_tags, taxonomy, evidence)
        _print_classification(classification, taxonomy)

    return 0


def _build_lastfm_lookup(cache_db: Path) -> LastFmLookup:
    api_key = os.environ.get("LASTFM_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Set LASTFM_API_KEY before running inspect with --lastfm.")

    api_secret = os.environ.get("LASTFM_API_SECRET")
    cache = LastFmCacheRepository(open_connection(cache_db))
    return LastFmLookup(LastFmClient(api_key=api_key, api_secret=api_secret), cache=cache)


def _get_lastfm_evidence(
    lookup: LastFmLookup, metadata: AlbumMetadata, *, refresh: bool = False
) -> tuple[LastFmTag, ...]:
    try:
        tags = lookup.get_tags(metadata, refresh=refresh)
    except InsufficientMetadataError as error:
        print(f"Last.fm: skipped ({error})")
        return ()
    except LastFmClientError as error:
        print(f"Last.fm: failed ({error})", file=sys.stderr)
        return ()

    if not tags:
        print("Last.fm tags: (none)")
        return ()

    print("Last.fm tags:")
    for tag in tags:
        print(f"  {tag.source}: {tag.name} ({tag.weight:g})")
    return tags


def _print_classification(result: ClassificationResult, taxonomy: Taxonomy) -> None:
    print("Classification:")
    if result.winner is None:
        print("  Proposed node: (none)")
        print("  Decision: review required")
        print(f"  Reason: {result.reason}")
        return

    node = taxonomy.by_id()[result.winner.taxonomy_node_id]
    decision = "review required" if result.requires_review else "eligible for automatic processing"
    print(f"  Proposed node: {node.name} [{node.id}]")
    print(f"  Destination folder: {node.folder_path}")
    print(f"  Score: {result.winner.score:.2f}")
    print(f"  Confidence: {result.winner.confidence:.2f}")
    print(f"  Decision: {decision}")
    print(f"  Reason: {result.reason}")

    if result.winner.evidence:
        print("  Evidence:")
        for evidence in result.winner.evidence:
            print(f"    {evidence.source}: {evidence.description} ({evidence.weight:+.2f})")
    if result.winner.conflicts:
        print("  Conflicts:")
        for conflict in result.winner.conflicts:
            print(f"    {conflict}")
    if result.alternatives:
        print("  Alternatives:")
        for alternative in result.alternatives[:3]:
            alternative_node = taxonomy.by_id()[alternative.taxonomy_node_id]
            print(
                f"    {alternative_node.name} [{alternative_node.id}]: "
                f"score={alternative.score:.2f}, confidence={alternative.confidence:.2f}"
            )


if __name__ == "__main__":
    raise SystemExit(main())
