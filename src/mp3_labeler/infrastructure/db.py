from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection, Row, connect


def open_connection(path: Path) -> Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(path)
    connection.row_factory = Row
    connection.execute("PRAGMA foreign_keys = ON")
    initialize_schema(connection)
    return connection


def initialize_schema(connection: Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS lastfm_album_lookup (
            artist_key TEXT NOT NULL,
            album_key TEXT NOT NULL,
            artist_query TEXT NOT NULL,
            album_query TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('found', 'not_found')),
            fetched_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            PRIMARY KEY (artist_key, album_key)
        );

        CREATE TABLE IF NOT EXISTS lastfm_album_tag (
            artist_key TEXT NOT NULL,
            album_key TEXT NOT NULL,
            position INTEGER NOT NULL,
            tag_name TEXT NOT NULL,
            weight REAL NOT NULL,
            PRIMARY KEY (artist_key, album_key, position),
            FOREIGN KEY (artist_key, album_key)
                REFERENCES lastfm_album_lookup (artist_key, album_key)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS lastfm_artist_lookup (
            artist_key TEXT PRIMARY KEY,
            artist_query TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('found', 'not_found')),
            resolved_name TEXT,
            url TEXT,
            mbid TEXT,
            listeners INTEGER,
            playcount INTEGER,
            similar_artists TEXT NOT NULL DEFAULT '[]',
            fetched_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS lastfm_artist_tag (
            artist_key TEXT NOT NULL,
            position INTEGER NOT NULL,
            tag_name TEXT NOT NULL,
            weight REAL NOT NULL,
            PRIMARY KEY (artist_key, position),
            FOREIGN KEY (artist_key)
                REFERENCES lastfm_artist_lookup (artist_key)
                ON DELETE CASCADE
        );
        """
    )
    connection.commit()


__all__ = ["initialize_schema", "open_connection"]
