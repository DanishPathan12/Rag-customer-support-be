import logging
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar

from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.exceptions import (
    AIIngestionConfigurationError,
    AIIngestionError,
    AIIngestionRateLimitError,
)
from app.modules.ingestion.service import StoredIngestionFile


logger = logging.getLogger(__name__)

SUPPORTED_FILE_EXTENSIONS = frozenset(
    {".csv", ".docx", ".json", ".md", ".markdown", ".pdf", ".txt"}
)


@dataclass(frozen=True)
class IngestionResult:
    chunks_indexed: int


class GeminiChromaIngestionService:
    """Parse a local document, embed its chunks, and store them in ChromaDB."""

    _embedding_rate_limit_lock: ClassVar[threading.Lock] = threading.Lock()
    _next_embedding_request_at: ClassVar[float] = 0.0

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @classmethod
    def validate_supported_filename(cls, filename: str | None) -> None:
        name = PurePosixPath((filename or "").replace("\\", "/")).name
        if Path(name).suffix.lower() not in SUPPORTED_FILE_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_FILE_EXTENSIONS))
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported file type. Supported types: {supported}.",
            )

    async def index_file(self, stored_file: StoredIngestionFile) -> IngestionResult:
        """Run the synchronous LangChain and provider SDK calls off the event loop."""
        return await run_in_threadpool(self._index_file, stored_file)

    def ensure_configured(self) -> None:
        self._validate_configuration()

    def _index_file(self, stored_file: StoredIngestionFile) -> IngestionResult:
        self.ensure_configured()
        collection: Any | None = None
        try:
            documents = self._load_documents(stored_file)
            chunks = self._split_documents(documents, stored_file)
            if not chunks:
                raise ValueError("The document did not contain indexable text.")

            embeddings = self._create_embeddings()
            collection = self._get_or_create_collection()
            self._replace_file_chunks(collection, embeddings, chunks, stored_file.file_id)
            return IngestionResult(chunks_indexed=len(chunks))
        except AIIngestionConfigurationError:
            raise
        except AIIngestionRateLimitError:
            self._delete_file_chunks(collection, stored_file.file_id)
            raise
        except Exception as exc:
            self._delete_file_chunks(collection, stored_file.file_id)
            logger.exception("Embedding ingestion failed for file_id=%s", stored_file.file_id)
            raise AIIngestionError from exc

    def _validate_configuration(self) -> None:
        if self.settings.google_api_key is None or not self.settings.chroma_collection_name:
            raise AIIngestionConfigurationError
        if self.settings.ingestion_chunk_overlap >= self.settings.ingestion_chunk_size:
            raise AIIngestionConfigurationError

    def _load_documents(self, stored_file: StoredIngestionFile) -> list[Any]:
        suffix = stored_file.path.suffix.lower()
        if suffix in {".csv", ".json", ".md", ".markdown", ".txt"}:
            from langchain_core.documents import Document

            return [
                Document(
                    page_content=stored_file.path.read_text(encoding="utf-8"),
                    metadata={},
                )
            ]
        if suffix == ".pdf":
            from langchain_community.document_loaders import PyPDFLoader

            return PyPDFLoader(str(stored_file.path)).load()
        if suffix == ".docx":
            from langchain_community.document_loaders import Docx2txtLoader

            return Docx2txtLoader(str(stored_file.path)).load()
        raise ValueError(f"Unsupported file type: {suffix}")

    def _split_documents(
        self, documents: list[Any], stored_file: StoredIngestionFile
    ) -> list[Any]:
        from langchain_core.documents import Document
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        normalized_documents = []
        for document in documents:
            text = document.page_content.strip()
            if not text:
                continue
            metadata: dict[str, str | int] = {
                "file_id": stored_file.file_id,
                "filename": stored_file.filename,
                "file_type": stored_file.path.suffix.lower().lstrip("."),
            }
            page = document.metadata.get("page")
            if isinstance(page, int):
                metadata["page"] = page + 1
            normalized_documents.append(Document(page_content=text, metadata=metadata))

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.settings.ingestion_chunk_size,
            chunk_overlap=self.settings.ingestion_chunk_overlap,
        )
        chunks = splitter.split_documents(normalized_documents)
        for chunk_number, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = chunk_number
        return chunks

    def _create_embeddings(self) -> Any:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(
            model=self.settings.gemini_embedding_model,
            google_api_key=self.settings.google_api_key.get_secret_value(),
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=self.settings.gemini_embedding_dimensions,
        )

    def _get_or_create_collection(self) -> Any:
        import chromadb

        expected_metadata = {
            "hnsw:space": "cosine",
            "embedding_model": self.settings.gemini_embedding_model,
            "embedding_dimensions": self.settings.gemini_embedding_dimensions,
        }
        try:
            client = chromadb.HttpClient(
                host=self.settings.chroma_host,
                port=self.settings.chroma_port,
                ssl=self.settings.chroma_ssl,
                tenant=self.settings.chroma_tenant,
                database=self.settings.chroma_database,
            )
            collection = client.get_or_create_collection(
                name=self.settings.chroma_collection_name,
                metadata=expected_metadata,
            )
        except Exception as exc:
            raise AIIngestionConfigurationError(
                "Could not connect to ChromaDB. Start the ChromaDB server and verify "
                "CHROMA_HOST, CHROMA_PORT, CHROMA_TENANT, and CHROMA_DATABASE."
            ) from exc
        if any(
            (collection.metadata or {}).get(key) != value
            for key, value in expected_metadata.items()
        ):
            raise AIIngestionConfigurationError(
                "The configured ChromaDB collection uses a different embedding "
                "configuration. Choose a new CHROMA_COLLECTION_NAME or recreate it."
            )
        return collection

    def _replace_file_chunks(
        self, collection: Any, embeddings: Any, chunks: list[Any], file_id: str
    ) -> None:
        """Replace one source file so retries cannot leave stale chunks behind."""
        self._delete_file_chunks(collection, file_id)
        for start in range(0, len(chunks), self.settings.gemini_embedding_batch_size):
            document_batch = chunks[
                start : start + self.settings.gemini_embedding_batch_size
            ]
            id_batch = [
                f"{file_id}:{chunk_number}"
                for chunk_number in range(start, start + len(document_batch))
            ]
            embedding_batch = self._embed_documents(
                embeddings, [document.page_content for document in document_batch]
            )
            if len(embedding_batch) != len(document_batch):
                raise ValueError("The embedding provider returned an unexpected vector count.")
            collection.upsert(
                ids=id_batch,
                embeddings=embedding_batch,
                documents=[document.page_content for document in document_batch],
                metadatas=[document.metadata for document in document_batch],
            )

    def _embed_documents(self, embeddings: Any, texts: list[str]) -> list[list[float]]:
        for attempt in range(self.settings.gemini_embedding_max_retries + 1):
            self._wait_for_embedding_request_slot()
            try:
                return embeddings.embed_documents(texts)
            except Exception as exc:
                retry_after_seconds = self._get_retry_after_seconds(exc)
                if retry_after_seconds is None:
                    raise
                if attempt == self.settings.gemini_embedding_max_retries:
                    raise AIIngestionRateLimitError(retry_after_seconds) from exc
                logger.warning(
                    "Gemini embedding quota reached; retrying in %s seconds "
                    "(attempt %s/%s).",
                    retry_after_seconds,
                    attempt + 1,
                    self.settings.gemini_embedding_max_retries,
                )
                time.sleep(retry_after_seconds)
        raise AssertionError("Embedding retry loop exited unexpectedly.")

    def _wait_for_embedding_request_slot(self) -> None:
        with self._embedding_rate_limit_lock:
            now = time.monotonic()
            wait_seconds = max(0.0, self._next_embedding_request_at - now)
            self.__class__._next_embedding_request_at = max(
                now, self._next_embedding_request_at
            ) + self.settings.gemini_embedding_min_request_interval_seconds
        if wait_seconds:
            time.sleep(wait_seconds)

    @staticmethod
    def _get_retry_after_seconds(exc: Exception) -> int | None:
        message = str(exc)
        if "429" not in message or "RESOURCE_EXHAUSTED" not in message:
            return None
        match = re.search(r"retry(?:Delay| in)[' :]+([0-9.]+)s", message)
        if match is None:
            return 30
        return max(1, round(float(match.group(1))))

    def _delete_file_chunks(self, collection: Any | None, file_id: str) -> None:
        if collection is None:
            return
        try:
            collection.delete(where={"file_id": file_id})
        except Exception:
            logger.exception("Could not clean up ChromaDB chunks for file_id=%s", file_id)
