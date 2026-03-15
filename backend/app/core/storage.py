import os
import re
import uuid
import aiofiles
from pathlib import Path
from app.config import settings

# Resolved absolute storage root
_STORAGE_ROOT = Path(settings.storage_path).resolve()


def _safe_subdir(subdir: str) -> Path:
    """
    Resolve subdir relative to storage root and verify it stays within it.
    Raises ValueError on path traversal attempt.
    """
    # Normalize separators and strip leading slashes
    normalized = subdir.replace("\\", "/").lstrip("/")
    # Allow only safe path characters (alphanumeric, -, _, /)
    if not re.match(r"^[a-zA-Z0-9_\-/]+$", normalized):
        raise ValueError(f"Invalid storage subdir: {subdir!r}")
    resolved = (_STORAGE_ROOT / normalized).resolve()
    if not str(resolved).startswith(str(_STORAGE_ROOT)):
        raise ValueError(f"Path traversal in subdir: {subdir!r}")
    return resolved


def _safe_filename(filename: str) -> str:
    """Sanitize a filename — keep only safe characters."""
    # Strip directory components
    name = Path(filename).name
    # Allow alphanumeric, dash, underscore, dot
    safe = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)
    if not safe or safe.startswith("."):
        safe = f"file_{uuid.uuid4()}"
    return safe[:255]


def get_storage_path(subdir: str) -> Path:
    path = _safe_subdir(subdir)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_file(content: bytes, subdir: str, filename: str | None = None) -> tuple[str, str]:
    """Save bytes to storage safely. Returns (file_path, file_name)."""
    dir_path = get_storage_path(subdir)
    if not filename:
        filename = str(uuid.uuid4())
    safe_name = _safe_filename(filename)
    file_path = (dir_path / safe_name).resolve()
    # Final guard: ensure we're still inside storage root
    if not str(file_path).startswith(str(_STORAGE_ROOT)):
        raise ValueError(f"Path traversal in filename: {filename!r}")
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)
    return str(file_path), safe_name


async def read_file(file_path: str) -> bytes:
    resolved = Path(file_path).resolve()
    if not str(resolved).startswith(str(_STORAGE_ROOT)):
        raise ValueError("Path traversal detected in read_file")
    async with aiofiles.open(resolved, "rb") as f:
        return await f.read()


def delete_file(file_path: str) -> None:
    try:
        resolved = Path(file_path).resolve()
        if not str(resolved).startswith(str(_STORAGE_ROOT)):
            raise ValueError("Path traversal detected in delete_file")
        os.remove(resolved)
    except FileNotFoundError:
        pass
