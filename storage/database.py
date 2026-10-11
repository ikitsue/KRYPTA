"""SQLite local : clés, préférences et historique sans contenu des messages."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.models import SubstitutionKey, example_keys, validate_key


class StorageError(RuntimeError):
    """Erreur de lecture ou d’écriture de la base locale."""


def default_database_path() -> Path:
    root = os.environ.get("APPDATA")
    base = Path(root) if root else Path.home() / "AppData" / "Roaming"
    return base / "Ciphera" / "ciphera.sqlite3"


class Database:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_database_path()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()
        except (OSError, sqlite3.Error) as error:
            raise StorageError(f"Impossible d’initialiser le stockage local : {error}") from error

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS substitution_keys (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    mapping_json TEXT NOT NULL,
                    case_mode TEXT NOT NULL,
                    output_format TEXT NOT NULL,
                    unknown_mode TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS history (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    key_name TEXT NOT NULL
                );
                INSERT OR IGNORE INTO preferences(key, value) VALUES ('history_enabled', 'false');
                """
            )
            count = connection.execute("SELECT COUNT(*) FROM substitution_keys").fetchone()[0]
            if count == 0:
                for key in example_keys():
                    self._insert_key(connection, key)

    @staticmethod
    def _insert_key(connection: sqlite3.Connection, key: SubstitutionKey) -> None:
        connection.execute(
            """INSERT INTO substitution_keys
               (id, name, mapping_json, case_mode, output_format, unknown_mode)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                key.id,
                key.name,
                json.dumps(key.mapping, ensure_ascii=False),
                key.case_mode,
                key.output_format,
                key.unknown_mode,
            ),
        )

    @staticmethod
    def _key_from_row(row: sqlite3.Row) -> SubstitutionKey:
        try:
            return SubstitutionKey(
                id=row["id"],
                name=row["name"],
                mapping=json.loads(row["mapping_json"]),
                case_mode=row["case_mode"],
                output_format=row["output_format"],
                unknown_mode=row["unknown_mode"],
            )
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            raise StorageError("Une clé enregistrée localement est invalide.") from error

    def list_keys(self) -> list[SubstitutionKey]:
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT * FROM substitution_keys ORDER BY name COLLATE NOCASE"
                ).fetchall()
            return [self._key_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise StorageError(f"Impossible de lire les clés locales : {error}") from error

    def save_key(self, key: SubstitutionKey) -> None:
        validate_key(key)
        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO substitution_keys
                       (id, name, mapping_json, case_mode, output_format, unknown_mode)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                       mapping_json=excluded.mapping_json, case_mode=excluded.case_mode,
                       output_format=excluded.output_format, unknown_mode=excluded.unknown_mode""",
                    (
                        key.id,
                        key.name,
                        json.dumps(key.mapping, ensure_ascii=False),
                        key.case_mode,
                        key.output_format,
                        key.unknown_mode,
                    ),
                )
        except sqlite3.Error as error:
            raise StorageError(f"Impossible d’enregistrer la clé : {error}") from error

    def delete_key(self, key_id: str) -> None:
        try:
            with self._connect() as connection:
                connection.execute("DELETE FROM substitution_keys WHERE id = ?", (key_id,))
        except sqlite3.Error as error:
            raise StorageError(f"Impossible de supprimer la clé : {error}") from error

    def get_preference(self, name: str, default: str = "") -> str:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT value FROM preferences WHERE key = ?", (name,)
                ).fetchone()
            return row["value"] if row else default
        except sqlite3.Error as error:
            raise StorageError(f"Impossible de lire les préférences : {error}") from error

    def set_preference(self, name: str, value: str) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO preferences(key, value) VALUES (?, ?)
                       ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                    (name, value),
                )
        except sqlite3.Error as error:
            raise StorageError(f"Impossible d’enregistrer les préférences : {error}") from error

    def add_history(self, operation: str, mode: str, key_name: str = "") -> None:
        if self.get_preference("history_enabled", "false") != "true":
            return
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO history VALUES (?, ?, ?, ?, ?)",
                    (
                        str(uuid4()),
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        operation,
                        mode,
                        key_name,
                    ),
                )
        except sqlite3.Error as error:
            raise StorageError(f"Impossible d’enregistrer l’historique : {error}") from error

    def list_history(self) -> list[dict[str, str]]:
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT id, created_at, operation, mode, key_name FROM history "
                    "ORDER BY created_at DESC"
                ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as error:
            raise StorageError(f"Impossible de lire l’historique : {error}") from error

    def delete_history_item(self, item_id: str) -> None:
        try:
            with self._connect() as connection:
                connection.execute("DELETE FROM history WHERE id = ?", (item_id,))
        except sqlite3.Error as error:
            raise StorageError(f"Impossible de supprimer l’entrée d’historique : {error}") from error

    def clear_history(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute("DELETE FROM history")
        except sqlite3.Error as error:
            raise StorageError(f"Impossible d’effacer l’historique : {error}") from error
