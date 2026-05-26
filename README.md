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
mp3-labeler inspect --inbox ./inbox --taxonomy ./config/taxonomy.example.toml
mp3-labeler review
```

`inspect` is read-only: it scans MP3 files, reads their tags, builds album-level metadata, and maps any existing genres to the configured taxonomy.

To include Last.fm evidence during inspection, provide the API key through an environment variable rather than a command-line argument:

```powershell
$env:LASTFM_API_KEY = "your-api-key"
mp3-labeler inspect --inbox ./inbox --taxonomy ./config/taxonomy.example.toml --lastfm
```

The current read-only Last.fm queries use the API key. `LASTFM_API_SECRET` is accepted for later authenticated Last.fm operations, but is not needed for local inspection.

Last.fm responses are cached in `.mp3-labeler-cache.sqlite3` by default. Successful lookups remain fresh for 30 days; not-found responses remain fresh for 7 days. Choose another file or force new requests when needed:

```powershell
mp3-labeler inspect --inbox ./inbox --lastfm --cache-db ./data/lastfm.sqlite3
mp3-labeler inspect --inbox ./inbox --lastfm --refresh-lastfm
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
