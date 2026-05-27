from __future__ import annotations

from pathlib import Path

import pytest
from mutagen.id3 import ID3, TALB, TCON, TPE1, TPE2, TRCK

import mp3_labeler.cli.main as cli
from mp3_labeler.domain.models import (
    ArtistCandidate,
    LastFmAlbumLookupResult,
    LastFmArtistLookupResult,
    LastFmLookupStatus,
    LastFmTag,
)


def save_track(path: Path, *, genre: str = "Death Metal") -> None:
    tags = ID3()
    tags.add(TPE1(encoding=3, text=["Track Artist"]))
    tags.add(TPE2(encoding=3, text=["Album Artist"]))
    tags.add(TALB(encoding=3, text=["Album Title"]))
    tags.add(TRCK(encoding=3, text=["1/1"]))
    tags.add(TCON(encoding=3, text=[genre]))
    tags.save(path)


def save_taxonomy(path: Path) -> None:
    path.write_text(
        """
[[nodes]]
id = "metal"
name = "Metal"
folder_path = "Metal"

[[nodes]]
id = "death-metal"
name = "Death Metal"
parent_id = "metal"
folder_path = "Metal/Death Metal"
positive_tags = ["death metal"]
required_tags = ["death metal"]

[[nodes]]
id = "black-metal"
name = "Black Metal"
parent_id = "metal"
folder_path = "Metal/Black Metal"
positive_tags = ["black metal"]
required_tags = ["black metal"]
""",
        encoding="utf-8",
    )


def prepare_inbox(tmp_path: Path) -> tuple[Path, Path]:
    inbox = tmp_path / "inbox"
    album = inbox / "Album Artist - Album Title"
    album.mkdir(parents=True)
    save_track(album / "01.mp3")
    taxonomy_path = tmp_path / "taxonomy.toml"
    save_taxonomy(taxonomy_path)
    return inbox, taxonomy_path


def save_overrides(path: Path) -> None:
    path.write_text(
        """
[[overrides]]
match_type = "artist_album"
artist = "Album Artist"
album = "Album Title"
taxonomy_node_id = "black-metal"
notes = "Personally verified."

[overrides.metadata_corrections]
genre = "Black Metal"
""",
        encoding="utf-8",
    )


def test_inspect_command_reads_real_id3_tags_and_maps_existing_genre(tmp_path, capsys) -> None:
    inbox, taxonomy_path = prepare_inbox(tmp_path)

    exit_code = cli.main(["inspect", "--inbox", str(inbox), "--taxonomy", str(taxonomy_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Albums found: 1" in output
    assert "Artist: Album Artist" in output
    assert "Album: Album Title" in output
    assert "Existing genres: Death Metal" in output
    assert "Matched taxonomy nodes: death-metal" in output
    assert "Last.fm" not in output
    assert "Proposed node: Death Metal [death-metal]" in output
    assert "Destination folder: Metal/Death Metal" in output
    assert "Decision: eligible for automatic processing" in output


def test_inspect_requires_review_when_only_top_level_local_genre_matches(tmp_path, capsys) -> None:
    inbox, taxonomy_path = prepare_inbox(tmp_path)
    save_track(inbox / "Album Artist - Album Title" / "01.mp3", genre="Metal")

    exit_code = cli.main(["inspect", "--inbox", str(inbox), "--taxonomy", str(taxonomy_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Proposed node: Metal [metal]" in output
    assert "Decision: review required" in output
    assert "broad top-level category" in output


def test_inspect_manual_override_supersedes_local_classification(tmp_path, capsys) -> None:
    inbox, taxonomy_path = prepare_inbox(tmp_path)
    override_path = tmp_path / "overrides.toml"
    save_overrides(override_path)

    exit_code = cli.main(
        [
            "inspect",
            "--inbox",
            str(inbox),
            "--taxonomy",
            str(taxonomy_path),
            "--override",
            str(override_path),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Proposed node: Black Metal [black-metal]" in output
    assert "Destination folder: Metal/Black Metal" in output
    assert "Decision: manual override" in output
    assert "Reason: matched artist_album override" in output
    assert "Notes: Personally verified." in output
    assert "genre: Black Metal" in output


def test_inspect_manual_override_avoids_lastfm_request(tmp_path, monkeypatch, capsys) -> None:
    inbox, taxonomy_path = prepare_inbox(tmp_path)
    override_path = tmp_path / "overrides.toml"
    save_overrides(override_path)
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)

    exit_code = cli.main(
        [
            "inspect",
            "--inbox",
            str(inbox),
            "--taxonomy",
            str(taxonomy_path),
            "--override",
            str(override_path),
            "--lastfm",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Decision: manual override" in output
    assert "Last.fm" not in output


def test_inspect_lastfm_requires_api_key(tmp_path, monkeypatch) -> None:
    inbox, taxonomy_path = prepare_inbox(tmp_path)
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)

    with pytest.raises(SystemExit, match="LASTFM_API_KEY"):
        cli.main(
            [
                "inspect",
                "--inbox",
                str(inbox),
                "--taxonomy",
                str(taxonomy_path),
                "--lastfm",
                "--cache-db",
                str(tmp_path / "cache.sqlite3"),
            ]
        )


def test_inspect_can_show_lastfm_evidence_when_enabled(tmp_path, monkeypatch, capsys) -> None:
    inbox, taxonomy_path = prepare_inbox(tmp_path)
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")

    class FakeClient:
        def __init__(self, api_key: str, api_secret: str | None = None) -> None:
            assert api_key == "test-key"

        def lookup_album(self, artist: str, album: str) -> LastFmAlbumLookupResult:
            return LastFmAlbumLookupResult(
                artist,
                album,
                LastFmLookupStatus.FOUND,
                (LastFmTag(name="death metal", weight=100.0, source="album"),),
            )

        def lookup_artist(self, artist_name: str) -> LastFmArtistLookupResult:
            return LastFmArtistLookupResult(
                artist_name,
                LastFmLookupStatus.FOUND,
                ArtistCandidate(
                    name=artist_name,
                    tags=(LastFmTag(name="metal", weight=75.0, source="artist"),),
                ),
            )

    monkeypatch.setattr(cli, "LastFmClient", FakeClient)

    exit_code = cli.main(
        [
            "inspect",
            "--inbox",
            str(inbox),
            "--taxonomy",
            str(taxonomy_path),
            "--lastfm",
            "--cache-db",
            str(tmp_path / "cache.sqlite3"),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Last.fm tags:" in output
    assert "album: death metal (100)" in output
    assert "artist: metal (75)" in output
    assert "Proposed node: Death Metal [death-metal]" in output
    assert "Decision: eligible for automatic processing" in output


def test_inspect_reports_review_for_conflicting_local_and_lastfm_genres(tmp_path, monkeypatch, capsys) -> None:
    inbox, taxonomy_path = prepare_inbox(tmp_path)
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")

    class FakeClient:
        def __init__(self, api_key: str, api_secret: str | None = None) -> None:
            assert api_key == "test-key"

        def lookup_album(self, artist: str, album: str) -> LastFmAlbumLookupResult:
            return LastFmAlbumLookupResult(
                artist,
                album,
                LastFmLookupStatus.FOUND,
                (LastFmTag(name="black metal", weight=100.0, source="album"),),
            )

        def lookup_artist(self, artist_name: str) -> LastFmArtistLookupResult:
            return LastFmArtistLookupResult(artist_name, LastFmLookupStatus.NOT_FOUND)

    monkeypatch.setattr(cli, "LastFmClient", FakeClient)

    exit_code = cli.main(
        [
            "inspect",
            "--inbox",
            str(inbox),
            "--taxonomy",
            str(taxonomy_path),
            "--lastfm",
            "--cache-db",
            str(tmp_path / "cache.sqlite3"),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Decision: review required" in output
    assert "conflicts with existing MP3 genre" in output


def test_refresh_lastfm_requires_lastfm_flag(tmp_path) -> None:
    inbox, taxonomy_path = prepare_inbox(tmp_path)

    with pytest.raises(SystemExit):
        cli.main(
            [
                "inspect",
                "--inbox",
                str(inbox),
                "--taxonomy",
                str(taxonomy_path),
                "--refresh-lastfm",
            ]
        )
