import os
import uuid
import aiofiles
from pathlib import Path
from app.config import settings


def get_storage_path(subdir: str) -> Path:
    path = Path(settings.storage_path) / subdir
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_file(content: bytes, subdir: str, filename: str | None = None) -> tuple[str, str]:
    """Save bytes to storage. Returns (file_path, file_name)."""
    dir_path = get_storage_path(subdir)
    if not filename:
        filename = str(uuid.uuid4())
    file_path = dir_path / filename
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)
    return str(file_path), filename


async def read_file(file_path: str) -> bytes:
    async with aiofiles.open(file_path, "rb") as f:
        return await f.read()


def delete_file(file_path: str) -> None:
    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass
