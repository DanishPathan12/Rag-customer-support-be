from pydantic import BaseModel


class IngestionUploadResponse(BaseModel):
    file_id: str
    filename: str
    file_url: str
    chunks_indexed: int
    embedding_status: str = "completed"
