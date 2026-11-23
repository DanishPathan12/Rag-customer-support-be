from pathlib import Path

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.core.exceptions import AIIngestionConfigurationError
from app.modules.ai.ingestion_service import GeminiPineconeIngestionService
from app.modules.ingestion.service import StoredIngestionFile


def make_settings(**overrides) -> Settings:
    values = {
        "database_url": "sqlite://",
        "jwt_secret": "j" * 32,
        "otp_pepper": "p" * 32,
        "google_api_key": "google-api-key",
        "pinecone_api_key": "pinecone-api-key",
        "pinecone_index_name": "support-index",
        "ingestion_chunk_size": 12,
        "ingestion_chunk_overlap": 2,
    }
    values.update(overrides)
    return Settings(**values)


def test_supported_file_validation_rejects_unknown_extensions() -> None:
    with pytest.raises(HTTPException) as error:
        GeminiPineconeIngestionService.validate_supported_filename("catalog.exe")

    assert error.value.status_code == 415


def test_ingestion_configuration_requires_both_api_keys_and_an_index() -> None:
    service = GeminiPineconeIngestionService(make_settings(google_api_key=None))

    with pytest.raises(AIIngestionConfigurationError):
        service.ensure_configured()


def test_settings_accepts_gemini_api_key_alias(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-api-key")

    settings = Settings(
        database_url="sqlite://",
        jwt_secret="j" * 32,
        otp_pepper="p" * 32,
    )

    assert settings.google_api_key is not None
    assert settings.google_api_key.get_secret_value() == "gemini-api-key"


def test_text_file_is_chunked_embedded_and_upserted_without_network(tmp_path, monkeypatch) -> None:
    source_path = tmp_path / "catalog.txt"
    source_path.write_text("alpha beta gamma delta epsilon zeta", encoding="utf-8")
    stored_file = StoredIngestionFile(
        file_id="file-123",
        filename="catalog.txt",
        path=source_path,
    )
    service = GeminiPineconeIngestionService(make_settings())

    class FakeEmbeddings:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]

    class FakePineconeIndex:
        def __init__(self) -> None:
            self.upserts: list[tuple[list[dict], str]] = []

        def upsert(self, vectors: list[dict], namespace: str) -> None:
            self.upserts.append((vectors, namespace))

    fake_index = FakePineconeIndex()
    monkeypatch.setattr(
        service,
        "_create_pinecone_index",
        lambda: (fake_index, FakeEmbeddings()),
    )

    result = service._index_file(stored_file)

    indexed_vectors = [vector for vectors, _ in fake_index.upserts for vector in vectors]
    assert result.chunks_indexed == len(indexed_vectors)
    assert result.chunks_indexed > 1
    assert {namespace for _, namespace in fake_index.upserts} == {"customer-support"}
    assert [vector["id"] for vector in indexed_vectors] == [
        f"file-123:{number}" for number in range(result.chunks_indexed)
    ]
    assert all(vector["metadata"]["file_id"] == "file-123" for vector in indexed_vectors)
    assert all("text" in vector["metadata"] for vector in indexed_vectors)
