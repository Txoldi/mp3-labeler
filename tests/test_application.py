from __future__ import annotations

from pathlib import Path

from mutagen.id3 import ID3, TALB, TCON, TPE1, TPE2, TRCK

from mp3_labeler.application import ApplyOptions, LabelerApplication, ScanOptions


def save_track(path: Path) -> None:
    tags = ID3()
    tags.add(TPE1(encoding=3, text=["Track Artist"]))
    tags.add(TPE2(encoding=3, text=["Album Artist"]))
    tags.add(TALB(encoding=3, text=["Album Title"]))
    tags.add(TRCK(encoding=3, text=["1/1"]))
    tags.add(TCON(encoding=3, text=["Death Metal"]))
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


def test_application_scan_returns_analysis_without_cli_output(tmp_path) -> None:
    inbox, taxonomy_path = prepare_inbox(tmp_path)

    result = LabelerApplication().scan(
        ScanOptions(
            inbox=inbox,
            taxonomy_path=taxonomy_path,
            override_path=tmp_path / "overrides.toml",
        )
    )

    assert result.taxonomy.by_id()["death-metal"].name == "Death Metal"
    assert len(result.analyses) == 1
    assert result.analyses[0].metadata.album == "Album Title"
    assert result.analyses[0].proposed_node_id == "death-metal"


def test_application_prepare_apply_builds_reusable_context(tmp_path) -> None:
    inbox, taxonomy_path = prepare_inbox(tmp_path)
    database_path = tmp_path / "data" / "mp3-labeler.sqlite3"

    context = LabelerApplication().prepare_apply(
        ApplyOptions(
            inbox=inbox,
            taxonomy_path=taxonomy_path,
            override_path=tmp_path / "overrides.toml",
            database_path=database_path,
        )
    )

    assert len(context.analyses) == 1
    assert database_path.parent.exists()
    assert context.history.list_applied() == ()
