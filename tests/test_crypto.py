from __future__ import annotations

import base64
import json

import pytest

from crypto.aes_gcm import (
    MAGIC,
    NONCE_LENGTH,
    SALT_LENGTH,
    CipheraCryptoError,
    decrypt_text,
    encrypt_text,
)


def _payload(envelope: str) -> dict[str, object]:
    encoded = envelope.removeprefix(MAGIC)
    raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    return json.loads(raw)


def _envelope(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("ascii")
    return MAGIC + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


@pytest.mark.parametrize("plaintext", ["", "Salut", "Κόσμε 😀\nEspañol"])
def test_aes_gcm_round_trip(plaintext: str) -> None:
    envelope = encrypt_text(plaintext, "mot de passe")
    assert decrypt_text(envelope, "mot de passe") == plaintext


def test_wrong_password_and_tampered_ciphertext_fail_without_plaintext() -> None:
    envelope = encrypt_text("message confidentiel", "correct")
    with pytest.raises(CipheraCryptoError, match="incorrect"):
        decrypt_text(envelope, "incorrect")
    payload = _payload(envelope)
    ciphertext = bytearray(base64.urlsafe_b64decode(str(payload["ct"]) + "=="))
    ciphertext[-1] ^= 1
    payload["ct"] = base64.urlsafe_b64encode(ciphertext).decode("ascii").rstrip("=")
    with pytest.raises(CipheraCryptoError, match="incorrect"):
        decrypt_text(_envelope(payload), "correct")


def test_each_encryption_uses_fresh_random_salt_and_nonce() -> None:
    first = _payload(encrypt_text("same", "password"))
    second = _payload(encrypt_text("same", "password"))
    first_salt = base64.urlsafe_b64decode(str(first["salt"]) + "==")
    second_salt = base64.urlsafe_b64decode(str(second["salt"]) + "==")
    first_nonce = base64.urlsafe_b64decode(str(first["nonce"]) + "==")
    second_nonce = base64.urlsafe_b64decode(str(second["nonce"]) + "==")
    assert len(first_salt) == len(second_salt) == SALT_LENGTH
    assert len(first_nonce) == len(second_nonce) == NONCE_LENGTH
    assert first_salt != second_salt
    assert first_nonce != second_nonce


def test_unsupported_versions_and_kdf_parameters_are_rejected() -> None:
    payload = _payload(encrypt_text("test", "password"))
    payload["v"] = 2
    with pytest.raises(CipheraCryptoError, match="Version"):
        decrypt_text(_envelope(payload), "password")
    payload = _payload(encrypt_text("test", "password"))
    payload["n"] = 2**20
    with pytest.raises(CipheraCryptoError, match="Paramètres Scrypt"):
        decrypt_text(_envelope(payload), "password")


@pytest.mark.parametrize(("field", "value"), [("salt", "AA"), ("nonce", "AA")])
def test_invalid_salt_and_nonce_lengths_are_rejected(field: str, value: str) -> None:
    payload = _payload(encrypt_text("test", "password"))
    payload[field] = value
    with pytest.raises(CipheraCryptoError, match="mal form"):
        decrypt_text(_envelope(payload), "password")


@pytest.mark.parametrize("envelope", ["", "CIPHERA1:@@@", "other:abc", "CIPHERA1:"])
def test_malformed_envelopes_are_rejected(envelope: str) -> None:
    with pytest.raises(CipheraCryptoError):
        decrypt_text(envelope, "password")


def test_duplicate_json_fields_are_rejected() -> None:
    raw = b'{"v":1,"v":1}'
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    with pytest.raises(CipheraCryptoError, match="mal form"):
        decrypt_text(MAGIC + encoded, "password")


def test_password_is_required_and_message_size_is_limited() -> None:
    with pytest.raises(CipheraCryptoError, match="mot de passe"):
        encrypt_text("", "")
    with pytest.raises(CipheraCryptoError, match="1 Mio"):
        encrypt_text("x" * (1_048_576 + 1), "password")
