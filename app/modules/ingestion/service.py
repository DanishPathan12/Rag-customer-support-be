from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.exceptions import IngestionStorageError


CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class StoredIngestionFile:
    file_id: str
    filename: str
    path: Path


class IngestionService:
    def __init__(self, storage_dir: Path, max_upload_bytes: int) -> None:
        self.storage_dir = storage_dir.resolve()
        self.max_upload_bytes = max_upload_bytes

    async def save_upload(self, upload: UploadFile) -> StoredIngestionFile:
        filename = self._safe_filename(upload.filename)
        file_id = str(uuid4())
        file_dir = self.storage_dir / file_id
        destination = file_dir / filename
        temporary_path = file_dir / ".uploading"
        bytes_written = 0

        try:
            file_dir.mkdir(parents=True, exist_ok=False)
            with temporary_path.open("xb") as destination_file:
                while chunk := await upload.read(CHUNK_SIZE):
                    bytes_written += len(chunk)
                    if bytes_written > self.max_upload_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                            detail=(
                                "The uploaded file exceeds the maximum size of "
                                f"{self.max_upload_bytes} bytes."
                            ),
                        )
                    destination_file.write(chunk)
            temporary_path.replace(destination)
        except HTTPException:
            self._remove_partial_file(file_dir)
            raise
        except OSError as exc:
            self._remove_partial_file(file_dir)
            raise IngestionStorageError from exc

        return StoredIngestionFile(
            file_id=file_id,
            filename=filename,
            path=destination,
        )

    def get_file(self, file_id: str, filename: str) -> Path:
        safe_filename = self._safe_filename(filename)
        if safe_filename != filename:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
        path = self.storage_dir / file_id / safe_filename
        if not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
        return path

    def get_stored_file(self, file_id: str, filename: str) -> StoredIngestionFile:
        return StoredIngestionFile(
            file_id=file_id,
            filename=filename,
            path=self.get_file(file_id, filename),
        )

    @staticmethod
    def _safe_filename(filename: str | None) -> str:
        if not filename or "\x00" in filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A file name is required.")
        safe_filename = PurePosixPath(filename.replace("\\", "/")).name.strip()
        if safe_filename in {"", ".", ".."}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file name.")
        return safe_filename

    @staticmethod
    def _remove_partial_file(file_dir: Path) -> None:
        try:
            for path in file_dir.iterdir():
                path.unlink(missing_ok=True)
            file_dir.rmdir()
        except OSError:
            # The original storage error is more useful to the API client.
            pass
