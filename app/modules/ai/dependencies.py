from app.core.config import get_settings
from app.modules.ai.ingestion_service import GeminiChromaIngestionService


def get_gemini_chroma_ingestion_service() -> GeminiChromaIngestionService:
    return GeminiChromaIngestionService(get_settings())
