from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.common.dependencies import get_current_admin
from app.modules.ai.dependencies import get_gemini_chroma_ingestion_service
from app.modules.ai.ingestion_service import GeminiChromaIngestionService
from app.modules.ingestion.dependencies import get_ingestion_service
from app.modules.ingestion.schemas import IngestionUploadResponse
from app.modules.ingestion.service import IngestionService
from app.modules.users.models import User


router = APIRouter(prefix="/admin/ingestion-files", tags=["admin ingestion"])


@router.post(
    "/upload",
    response_model=IngestionUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a knowledge-source file",
    description=(
        "Store an uploaded knowledge source locally, then chunk, embed, and upsert it "
        "to ChromaDB."
    ),
)
async def upload_ingestion_file(
    request: Request,
    file: UploadFile = File(...),
    _: User = Depends(get_current_admin),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    ai_ingestion_service: GeminiChromaIngestionService = Depends(
        get_gemini_chroma_ingestion_service
    ),
) -> IngestionUploadResponse:
    ai_ingestion_service.validate_supported_filename(file.filename)
    ai_ingestion_service.ensure_configured()
    stored_file = await ingestion_service.save_upload(file)
    result = await ai_ingestion_service.index_file(stored_file)
    return IngestionUploadResponse(
        file_id=stored_file.file_id,
        filename=stored_file.filename,
        file_url=str(
            request.url_for(
                "download_ingestion_file",
                file_id=stored_file.file_id,
                filename=stored_file.filename,
            )
        ),
        chunks_indexed=result.chunks_indexed,
    )


@router.get(
    "/{file_id}/{filename}",
    name="download_ingestion_file",
    summary="Download an uploaded knowledge-source file",
)
def download_ingestion_file(
    file_id: UUID,
    filename: str,
    _: User = Depends(get_current_admin),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> FileResponse:
    path = ingestion_service.get_file(str(file_id), filename)
    return FileResponse(path, filename=filename)


@router.post(
    "/{file_id}/{filename}/index",
    response_model=IngestionUploadResponse,
    summary="Retry embedding an uploaded knowledge-source file",
    description="Chunk and upsert an already stored local file after a failed ingestion attempt.",
)
async def index_ingestion_file(
    request: Request,
    file_id: UUID,
    filename: str,
    _: User = Depends(get_current_admin),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    ai_ingestion_service: GeminiChromaIngestionService = Depends(
        get_gemini_chroma_ingestion_service
    ),
) -> IngestionUploadResponse:
    ai_ingestion_service.validate_supported_filename(filename)
    ai_ingestion_service.ensure_configured()
    stored_file = ingestion_service.get_stored_file(str(file_id), filename)
    result = await ai_ingestion_service.index_file(stored_file)
    return IngestionUploadResponse(
        file_id=stored_file.file_id,
        filename=stored_file.filename,
        file_url=str(
            request.url_for(
                "download_ingestion_file",
                file_id=stored_file.file_id,
                filename=stored_file.filename,
            )
        ),
        chunks_indexed=result.chunks_indexed,
    )
