import asyncio
from tempfile import SpooledTemporaryFile

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.common.dependencies import get_current_admin
from app.modules.ingestion.service import IngestionService
from app.modules.users.models import User


def make_upload(filename: str, contents: bytes) -> UploadFile:
    source = SpooledTemporaryFile()
    source.write(contents)
    source.seek(0)
    return UploadFile(filename=filename, file=source)


def test_ingestion_service_streams_file_to_a_uuid_directory(tmp_path) -> None:
    service = IngestionService(tmp_path / "ingestion", max_upload_bytes=1024)
    upload = make_upload(r"..\catalog.pdf", b"catalog contents")

    stored = asyncio.run(service.save_upload(upload))

    assert stored.filename == "catalog.pdf"
    assert stored.path == tmp_path / "ingestion" / stored.file_id / "catalog.pdf"
    assert stored.path.read_bytes() == b"catalog contents"
    assert service.get_file(stored.file_id, stored.filename) == stored.path
    assert service.get_stored_file(stored.file_id, stored.filename) == stored


def test_ingestion_service_rejects_files_over_the_configured_limit(tmp_path) -> None:
    service = IngestionService(tmp_path / "ingestion", max_upload_bytes=3)
    upload = make_upload("large.txt", b"four")

    with pytest.raises(HTTPException) as error:
        asyncio.run(service.save_upload(upload))

    assert error.value.status_code == 413
    assert list((tmp_path / "ingestion").iterdir()) == []


def test_current_admin_rejects_non_admin_users() -> None:
    with pytest.raises(HTTPException) as error:
        get_current_admin(User(email="customer@example.com", is_admin=False))

    assert error.value.status_code == 403
