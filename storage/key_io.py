"""Import/export strict des clés Ciphera au format JSON versionné."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.models import KeyValidationError, SubstitutionKey, validate_key

SCHEMA_VERSION = 1
MAX_IMPORT_BYTES = 1_048_576
ROOT_FIELDS = {"schema_version", "id", "name", "mode", "mapping", "options"}
OPTION_FIELDS = {"case_mode", "output_format", "unknown_mode"}


class KeyFileError(ValueError):
    """Fichier de clé invalide ou non pris en charge."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise KeyFileError("Le fichier JSON contient un champ dupliqué.")
        result[key] = value
    return result


def key_from_json(content: str) -> SubstitutionKey:
    try:
        content_size = len(content.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise KeyFileError("Le fichier contient une séquence Unicode invalide.") from error
    if content_size > MAX_IMPORT_BYTES:
        raise KeyFileError("Le fichier de clé dépasse la taille maximale de 1 Mio.")
    try:
        data = json.loads(content, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeEncodeError) as error:
        raise KeyFileError("Le fichier n’est pas un JSON valide.") from error
    if not isinstance(data, dict) or set(data) != ROOT_FIELDS:
        raise KeyFileError("Le fichier ne correspond pas au schéma Ciphera attendu.")
    if type(data["schema_version"]) is not int or data["schema_version"] != SCHEMA_VERSION:
        raise KeyFileError("Version du fichier de clé non prise en charge.")
    if data["mode"] != "substitution":
        raise KeyFileError("Ce type de clé n’est pas une clé de substitution.")
    if not isinstance(data["options"], dict) or set(data["options"]) != OPTION_FIELDS:
        raise KeyFileError("Options de clé manquantes ou inconnues.")
    if not isinstance(data["mapping"], dict):
        raise KeyFileError("Les correspondances doivent être un objet JSON.")
    try:
        return SubstitutionKey(
            id=data["id"],
            name=data["name"],
            mapping=data["mapping"],
            case_mode=data["options"]["case_mode"],
            output_format=data["options"]["output_format"],
            unknown_mode=data["options"]["unknown_mode"],
        )
    except (KeyValidationError, TypeError) as error:
        raise KeyFileError(str(error)) from error


def key_to_json(key: SubstitutionKey) -> str:
    validate_key(key)
    data = {
        "schema_version": SCHEMA_VERSION,
        "id": key.id,
        "name": key.name,
        "mode": "substitution",
        "mapping": key.mapping,
        "options": {
            "case_mode": key.case_mode,
            "output_format": key.output_format,
            "unknown_mode": key.unknown_mode,
        },
    }
    content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if len(content.encode("utf-8")) > MAX_IMPORT_BYTES:
        raise KeyFileError("Cette clé dépasse la taille maximale de 1 Mio pour un export JSON.")
    return content


def load_key(path: str | Path) -> SubstitutionKey:
    file_path = Path(path)
    try:
        if file_path.stat().st_size > MAX_IMPORT_BYTES:
            raise KeyFileError("Le fichier de clé dépasse la taille maximale de 1 Mio.")
        return key_from_json(file_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise KeyFileError(f"Impossible de lire le fichier de clé : {error}") from error


def save_key(path: str | Path, key: SubstitutionKey) -> None:
    try:
        Path(path).write_text(key_to_json(key), encoding="utf-8")
    except OSError as error:
        raise KeyFileError(f"Impossible d’écrire le fichier de clé : {error}") from error
