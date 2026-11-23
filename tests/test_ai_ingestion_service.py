from pathlib import Path

import chromadb
import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.core.exceptions import AIIngestionConfigurationError, AIIngestionRateLimitError
from app.modules.ai.ingestion_service import GeminiChromaIngestionService
from app.modules.ingestion.service import StoredIngestionFile


def make_settings(**overrides) -> Settings:
    values = {
        "database_url": "sqlite://",
        "jwt_secret": "j" * 32,
        "otp_pepper": "p" * 32,
        "google_api_key": "google-api-key",
        "chroma_collection_name": "support-knowledge",
        "ingestion_chunk_size": 12,
        "ingestion_chunk_overlap": 2,
    }
    values.update(overrides)
    return Settings(**values)


def test_supported_file_validation_rejects_unknown_extensions() -> None:
    with pytest.raises(HTTPException) as error:
        GeminiChromaIngestionService.validate_supported_filename("catalog.exe")

    assert error.value.status_code == 415


def test_ingestion_configuration_requires_a_gemini_api_key() -> None:
    service = GeminiChromaIngestionService(make_settings(google_api_key=None))

    with pytest.raises(AIIngestionConfigurationError):
        service.ensure_configured()


def test_chroma_server_client_uses_the_configured_connection(monkeypatch) -> None:
    settings = make_settings(
        chroma_host="chroma.internal",
        chroma_port=8443,
        chroma_ssl=True,
        chroma_tenant="support-team",
        chroma_database="knowledge-base",
    )
    service = GeminiChromaIngestionService(settings)
    client_arguments: dict[str, str | int | bool] = {}

    class FakeCollection:
        metadata = {
            "hnsw:space": "cosine",
            "embedding_model": "gemini-embedding-2",
            "embedding_dimensions": 768,
        }

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            client_arguments.update(kwargs)

        def get_or_create_collection(self, **kwargs) -> FakeCollection:
            assert kwargs["name"] == "support-knowledge"
            return FakeCollection()

    monkeypatch.setattr(chromadb, "HttpClient", FakeClient)

    assert isinstance(service._get_or_create_collection(), FakeCollection)
    assert client_arguments == {
        "host": "chroma.internal",
        "port": 8443,
        "ssl": True,
        "tenant": "support-team",
        "database": "knowledge-base",
    }


def test_settings_accepts_gemini_api_key_alias(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-api-key")

    settings = Settings(
        database_url="sqlite://",
        jwt_secret="j" * 32,
        otp_pepper="p" * 32,
    )

    assert settings.google_api_key is not None
    assert settings.google_api_key.get_secret_value() == "gemini-api-key"


def test_text_file_is_chunked_embedded_and_upserted_to_chroma_without_network(
    tmp_path, monkeypatch
) -> None:
    source_path = tmp_path / "catalog.txt"
    source_path.write_text("alpha beta gamma delta epsilon zeta", encoding="utf-8")
    stored_file = StoredIngestionFile(
        file_id="file-123",
        filename="catalog.txt",
        path=source_path,
    )
    service = GeminiChromaIngestionService(make_settings())

    class FakeEmbeddings:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]

    class FakeChromaCollection:
        def __init__(self) -> None:
            self.upserts: list[dict[str, list]] = []
            self.deleted_filters: list[dict[str, str]] = []

        def delete(self, *, where: dict[str, str]) -> None:
            self.deleted_filters.append(where)

        def upsert(self, **kwargs) -> None:
            self.upserts.append(kwargs)

    fake_collection = FakeChromaCollection()
    monkeypatch.setattr(
        service,
        "_create_embeddings",
        lambda: FakeEmbeddings(),
    )
    monkeypatch.setattr(service, "_get_or_create_collection", lambda: fake_collection)

    result = service._index_file(stored_file)

    indexed_ids = [vector_id for batch in fake_collection.upserts for vector_id in batch["ids"]]
    indexed_metadata = [
        metadata for batch in fake_collection.upserts for metadata in batch["metadatas"]
    ]
    assert result.chunks_indexed == len(indexed_ids)
    assert result.chunks_indexed > 1
    assert fake_collection.deleted_filters == [{"file_id": "file-123"}]
    assert indexed_ids == [
        f"file-123:{number}" for number in range(result.chunks_indexed)
    ]
    assert all(metadata["file_id"] == "file-123" for metadata in indexed_metadata)


def test_failed_upsert_removes_partially_written_file_chunks(tmp_path, monkeypatch) -> None:
    source_path = tmp_path / "catalog.txt"
    source_path.write_text("alpha beta gamma delta epsilon zeta", encoding="utf-8")
    stored_file = StoredIngestionFile(
        file_id="file-123",
        filename="catalog.txt",
        path=source_path,
    )
    service = GeminiChromaIngestionService(make_settings())

    class FakeEmbeddings:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]

    class FailingChromaCollection:
        def __init__(self) -> None:
            self.deleted_filters: list[dict[str, str]] = []

        def delete(self, *, where: dict[str, str]) -> None:
            self.deleted_filters.append(where)

        def upsert(self, **kwargs) -> None:
            raise RuntimeError("storage unavailable")

    collection = FailingChromaCollection()
    monkeypatch.setattr(service, "_create_embeddings", lambda: FakeEmbeddings())
    monkeypatch.setattr(service, "_get_or_create_collection", lambda: collection)

    from app.core.exceptions import AIIngestionError

    with pytest.raises(AIIngestionError):
        service._index_file(stored_file)

    assert collection.deleted_filters == [{"file_id": "file-123"}] * 2


def test_embedding_retries_after_the_gemini_requested_delay(monkeypatch) -> None:
    service = GeminiChromaIngestionService(
        make_settings(
            gemini_embedding_max_retries=1,
            gemini_embedding_min_request_interval_seconds=0,
        )
    )

    class FlakyEmbeddings:
        def __init__(self) -> None:
            self.calls = 0

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError(
                    "429 RESOURCE_EXHAUSTED. Please retry in 21.029415397s."
                )
            return [[0.1, 0.2] for _ in texts]

    delays: list[float] = []
    monkeypatch.setattr(GeminiChromaIngestionService, "_next_embedding_request_at", 0.0)
    monkeypatch.setattr("app.modules.ai.ingestion_service.time.sleep", delays.append)
    embeddings = FlakyEmbeddings()

    assert service._embed_documents(embeddings, ["knowledge-base chunk"]) == [[0.1, 0.2]]
    assert embeddings.calls == 2
    assert delays == [21]


def test_embedding_quota_error_becomes_a_rate_limit_error(monkeypatch) -> None:
    service = GeminiChromaIngestionService(
        make_settings(
            gemini_embedding_max_retries=0,
            gemini_embedding_min_request_interval_seconds=0,
        )
    )

    class RateLimitedEmbeddings:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("429 RESOURCE_EXHAUSTED. Please retry in 21s.")

    monkeypatch.setattr(GeminiChromaIngestionService, "_next_embedding_request_at", 0.0)
    with pytest.raises(AIIngestionRateLimitError) as error:
        service._embed_documents(RateLimitedEmbeddings(), ["knowledge-base chunk"])

    assert error.value.retry_after_seconds == 21
