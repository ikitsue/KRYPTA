"""Modèles et validation des clés de substitution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4

CaseMode = Literal["sensitive", "common", "lower"]
OutputFormat = Literal["separated", "compact"]
UnknownMode = Literal["preserve", "error"]

MAX_MAPPINGS = 1024
MAX_TOKEN_LENGTH = 128
MAX_NAME_LENGTH = 120


class KeyValidationError(ValueError):
    """Une clé de substitution ne respecte pas le schéma attendu."""


@dataclass
class SubstitutionKey:
    name: str
    mapping: dict[str, str]
    id: str = field(default_factory=lambda: str(uuid4()))
    case_mode: CaseMode = "sensitive"
    output_format: OutputFormat = "separated"
    unknown_mode: UnknownMode = "preserve"

    def __post_init__(self) -> None:
        validate_key(self)

    @property
    def is_reversible(self) -> bool:
        tokens = list(self.mapping.values())
        return (
            self.case_mode == "sensitive"
            and len(tokens) == len(set(tokens))
            and all(tokens)
        )

    @property
    def case_warning(self) -> str | None:
        if self.case_mode != "sensitive":
            return "La casse est normalisée : le décodage ne peut pas retrouver les majuscules d’origine."
        return None


def validate_key(key: SubstitutionKey) -> None:
    if not isinstance(key.name, str) or not key.name.strip() or len(key.name) > MAX_NAME_LENGTH:
        raise KeyValidationError("Le nom de la clé doit contenir entre 1 et 120 caractères.")
    if not isinstance(key.id, str) or not key.id or len(key.id) > 80:
        raise KeyValidationError("L’identifiant de clé est invalide.")
    if not isinstance(key.mapping, dict) or len(key.mapping) > MAX_MAPPINGS:
        raise KeyValidationError(f"La clé doit contenir au maximum {MAX_MAPPINGS} correspondances.")
    if key.case_mode not in ("sensitive", "common", "lower"):
        raise KeyValidationError("Option de casse inconnue.")
    if key.output_format not in ("separated", "compact"):
        raise KeyValidationError("Format de sortie inconnu.")
    if key.unknown_mode not in ("preserve", "error"):
        raise KeyValidationError("Option pour les caractères inconnus inconnue.")

    for source, token in key.mapping.items():
        if not isinstance(source, str) or len(source) != 1:
            raise KeyValidationError("Chaque caractère d’entrée doit être exactement un caractère Unicode.")
        if 0xD800 <= ord(source) <= 0xDFFF:
            raise KeyValidationError("Les substituts Unicode isolés ne sont pas des caractères valides.")
        if key.case_mode == "common" and (
            len(source.casefold()) != 1 or source != source.casefold()
        ):
            raise KeyValidationError(
                "Avec une correspondance commune, les caractères d’entrée doivent être en minuscules."
            )
        if key.case_mode == "lower" and (len(source.lower()) != 1 or source != source.lower()):
            raise KeyValidationError(
                "Avec une normalisation en minuscules, les caractères d’entrée doivent être en minuscules."
            )
        if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_LENGTH:
            raise KeyValidationError(
                f"Chaque jeton de sortie doit contenir entre 1 et {MAX_TOKEN_LENGTH} caractères."
            )
        if any(0xD800 <= ord(character) <= 0xDFFF for character in token):
            raise KeyValidationError("Les jetons ne peuvent pas contenir de substitut Unicode isolé.")
        if key.output_format == "compact" and token.startswith("~"):
            raise KeyValidationError("En format compact, les jetons ne peuvent pas commencer par « ~ ».")

    if key.output_format == "compact":
        tokens = list(key.mapping.values())
        if len(tokens) != len(set(tokens)):
            raise KeyValidationError("Les jetons compacts doivent être tous distincts.")
        ordered = sorted(tokens)
        if any(right.startswith(left) for left, right in zip(ordered, ordered[1:])):
            raise KeyValidationError(
                "Les jetons compacts doivent former un code préfixe (aucun jeton ne peut en préfixer un autre)."
            )


def example_keys() -> list[SubstitutionKey]:
    latin = "abcdefghijklmnopqrstuvwxyz"
    greek = "αβγδεζηθικλμνξοπρστυφχψω"
    mapping = dict(zip(latin, greek))
    mapping.update({key.upper(): value.upper() for key, value in zip(latin, greek)})
    return [
        SubstitutionKey(
            name="Exemple grec — correspondance illustrative",
            mapping=mapping,
            output_format="separated",
        )
    ]
