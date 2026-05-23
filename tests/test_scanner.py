from __future__ import annotations

from datetime import datetime

import pytest

from mp3_labeler.services.scanner import InboxScanner


def test_scan_returns_album_folders_for_immediate_child_directories_with_mp3s(tmp_path) -> None:
    inbox = tmp_path / "inbox"
    album = inbox / "Artist - Album"
    album.mkdir(parents=True)
    first_track = album / "01 - First.mp3"
    second_track = album / "02 - Second.MP3"
    first_track.write_bytes(b"")
    second_track.write_bytes(b"")

    discovered_at = datetime(2026, 5, 23, 12, 0, 0)
    scanner = InboxScanner(clock=lambda: discovered_at)

    albums = scanner.scan(inbox)

    assert len(albums) == 1
    assert albums[0].path == album
    assert albums[0].audio_files == (first_track, second_track)
    assert albums[0].discovered_at == discovered_at


def test_scan_finds_mp3s_recursively_inside_album_folder(tmp_path) -> None:
    inbox = tmp_path / "inbox"
    disc_one = inbox / "Artist - Album" / "CD1"
    disc_two = inbox / "Artist - Album" / "CD2"
    disc_one.mkdir(parents=True)
    disc_two.mkdir(parents=True)
    first_track = disc_one / "01.mp3"
    second_track = disc_two / "01.mp3"
    first_track.write_bytes(b"")
    second_track.write_bytes(b"")

    albums = InboxScanner().scan(inbox)

    assert len(albums) == 1
    assert albums[0].audio_files == (first_track, second_track)


def test_scan_ignores_root_files_and_child_folders_without_mp3s(tmp_path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "loose-track.mp3").write_bytes(b"")
    no_audio = inbox / "Artwork Only"
    no_audio.mkdir()
    (no_audio / "cover.jpg").write_bytes(b"")

    assert InboxScanner().scan(inbox) == ()


def test_scan_ignores_hidden_and_temporary_album_folders(tmp_path) -> None:
    inbox = tmp_path / "inbox"
    hidden = inbox / ".Hidden Album"
    partial = inbox / "Downloading Album.part"
    temp = inbox / "Temp Album.tmp"
    hidden.mkdir(parents=True)
    partial.mkdir()
    temp.mkdir()
    (hidden / "01.mp3").write_bytes(b"")
    (partial / "01.mp3").write_bytes(b"")
    (temp / "01.mp3").write_bytes(b"")

    assert InboxScanner().scan(inbox) == ()


def test_scan_ignores_audio_files_inside_hidden_or_temporary_subfolders(tmp_path) -> None:
    inbox = tmp_path / "inbox"
    album = inbox / "Artist - Album"
    hidden_disc = album / ".hidden"
    temp_disc = album / "tmp"
    hidden_disc.mkdir(parents=True)
    temp_disc.mkdir()
    (hidden_disc / "01.mp3").write_bytes(b"")
    (temp_disc / "02.mp3").write_bytes(b"")

    assert InboxScanner().scan(inbox) == ()


def test_scan_returns_albums_in_stable_case_insensitive_order(tmp_path) -> None:
    inbox = tmp_path / "inbox"
    z_album = inbox / "zeta"
    a_album = inbox / "Alpha"
    z_album.mkdir(parents=True)
    a_album.mkdir()
    (z_album / "01.mp3").write_bytes(b"")
    (a_album / "01.mp3").write_bytes(b"")

    albums = InboxScanner().scan(inbox)

    assert [album.path.name for album in albums] == ["Alpha", "zeta"]


def test_scan_raises_when_inbox_does_not_exist(tmp_path) -> None:
    scanner = InboxScanner()

    with pytest.raises(FileNotFoundError):
        scanner.scan(tmp_path / "missing")


def test_scan_raises_when_inbox_is_not_a_directory(tmp_path) -> None:
    inbox = tmp_path / "inbox.mp3"
    inbox.write_bytes(b"")

    with pytest.raises(NotADirectoryError):
        InboxScanner().scan(inbox)


def test_scan_can_be_configured_with_additional_supported_extensions(tmp_path) -> None:
    inbox = tmp_path / "inbox"
    album = inbox / "Artist - Album"
    album.mkdir(parents=True)
    flac_track = album / "01.flac"
    flac_track.write_bytes(b"")

    scanner = InboxScanner(supported_extensions=frozenset({".mp3", ".flac"}))

    albums = scanner.scan(inbox)

    assert len(albums) == 1
    assert albums[0].audio_files == (flac_track,)
