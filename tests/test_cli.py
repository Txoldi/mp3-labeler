from __future__ import annotations

from pathlib import Path

import pytest
from mutagen.id3 import ID3, TALB, TCON, TPE1, TPE2, TRCK

import mp3_labeler.cli.main as cli
from mp3_labeler.domain.models import ArtistCandidate, LastFmAlbumLookupResult, LastFmArtistLookupResult, LastFmLookupStatus, LastFmTag
from mp3_labeler.infrastructure.db import open_connection
from mp3_labeler.infrastructure.repositories import DecisionRepository
from mp3_labeler.services.override_service import OverrideService


def save_track(
    path: Path,
    *,
    genre: str = "Death Metal",
    album_artist: str = "Album Artist",
    album: str = "Album Title",
) -> None:
    tags = ID3()
    tags.add(TPE1(encoding=3, text=["Track Artist"]))
    tags.add(TPE2(encoding=3, text=[album_artist]))
    tags.add(TALB(encoding=3, text=[album]))
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

[[nodes]]
id = "melodic-black-metal"
name = "Melodic Black Metal"
parent_id = "black-metal"
folder_path = "Metal/Black Metal/Melodic Black Metal"
positive_tags = ["melodic black metal"]
required_tags = ["black metal"]

[[nodes]]
id = "hardcore"
name = "Hardcore"
folder_path = "Hardcore"
positive_tags = ["hardcore"]
""",
        encoding="utf-8",
    )


def prepare_inbox(tmp_path: Path, *, genre: str = "Death Metal") -> tuple[Path, Path, Path]:
    inbox = tmp_path / "inbox"
    album = inbox / "Album Artist - Album Title"
    album.mkdir(parents=True)
    save_track(album / "01.mp3", genre=genre)
    taxonomy_path = tmp_path / "taxonomy.toml"
    save_taxonomy(taxonomy_path)
    return inbox, album, taxonomy_path


def save_override(path: Path, node_id: str = "black-metal") -> None:
    path.write_text(
        f"""
[[overrides]]
match_type = "artist_album"
artist = "Album Artist"
album = "Album Title"
taxonomy_node_id = "{node_id}"
""",
        encoding="utf-8",
    )


def isolated_override_args(tmp_path: Path) -> list[str]:
    return ["--override", str(tmp_path / "overrides.empty.toml")]


def genres(path: Path) -> tuple[str, ...]:
    return tuple(str(value) for value in ID3(path)["TCON"].text)


def test_removed_inspect_and_review_commands_are_not_exposed() -> None:
    with pytest.raises(SystemExit):
        cli.main(["inspect"])
    with pytest.raises(SystemExit):
        cli.main(["review"])


def test_scan_prints_automatic_proposal_without_writing_or_moving(tmp_path, capsys) -> None:
    inbox, album, taxonomy_path = prepare_inbox(tmp_path)
    library = tmp_path / "library"

    assert cli.main(
        [
            "scan",
            "--inbox",
            str(inbox),
            "--library",
            str(library),
            "--taxonomy",
            str(taxonomy_path),
            *isolated_override_args(tmp_path),
        ]
    ) == 0

    output = capsys.readouterr().out
    assert "Mode: scan (read-only)" in output
    assert "Proposed node: Death Metal [death-metal]" in output
    assert "Decision: meets automatic confidence gates" in output
    assert "Proposed genre tags: Death Metal" in output
    assert album.exists()
    assert not library.exists()
    assert genres(album / "01.mp3") == ("Death Metal",)


def test_scan_can_display_lastfm_evidence_without_creating_database(tmp_path, monkeypatch, capsys) -> None:
    inbox, _album, taxonomy_path = prepare_inbox(tmp_path)
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")

    class FakeClient:
        def __init__(self, api_key: str, api_secret: str | None = None) -> None:
            assert api_key == "test-key"

        def lookup_album(self, artist: str, album: str) -> LastFmAlbumLookupResult:
            return LastFmAlbumLookupResult(
                artist, album, LastFmLookupStatus.FOUND, (LastFmTag("death metal", 100, "album"),)
            )

        def lookup_artist(self, artist: str) -> LastFmArtistLookupResult:
            return LastFmArtistLookupResult(
                artist,
                LastFmLookupStatus.FOUND,
                ArtistCandidate(artist, tags=(LastFmTag("metal", 50, "artist"),)),
            )

    monkeypatch.setattr(cli, "LastFmClient", FakeClient)
    assert cli.main(
        [
            "scan",
            "--inbox",
            str(inbox),
            "--library",
            str(tmp_path / "library"),
            "--taxonomy",
            str(taxonomy_path),
            *isolated_override_args(tmp_path),
            "--lastfm",
        ]
    ) == 0

    output = capsys.readouterr().out
    assert "Last.fm tags:" in output
    assert output.index("Inbox:") < output.index("Last.fm tags:")
    assert not (tmp_path / ".mp3-labeler.sqlite3").exists()


def test_apply_prompts_for_automatic_proposal_writes_tags_moves_and_records_history(
    tmp_path, monkeypatch, capsys
) -> None:
    inbox, album, taxonomy_path = prepare_inbox(tmp_path)
    library = tmp_path / "library"
    database = tmp_path / "history.sqlite3"
    destination = library / "Metal" / "Death Metal" / album.name
    answers = iter(("", "n"))
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    assert cli.main(
        [
            "apply",
            "--inbox",
            str(inbox),
            "--library",
            str(library),
            "--taxonomy",
            str(taxonomy_path),
            *isolated_override_args(tmp_path),
            "--db",
            str(database),
        ]
    ) == 0

    output = capsys.readouterr().out
    assert "Moved:" in output
    assert not album.exists()
    assert genres(destination / "01.mp3") == ("Death Metal",)
    recorded = DecisionRepository(open_connection(database)).list_applied()
    assert len(recorded) == 1
    assert recorded[0].taxonomy_node_id == "death-metal"
    assert recorded[0].decision_source == "confirmed_automatic"


def test_apply_accept_automatic_tags_skips_classification_prompt_but_asks_about_permanent_rule(
    tmp_path, monkeypatch
) -> None:
    inbox, album, taxonomy_path = prepare_inbox(tmp_path)
    prompts: list[str] = []

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return "n"

    monkeypatch.setattr("builtins.input", answer)

    assert cli.main(
        [
            "apply",
            "--inbox",
            str(inbox),
            "--library",
            str(tmp_path / "library"),
            "--taxonomy",
            str(taxonomy_path),
            *isolated_override_args(tmp_path),
            "--db",
            str(tmp_path / "history.sqlite3"),
            "--accept-automatic-tags",
        ]
    ) == 0

    assert not album.exists()
    assert prompts == ["Save this classification as a permanent override? [y/N]: "]


def test_apply_review_required_accepts_manual_node_and_saves_permanent_override(
    tmp_path, monkeypatch, capsys
) -> None:
    inbox, album, taxonomy_path = prepare_inbox(tmp_path, genre="Metal")
    library = tmp_path / "library"
    override_path = tmp_path / "overrides.toml"
    monkeypatch.setattr("builtins.input", lambda _prompt: "melodic-black-metal")

    assert cli.main(
        [
            "apply",
            "--inbox",
            str(inbox),
            "--library",
            str(library),
            "--taxonomy",
            str(taxonomy_path),
            "--override",
            str(override_path),
            "--db",
            str(tmp_path / "history.sqlite3"),
            "--genre-depth",
            "2",
            "--save-overrides",
        ]
    ) == 0

    destination = library / "Metal" / "Black Metal" / "Melodic Black Metal" / album.name
    assert genres(destination / "01.mp3") == ("Black Metal", "Melodic Black Metal")
    service = OverrideService.load(override_path, cli.TaxonomyLoader().load(taxonomy_path))
    assert service.overrides[0].taxonomy_node_id == "melodic-black-metal"
    assert "Permanent override saved" in capsys.readouterr().out


def test_apply_prompts_to_save_override_without_flag(tmp_path, monkeypatch) -> None:
    inbox, _album, taxonomy_path = prepare_inbox(tmp_path, genre="Metal")
    override_path = tmp_path / "overrides.toml"
    answers = iter(("black-metal", "y"))
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    assert cli.main(
        [
            "apply",
            "--inbox",
            str(inbox),
            "--library",
            str(tmp_path / "library"),
            "--taxonomy",
            str(taxonomy_path),
            "--override",
            str(override_path),
            "--db",
            str(tmp_path / "history.sqlite3"),
        ]
    ) == 0
    assert OverrideService.load(override_path, cli.TaxonomyLoader().load(taxonomy_path)).overrides


def test_apply_skip_leaves_review_required_album_unchanged(tmp_path, monkeypatch, capsys) -> None:
    inbox, album, taxonomy_path = prepare_inbox(tmp_path, genre="Metal")
    monkeypatch.setattr("builtins.input", lambda _prompt: "s")

    assert cli.main(
        [
            "apply",
            "--inbox",
            str(inbox),
            "--library",
            str(tmp_path / "library"),
            "--taxonomy",
            str(taxonomy_path),
            *isolated_override_args(tmp_path),
            "--db",
            str(tmp_path / "history.sqlite3"),
        ]
    ) == 0

    assert "Action: skipped" in capsys.readouterr().out
    assert album.exists()
    assert genres(album / "01.mp3") == ("Metal",)


def test_apply_uses_existing_permanent_override_without_prompt(tmp_path, monkeypatch) -> None:
    inbox, album, taxonomy_path = prepare_inbox(tmp_path, genre="Metal")
    override_path = tmp_path / "overrides.toml"
    save_override(override_path)
    monkeypatch.setattr("builtins.input", lambda _prompt: pytest.fail("saved override should not prompt"))

    assert cli.main(
        [
            "apply",
            "--inbox",
            str(inbox),
            "--library",
            str(tmp_path / "library"),
            "--taxonomy",
            str(taxonomy_path),
            "--override",
            str(override_path),
            "--db",
            str(tmp_path / "history.sqlite3"),
        ]
    ) == 0

    assert not album.exists()
    assert genres(tmp_path / "library" / "Metal" / "Black Metal" / album.name / "01.mp3") == ("Black Metal",)


def test_apply_blocks_existing_destination_before_writing_metadata(tmp_path, monkeypatch, capsys) -> None:
    inbox, album, taxonomy_path = prepare_inbox(tmp_path)
    library = tmp_path / "library"
    destination = library / "Metal" / "Death Metal" / album.name
    destination.mkdir(parents=True)
    answers = iter(("", "n"))
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    assert cli.main(
        [
            "apply",
            "--inbox",
            str(inbox),
            "--library",
            str(library),
            "--taxonomy",
            str(taxonomy_path),
            *isolated_override_args(tmp_path),
            "--db",
            str(tmp_path / "history.sqlite3"),
        ]
    ) == 1

    assert "Action blocked" in capsys.readouterr().out
    assert album.exists()
    assert genres(album / "01.mp3") == ("Death Metal",)
