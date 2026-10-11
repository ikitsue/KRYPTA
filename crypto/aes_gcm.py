"""Enveloppe AES-256-GCM avec dérivation Scrypt et format versionné."""

from __future__ import annotations

import base64
import binascii
import json
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = "CIPHERA1:"
VERSION = 1
SALT_LENGTH = 16
NONCE_LENGTH = 12
KEY_LENGTH = 32
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
MAX_MESSAGE_BYTES = 1_048_576
MAX_ENVELOPE_BYTES = 2_097_152
AAD = b"Ciphera|AES-256-GCM|v1"


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise CipheraCryptoError("Enveloppe chiffrée mal formée.")
        result[name] = value
    return result


class CipheraCryptoError(ValueError):
    """Format, mot de passe ou authentification de chiffrement invalide."""


def _derive_key(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    if not isinstance(password, str) or not password:
        raise CipheraCryptoError("Saisissez le mot de passe de chiffrement.")
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 1024:
        raise CipheraCryptoError("Le mot de passe dépasse la limite de 1 024 octets UTF-8.")
    return Scrypt(salt=salt, length=KEY_LENGTH, n=n, r=r, p=p).derive(password_bytes)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode_b64(value: object, expected_length: int | None = None) -> bytes:
    if not isinstance(value, str) or not value or len(value) > MAX_ENVELOPE_BYTES:
        raise CipheraCryptoError("Enveloppe chiffrée mal formée.")
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as error:
        raise CipheraCryptoError("Enveloppe chiffrée mal formée.") from error
    if expected_length is not None and len(raw) != expected_length:
        raise CipheraCryptoError("Enveloppe chiffrée mal formée.")
    return raw


def encrypt_text(plaintext: str, password: str) -> str:
    if not isinstance(plaintext, str):
        raise CipheraCryptoError("Le texte à chiffrer doit être du texte.")
    raw = plaintext.encode("utf-8")
    if len(raw) > MAX_MESSAGE_BYTES:
        raise CipheraCryptoError("Le texte dépasse la limite de 1 Mio.")
    salt = os.urandom(SALT_LENGTH)
    nonce = os.urandom(NONCE_LENGTH)
    key = _derive_key(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    ciphertext = AESGCM(key).encrypt(nonce, raw, AAD)
    envelope = {
        "v": VERSION,
        "alg": "AES-256-GCM",
        "kdf": "scrypt",
        "n": SCRYPT_N,
        "r": SCRYPT_R,
        "p": SCRYPT_P,
        "salt": _b64(salt),
        "nonce": _b64(nonce),
        "ct": _b64(ciphertext),
    }
    payload = json.dumps(envelope, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return MAGIC + _b64(payload)


def decrypt_text(envelope_text: str, password: str) -> str:
    if not isinstance(envelope_text, str) or len(envelope_text) > MAX_ENVELOPE_BYTES:
        raise CipheraCryptoError("Le message chiffré dépasse la taille autorisée.")
    if not envelope_text.startswith(MAGIC):
        raise CipheraCryptoError("Format de message inconnu ou version non prise en charge.")
    payload = _decode_b64(envelope_text[len(MAGIC) :])
    if len(payload) > MAX_ENVELOPE_BYTES:
        raise CipheraCryptoError("Le message chiffré dépasse la taille autorisée.")
    try:
        data = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CipheraCryptoError("Enveloppe chiffrée mal formée.") from error
    fields = {"v", "alg", "kdf", "n", "r", "p", "salt", "nonce", "ct"}
    if not isinstance(data, dict) or set(data) != fields:
        raise CipheraCryptoError("Enveloppe chiffrée mal formée.")
    if type(data["v"]) is not int or data["v"] != VERSION:
        raise CipheraCryptoError("Version de chiffrement non prise en charge.")
    if data["alg"] != "AES-256-GCM" or data["kdf"] != "scrypt":
        raise CipheraCryptoError("Algorithme ou dérivation non pris en charge.")
    if any(type(data[name]) is not int for name in ("n", "r", "p")) or (
        data["n"], data["r"], data["p"]
    ) != (SCRYPT_N, SCRYPT_R, SCRYPT_P):
        raise CipheraCryptoError("Paramètres Scrypt non pris en charge.")
    salt = _decode_b64(data["salt"], SALT_LENGTH)
    nonce = _decode_b64(data["nonce"], NONCE_LENGTH)
    ciphertext = _decode_b64(data["ct"])
    if len(ciphertext) < 16 or len(ciphertext) > MAX_MESSAGE_BYTES + 16:
        raise CipheraCryptoError("Taille du texte chiffré invalide.")
    key = _derive_key(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, AAD)
        return plaintext.decode("utf-8")
    except (InvalidTag, UnicodeDecodeError) as error:
        raise CipheraCryptoError("Mot de passe incorrect ou message altéré.") from error
