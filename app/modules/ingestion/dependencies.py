from app.core.config import get_settings
from app.modules.ingestion.service import IngestionService


def get_ingestion_service() -> IngestionService:
    settings = get_settings()
    return IngestionService(
        storage_dir=settings.ingestion_dir,
        max_upload_bytes=settings.ingestion_max_upload_bytes,
    )
