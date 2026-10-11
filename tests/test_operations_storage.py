from __future__ import annotations

from core.models import SubstitutionKey
from core.operations import transform
from storage.database import Database


def test_combined_substitution_and_aes_round_trip() -> None:
    mapping = {chr(value): chr(value) for value in range(32, 127)}
    key = SubstitutionKey("ASCII complet", mapping)
    encrypted = transform("Κόσμε 😀", "Coder", "Chiffrement AES-256-GCM", key, "secret", True)
    assert encrypted != "Κόσμε 😀"
    assert transform(encrypted, "Décoder", "Chiffrement AES-256-GCM", key, "secret", True) == "Κόσμε 😀"


def test_combined_substitution_requires_full_envelope_coverage() -> None:
    key = SubstitutionKey("incomplète", {"a": "α"})
    try:
        transform("message", "Coder", "Chiffrement AES-256-GCM", key, "secret", True)
    except ValueError as error:
        assert "ne couvre pas" in str(error)
    else:
        raise AssertionError("La couverture insuffisante aurait dû être refusée.")


def test_history_is_disabled_by_default_and_never_contains_text(tmp_path) -> None:
    database = Database(tmp_path / "ciphera.sqlite3")
    database.add_history("Coder", "Substitution", "Exemple")
    assert database.list_history() == []
    database.set_preference("history_enabled", "true")
    database.add_history("Coder", "Substitution", "Exemple")
    history = database.list_history()
    assert len(history) == 1
    assert set(history[0]) == {"id", "created_at", "operation", "mode", "key_name"}
    database.delete_history_item(history[0]["id"])
    assert database.list_history() == []
    database.add_history("Décoder", "AES-256-GCM")
    database.clear_history()
    assert database.list_history() == []


def test_database_keeps_substitution_keys_and_supports_delete(tmp_path) -> None:
    database = Database(tmp_path / "ciphera.sqlite3")
    key = SubstitutionKey("à sauvegarder", {"a": "α"})
    database.save_key(key)
    assert key in database.list_keys()
    database.delete_key(key.id)
    assert key not in database.list_keys()
