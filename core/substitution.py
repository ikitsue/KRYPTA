"""Codage et décodage par substitution avec formats non ambigus."""

from __future__ import annotations

from .models import SubstitutionKey, validate_key

MAX_TRANSFORM_CHARS = 2_097_152


class SubstitutionError(ValueError):
    """Une transformation de substitution ne peut pas être effectuée."""


def _lookup_character(character: str, key: SubstitutionKey) -> str | None:
    if key.case_mode == "sensitive":
        return key.mapping.get(character)
    normalized = character.lower() if key.case_mode == "lower" else character.casefold()
    if len(normalized) == 1:
        return key.mapping.get(normalized)
    return None


def _escape_token(token: str) -> str:
    return token.replace("\\", "\\\\").replace("|", "\\|")


def _split_escaped_tokens(encoded: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    escaped = False
    for character in encoded:
        if escaped:
            if character not in ("\\", "|"):
                raise SubstitutionError("Séquence d’échappement inconnue dans le texte.")
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "|":
            tokens.append("".join(current))
            current.clear()
        else:
            current.append(character)
    if escaped:
        raise SubstitutionError("Séquence d’échappement incomplète dans le texte.")
    tokens.append("".join(current))
    return tokens


def encode_text(
    text: str,
    key: SubstitutionKey,
    *,
    unknown_mode: str | None = None,
) -> str:
    validate_key(key)
    if len(text) > MAX_TRANSFORM_CHARS:
        raise SubstitutionError("Le texte dépasse la limite de traitement de 2 Mio de caractères.")
    behavior = unknown_mode or key.unknown_mode
    if behavior not in ("preserve", "error"):
        raise SubstitutionError("Option pour les caractères inconnus invalide.")
    reverse = {token: character for character, token in key.mapping.items()}
    if key.output_format == "separated" and len(reverse) != len(key.mapping):
        raise SubstitutionError("Cette clé contient des jetons en collision et ne peut pas être décodée.")
    pieces: list[str] = []
    output_length = 0
    for character in text:
        token = _lookup_character(character, key)
        if token is None:
            if behavior == "error":
                raise SubstitutionError(f"La clé ne couvre pas le caractère {character!r}.")
            token = f"~{ord(character):X};"
            marker = "U:"
        else:
            marker = "M:"
        if key.output_format == "separated":
            piece = marker + _escape_token(token)
        else:
            piece = token
        output_length += len(piece) + (1 if pieces and key.output_format == "separated" else 0)
        if output_length > MAX_TRANSFORM_CHARS:
            raise SubstitutionError("Le résultat dépasse la limite de traitement de 2 Mio de caractères.")
        pieces.append(piece)
    return "|".join(pieces) if key.output_format == "separated" else "".join(pieces)


def _decode_unknown_escape(token: str) -> str:
    if not token.startswith("~") or not token.endswith(";"):
        raise SubstitutionError("Jeton inconnu ou mal formé dans le texte.")
    try:
        value = int(token[1:-1], 16)
        if 0xD800 <= value <= 0xDFFF:
            raise ValueError("substitut Unicode isolé")
        return chr(value)
    except (ValueError, OverflowError) as error:
        raise SubstitutionError("Code de caractère échappé invalide.") from error


def decode_text(encoded: str, key: SubstitutionKey) -> str:
    validate_key(key)
    if len(encoded) > MAX_TRANSFORM_CHARS:
        raise SubstitutionError("Le texte dépasse la limite de traitement de 2 Mio de caractères.")
    if not encoded:
        return ""
    reverse: dict[str, str] = {}
    for character, token in key.mapping.items():
        if token in reverse:
            raise SubstitutionError("Cette clé contient des jetons en collision et ne peut pas être décodée.")
        reverse[token] = character

    if key.output_format == "separated":
        result: list[str] = []
        for token in _split_escaped_tokens(encoded):
            if token.startswith("M:"):
                mapped = token[2:]
                if mapped not in reverse:
                    raise SubstitutionError("Jeton absent de la clé sélectionnée.")
                result.append(reverse[mapped])
            elif token.startswith("U:"):
                result.append(_decode_unknown_escape(token[2:]))
            else:
                raise SubstitutionError("Jeton séparé mal formé.")
        return "".join(result)

    result = []
    position = 0
    tokens = list(reverse)
    while position < len(encoded):
        if encoded[position] == "~":
            end = encoded.find(";", position + 1)
            if end < 0:
                raise SubstitutionError("Échappement compact incomplet.")
            result.append(_decode_unknown_escape(encoded[position : end + 1]))
            position = end + 1
            continue
        match = next((token for token in tokens if encoded.startswith(token, position)), None)
        if match is None:
            raise SubstitutionError("Jeton compact absent de la clé sélectionnée.")
        result.append(reverse[match])
        position += len(match)
    return "".join(result)
