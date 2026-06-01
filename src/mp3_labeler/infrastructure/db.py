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

        CREATE TABLE IF NOT EXISTS review_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            album_path TEXT NOT NULL UNIQUE,
            artist TEXT,
            album TEXT,
            year INTEGER,
            existing_genres TEXT NOT NULL DEFAULT '[]',
            matched_taxonomy_node_ids TEXT NOT NULL DEFAULT '[]',
            proposed_node_id TEXT,
            score REAL,
            confidence REAL,
            reason TEXT NOT NULL,
            conflicts TEXT NOT NULL DEFAULT '[]',
            evidence TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'overridden', 'dismissed')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS manual_override (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_type TEXT NOT NULL CHECK (match_type IN ('artist_album', 'folder_hash', 'artist')),
            artist TEXT,
            album TEXT,
            folder_hash TEXT,
            taxonomy_node_id TEXT NOT NULL,
            metadata_corrections TEXT NOT NULL DEFAULT '{}',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS manual_override_artist_album_uq
            ON manual_override (lower(trim(artist)), lower(trim(album)))
            WHERE match_type = 'artist_album';

        CREATE UNIQUE INDEX IF NOT EXISTS manual_override_artist_uq
            ON manual_override (lower(trim(artist)))
            WHERE match_type = 'artist';

        CREATE UNIQUE INDEX IF NOT EXISTS manual_override_folder_hash_uq
            ON manual_override (lower(trim(folder_hash)))
            WHERE match_type = 'folder_hash';

        CREATE TABLE IF NOT EXISTS applied_album_decision (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT NOT NULL,
            destination_path TEXT NOT NULL,
            artist TEXT,
            album TEXT,
            taxonomy_node_id TEXT NOT NULL,
            genres_written TEXT NOT NULL DEFAULT '[]',
            decision_source TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );
        """
    )
    connection.commit()


__all__ = ["initialize_schema", "open_connection"]
