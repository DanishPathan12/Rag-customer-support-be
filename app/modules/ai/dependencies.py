from app.core.config import get_settings
from app.modules.ai.ingestion_service import GeminiChromaIngestionService
from app.modules.ai.rag_service import GeminiRAGService


def get_gemini_chroma_ingestion_service() -> GeminiChromaIngestionService:
    return GeminiChromaIngestionService(get_settings())


def get_gemini_rag_service() -> GeminiRAGService:
    return GeminiRAGService(get_settings())
