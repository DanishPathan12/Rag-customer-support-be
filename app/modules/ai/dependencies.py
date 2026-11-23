from app.core.config import get_settings
from app.modules.ai.ingestion_service import GeminiPineconeIngestionService


def get_gemini_pinecone_ingestion_service() -> GeminiPineconeIngestionService:
    return GeminiPineconeIngestionService(get_settings())
