import logging
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.exceptions import AIIngestionConfigurationError, AIIngestionError
from app.modules.ingestion.service import StoredIngestionFile


logger = logging.getLogger(__name__)

SUPPORTED_FILE_EXTENSIONS = frozenset(
    {".csv", ".docx", ".json", ".md", ".markdown", ".pdf", ".txt"}
)


@dataclass(frozen=True)
class IngestionResult:
    chunks_indexed: int


class GeminiPineconeIngestionService:
    """Parse one locally stored document, embed its chunks, and upsert them to Pinecone."""

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
        pinecone_index: Any | None = None
        embeddings: Any | None = None
        vector_ids: list[str] = []
        try:
            documents = self._load_documents(stored_file)
            chunks = self._split_documents(documents, stored_file)
            if not chunks:
                raise ValueError("The document did not contain indexable text.")

            pinecone_index, embeddings = self._create_pinecone_index()
            vector_ids = [f"{stored_file.file_id}:{chunk_number}" for chunk_number in range(len(chunks))]
            self._upsert_chunks(pinecone_index, embeddings, chunks, vector_ids)
            return IngestionResult(chunks_indexed=len(chunks))
        except AIIngestionConfigurationError:
            raise
        except Exception as exc:
            self._delete_partial_vectors(pinecone_index, vector_ids)
            logger.exception("Embedding ingestion failed for file_id=%s", stored_file.file_id)
            raise AIIngestionError from exc

    def _validate_configuration(self) -> None:
        if (
            self.settings.google_api_key is None
            or self.settings.pinecone_api_key is None
            or not self.settings.pinecone_index_name
        ):
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

    def _create_pinecone_index(self) -> tuple[Any, Any]:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        from pinecone.exceptions.exceptions import NotFoundException
        from pinecone import Pinecone

        embeddings = GoogleGenerativeAIEmbeddings(
            model=self.settings.gemini_embedding_model,
            google_api_key=self.settings.google_api_key.get_secret_value(),
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=self.settings.gemini_embedding_dimensions,
        )
        pinecone = Pinecone(api_key=self.settings.pinecone_api_key.get_secret_value())
        try:
            index_description = pinecone.describe_index(self.settings.pinecone_index_name)
        except NotFoundException as exc:
            raise AIIngestionConfigurationError(
                "The configured Pinecone index was not found. Create the index or set "
                "PINECONE_INDEX_NAME to an existing index."
            ) from exc
        if index_description.dimension != self.settings.gemini_embedding_dimensions:
            raise AIIngestionConfigurationError(
                "The configured Pinecone index dimension does not match "
                "GEMINI_EMBEDDING_DIMENSIONS."
            )
        if index_description.metric != self.settings.pinecone_metric:
            raise AIIngestionConfigurationError(
                "The configured Pinecone index metric does not match PINECONE_METRIC."
            )
        return pinecone.Index(host=index_description.host), embeddings

    def _upsert_chunks(
        self, index: Any, embeddings: Any, chunks: list[Any], vector_ids: list[str]
    ) -> None:
        for start in range(0, len(chunks), 50):
            document_batch = chunks[start : start + 50]
            id_batch = vector_ids[start : start + 50]
            vectors_for_batch = embeddings.embed_documents(
                [document.page_content for document in document_batch]
            )
            vectors = [
                {
                    "id": vector_id,
                    "values": embedding,
                    "metadata": {"text": document.page_content, **document.metadata},
                }
                for vector_id, embedding, document in zip(
                    id_batch, vectors_for_batch, document_batch
                )
            ]
            index.upsert(vectors=vectors, namespace=self.settings.pinecone_namespace)

    def _delete_partial_vectors(self, index: Any | None, vector_ids: list[str]) -> None:
        if index is None or not vector_ids:
            return
        try:
            index.delete(ids=vector_ids, namespace=self.settings.pinecone_namespace)
        except Exception:
            logger.exception("Could not roll back partial Pinecone vectors.")
