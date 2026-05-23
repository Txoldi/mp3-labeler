# mp3-labeler

`mp3-labeler` is a Python 3.12 application for organizing album folders into a user-controlled genre and subgenre taxonomy.

The first milestone is a CLI that scans an inbox folder, reads MP3 metadata, queries Last.fm, classifies albums conservatively, writes metadata only when requested, and moves albums into a library folder.

The initial CLI uses Python's standard `argparse` module to keep runtime dependencies small.

## Design priorities

- Accuracy over speed
- No automatic action on ambiguous matches
- Fully user-controlled taxonomy
- Manual overrides
- Dry-run first workflow
- SQLite-backed cache and decision history
- Testable service boundaries
- Minimal dependencies

## Planned CLI

```powershell
mp3-labeler scan --inbox ./inbox --library ./library --dry-run
mp3-labeler classify ./inbox/AlbumFolder --genre-depth 2 --dry-run
mp3-labeler review
```

## Project layout

```text
src/mp3_labeler/
  cli/              CLI entrypoints
  config/           settings, paths, taxonomy loading
  domain/           data models and scoring types
  services/         application pipeline services
  infrastructure/   filesystem, SQLite, Last.fm, metadata adapters
tests/              unit tests
config/             example user-controlled taxonomy and overrides
```
