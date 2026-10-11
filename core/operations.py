"""Orchestration des traitements texte et du mode combiné."""

from __future__ import annotations

from core.models import SubstitutionKey
from core.substitution import decode_text, encode_text
from crypto.aes_gcm import decrypt_text, encrypt_text


def transform(
    text: str,
    operation: str,
    mode: str,
    key: SubstitutionKey | None = None,
    password: str = "",
    combined: bool = False,
) -> str:
    if operation not in ("Coder", "Décoder"):
        raise ValueError("Action inconnue.")
    if mode == "Substitution":
        if key is None:
            raise ValueError("Sélectionnez une clé de substitution.")
        return encode_text(text, key) if operation == "Coder" else decode_text(text, key)
    if mode != "Chiffrement AES-256-GCM":
        raise ValueError("Mode de transformation inconnu.")
    if combined and key is None:
        raise ValueError("Sélectionnez une clé pour la couche de présentation.")
    if operation == "Coder":
        encrypted = encrypt_text(text, password)
        return (
            encode_text(encrypted, key, unknown_mode="error")
            if combined and key is not None
            else encrypted
        )
    envelope = (
        decode_text(text, key)
        if combined and key is not None
        else text
    )
    return decrypt_text(envelope, password)
