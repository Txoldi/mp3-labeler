from __future__ import annotations

import argparse


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

    if args.command == "review":
        print("review is scaffolded only")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
