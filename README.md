# mp3-labeler

`mp3-labeler` organizes MP3 album folders into a user-controlled genre and subgenre taxonomy. It favors explicit human decisions whenever classification is uncertain.

## Commands

The CLI has two working modes:

- `scan` analyzes the inbox and previews genre tags and destinations. It never modifies files or SQLite state.
- `apply` runs the same analysis, confirms decisions where required, writes genre tags, moves album folders, and records successful actions in SQLite.

### Scan

```powershell
$env:LASTFM_API_KEY = "your-api-key"

mp3-labeler scan `
  --inbox "C:\Temp\Inbox" `
  --library "D:\\Music\Library" `
  --taxonomy .\config\taxonomy.example.toml `
  --override .\config\overrides.toml `
  --lastfm `
  --genre-depth 2
```

For every album, `scan` prints the local metadata evidence, Last.fm evidence when requested, classification result, proposed MP3 genre values, and destination folder.

### Apply

```powershell
mp3-labeler apply `
  --inbox "C:\Temp\Inbox" `
  --library "D:\Music\Library" `
  --taxonomy .\config\taxonomy.example.toml `
  --override .\config\overrides.toml `
  --db .\data\mp3-labeler.sqlite3 `
  --lastfm `
  --genre-depth 2
```

For each album without an existing permanent override:

- Press `Enter` to accept the proposed taxonomy node.
- Type another configured node ID or genre name to correct it.
- Type `s` to leave the album unchanged.
- After acceptance, answer whether the classification should be saved to `overrides.toml` as a permanent rule.

Existing permanent overrides are applied without another prompt.

To automatically accept only classifications that pass the automatic confidence gates:

```powershell
mp3-labeler apply ... --accept-automatic-tags
```

Albums requiring review still prompt for a human decision. Without `--save-overrides`, the program still asks whether each newly applied classification should become a permanent TOML rule.

To save all newly applied classifications as permanent override rules without that save prompt:

```powershell
mp3-labeler apply ... --save-overrides
```

The two flags may be combined for unattended handling of automatically safe classifications:

```powershell
mp3-labeler apply ... --accept-automatic-tags --save-overrides
```

## Apply Safety

- Destinations are validated before genre tags are changed.
- Existing destination album folders are blocked instead of merged or overwritten.
- Tag writes are verified before moving the album.
- If moving fails while the source album remains available, the original genre values are restored.
- Successful applied decisions are recorded in SQLite.
- Permanent TOML overrides always take precedence on future runs.

`--genre-depth` writes the most-specific subgenre values from the approved taxonomy path. For example, selecting `Melodic Black Metal` with `--genre-depth 2` writes `Black Metal` and `Melodic Black Metal`.

## Last.fm Keys

Provide `LASTFM_API_KEY` through the environment rather than storing it in source-controlled files. `scan` uses Last.fm without writing cache state; `apply` caches Last.fm lookups in its SQLite database.

## Project Layout

```text
src/mp3_labeler/
  cli/              CLI entrypoints
  config/           settings, paths, taxonomy loading
  domain/           data models and scoring types
  services/         application pipeline services
  infrastructure/   filesystem, SQLite, Last.fm, metadata adapters
tests/              automated tests
config/             user-controlled taxonomy and overrides
```
