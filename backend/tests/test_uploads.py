import pytest

from greenflex.domain import DomainError
from greenflex.services import parse_batch_upload


def test_parse_csv_upload() -> None:
    content = b"client_item_id,prompt,max_output_tokens\nitem-1,hello,64\n"
    items = parse_batch_upload("tasks.csv", content)
    assert items[0].client_item_id == "item-1"
    assert items[0].max_output_tokens == 64


def test_parse_jsonl_upload() -> None:
    content = b'{"client_item_id":"item-1","prompt":"hello"}\n'
    items = parse_batch_upload("tasks.jsonl", content)
    assert len(items) == 1


@pytest.mark.parametrize(
    ("name", "payload", "code"),
    [
        ("tasks.txt", b"hello", "unsupported_file_type"),
        ("tasks.jsonl", b"not-json", "invalid_jsonl"),
        ("tasks.csv", b"wrong,column\n1,2\n", "invalid_upload_schema"),
        ("tasks.csv", b"client_item_id,prompt\n", "empty_upload"),
    ],
)
def test_invalid_uploads_are_rejected(name: str, payload: bytes, code: str) -> None:
    with pytest.raises(DomainError) as error:
        parse_batch_upload(name, payload)
    assert error.value.code == code


def test_duplicate_client_ids_are_rejected() -> None:
    content = b"client_item_id,prompt\nitem-1,one\nitem-1,two\n"
    with pytest.raises(DomainError) as error:
        parse_batch_upload("tasks.csv", content)
    assert error.value.code == "duplicate_client_item_id"
