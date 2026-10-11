from __future__ import annotations

import pytest

from core.models import KeyValidationError, SubstitutionKey, example_keys
from core.substitution import SubstitutionError, decode_text, encode_text


@pytest.mark.parametrize("output_format", ["separated", "compact"])
def test_example_key_round_trip_unicode_and_unknown_characters(output_format: str) -> None:
    key = example_keys()[0]
    key.output_format = output_format
    if output_format == "compact":
        key.mapping = {character: f"x{index:02d}" for index, character in enumerate(key.mapping)}
    source = "Bonjour, κόσμε !\nÉté 😀 123 | \\"
    assert decode_text(encode_text(source, key), key) == source


def test_empty_text_round_trip() -> None:
    key = example_keys()[0]
    assert encode_text("", key) == ""
    assert decode_text("", key) == ""


def test_case_sensitive_mapping_preserves_upper_and_lowercase() -> None:
    key = SubstitutionKey("casse", {"a": "α", "A": "Α"})
    assert decode_text(encode_text("aA", key), key) == "aA"
    assert key.is_reversible


def test_case_normalization_warns_and_cannot_recover_original_case() -> None:
    key = SubstitutionKey("minuscule", {"a": "α"}, case_mode="lower")
    assert key.case_warning
    assert not key.is_reversible
    assert decode_text(encode_text("Aa", key), key) == "aa"


def test_common_casefold_maps_uppercase_to_shared_mapping() -> None:
    key = SubstitutionKey("commun", {"a": "α"}, case_mode="common")
    assert decode_text(encode_text("Aa", key), key) == "aa"


def test_delimited_tokens_escape_delimiter_and_backslash() -> None:
    key = SubstitutionKey("échappement", {"a": "jet|on\\", "b": "β"})
    assert decode_text(encode_text("ab", key), key) == "ab"


def test_ambiguous_delimited_key_is_refused_for_encoding_and_decoding() -> None:
    key = SubstitutionKey("collision", {"a": "x", "b": "x"})
    assert not key.is_reversible
    with pytest.raises(SubstitutionError, match="collision"):
        encode_text("a", key)
    with pytest.raises(SubstitutionError, match="collision"):
        decode_text("M:x", key)


def test_compact_key_requires_prefix_free_tokens() -> None:
    with pytest.raises(KeyValidationError, match="code préfixe"):
        SubstitutionKey("ambiguë", {"a": "x", "b": "xy"}, output_format="compact")
    with pytest.raises(KeyValidationError, match="distincts"):
        SubstitutionKey("collision", {"a": "x", "b": "x"}, output_format="compact")
    with pytest.raises(KeyValidationError, match="commencer"):
        SubstitutionKey("réservé", {"a": "~x"}, output_format="compact")


def test_compact_decode_rejects_invalid_tokens_and_escapes() -> None:
    key = SubstitutionKey("compacte", {"a": "ab"}, output_format="compact")
    with pytest.raises(SubstitutionError):
        decode_text("ac", key)
    with pytest.raises(SubstitutionError):
        decode_text("~GG;", key)


def test_unknown_mode_error_rejects_unmapped_unicode() -> None:
    key = SubstitutionKey("stricte", {"a": "α"}, unknown_mode="error")
    with pytest.raises(SubstitutionError, match="ne couvre pas"):
        encode_text("a😀", key)


def test_common_mapping_requires_normalized_input_keys() -> None:
    with pytest.raises(KeyValidationError, match="minuscules"):
        SubstitutionKey("casse commune", {"A": "α"}, case_mode="common")


def test_isolated_unicode_surrogates_are_rejected() -> None:
    with pytest.raises(KeyValidationError, match="Unicode"):
        SubstitutionKey("invalide", {"\ud800": "x"})
    key = SubstitutionKey("échappement", {"a": "x"})
    with pytest.raises(SubstitutionError, match="Code de caractère"):
        decode_text("U:~D800;", key)
