from __future__ import annotations

import json

import pytest

from core.models import SubstitutionKey, example_keys
from storage.key_io import KeyFileError, key_from_json, key_to_json


def test_key_json_round_trip() -> None:
    key = example_keys()[0]
    assert key_from_json(key_to_json(key)) == key


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "{}",
        '{"schema_version":true}',
        '{"schema_version":1,"schema_version":1}',
    ],
)
def test_invalid_or_ambiguous_json_is_rejected(content: str) -> None:
    with pytest.raises(KeyFileError):
        key_from_json(content)


def test_unknown_fields_and_invalid_mapping_are_rejected() -> None:
    key = SubstitutionKey("test", {"a": "α"})
    data = json.loads(key_to_json(key))
    data["execute"] = "not run"
    with pytest.raises(KeyFileError, match="schéma"):
        key_from_json(json.dumps(data))
    del data["execute"]
    data["mapping"] = {"ab": "jeton"}
    with pytest.raises(KeyFileError, match="exactement un"):
        key_from_json(json.dumps(data))


def test_import_size_limit_is_enforced() -> None:
    with pytest.raises(KeyFileError, match="1 Mio"):
        key_from_json(" " * (1_048_577))
