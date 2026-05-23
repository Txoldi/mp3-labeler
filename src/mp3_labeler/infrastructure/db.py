from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection, connect


def open_connection(path: Path) -> Connection:
    return connect(path)

