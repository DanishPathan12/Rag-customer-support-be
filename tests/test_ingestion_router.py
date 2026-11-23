import asyncio
from tempfile import SpooledTemporaryFile

from app.main import app
from app.modules.ai.ingestion_service import IngestionResult
from app.modules.ingestion.router import index_ingestion_file, upload_ingestion_file
from app.modules.ingestion.service import IngestionService
from app.modules.users.models import User
from starlette.datastructures import UploadFile
from starlette.requests import Request


def test_admin_upload_runs_the_embedding_pipeline_after_local_save(tmp_path) -> None:
    class FakeAIIngestionService:
        def __init__(self) -> None:
            self.indexed_file_id: str | None = None

        def validate_supported_filename(self, filename: str | None) -> None:
            assert filename == "catalog.txt"

        def ensure_configured(self) -> None:
            return None

        async def index_file(self, stored_file) -> IngestionResult:
            self.indexed_file_id = stored_file.file_id
            assert stored_file.path.read_text(encoding="utf-8") == "catalog contents"
            return IngestionResult(chunks_indexed=3)

    ai_service = FakeAIIngestionService()
    source = SpooledTemporaryFile()
    source.write(b"catalog contents")
    source.seek(0)
    upload = UploadFile(filename="catalog.txt", file=source)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("testserver", 80),
            "path": "/admin/ingestion-files/upload",
            "headers": [],
            "router": app.router,
        }
    )
    response = asyncio.run(
        upload_ingestion_file(
            request=request,
            file=upload,
            _=User(email="admin@example.com", is_admin=True),
            ingestion_service=IngestionService(tmp_path / "ingestion", 1024),
            ai_ingestion_service=ai_service,
        )
    )

    assert response.chunks_indexed == 3
    assert response.embedding_status == "completed"
    assert ai_service.indexed_file_id == response.file_id


def test_admin_can_retry_indexing_a_saved_file(tmp_path) -> None:
    class FakeAIIngestionService:
        def validate_supported_filename(self, filename: str | None) -> None:
            assert filename == "catalog.txt"

        def ensure_configured(self) -> None:
            return None

        async def index_file(self, stored_file) -> IngestionResult:
            assert stored_file.path.read_text(encoding="utf-8") == "catalog contents"
            return IngestionResult(chunks_indexed=2)

    ingestion_service = IngestionService(tmp_path / "ingestion", 1024)
    saved_path = tmp_path / "ingestion" / "123e4567-e89b-12d3-a456-426614174000"
    saved_path.mkdir(parents=True)
    (saved_path / "catalog.txt").write_text("catalog contents", encoding="utf-8")
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("testserver", 80),
            "path": "/admin/ingestion-files/123e4567-e89b-12d3-a456-426614174000/catalog.txt/index",
            "headers": [],
            "router": app.router,
        }
    )

    response = asyncio.run(
        index_ingestion_file(
            request=request,
            file_id="123e4567-e89b-12d3-a456-426614174000",
            filename="catalog.txt",
            _=User(email="admin@example.com", is_admin=True),
            ingestion_service=ingestion_service,
            ai_ingestion_service=FakeAIIngestionService(),
        )
    )

    assert response.chunks_indexed == 2
