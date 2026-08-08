import json
import sqlite3
from pathlib import Path
from typing import Any


DB_FILE = Path("chatbois.db")


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_FILE)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    return connection


def load(key: str, default: Any) -> Any:
    with connect() as connection:
        row = connection.execute(
            "SELECT value FROM state WHERE key = ?", (key,)
        ).fetchone()
    return default if row is None else json.loads(row[0])


def save(key: str, value: Any) -> None:
    with connect() as connection:
        connection.execute(
            "INSERT INTO state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )


