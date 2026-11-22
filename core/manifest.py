import os
import json
import zipfile
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any


@dataclass
class FileManifest:
    original_filename: str
    category: str
    total_size: int
    total_sha256: str
    chunk_size: int
    chunks_folder: str
    chunks: List[Dict[str, Any]]
    thumbnail_b64: str = ""
    archive_contents: List[str] = field(default_factory=list)
    width: int = 0
    height: int = 0
    duration_seconds: float = 0.0

    def to_bytes(self) -> bytes:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def from_bytes(raw: bytes) -> "FileManifest":
        data = json.loads(raw.decode("utf-8"))
        return FileManifest(
            original_filename=data["original_filename"],
            category=data.get("category", "document"),
            total_size=data["total_size"],
            total_sha256=data["total_sha256"],
            chunk_size=data["chunk_size"],
            chunks_folder=data["chunks_folder"],
            chunks=data["chunks"],
            thumbnail_b64=data.get("thumbnail_b64", ""),
            archive_contents=data.get("archive_contents") or [],
            width=int(data.get("width", 0) or 0),
            height=int(data.get("height", 0) or 0),
            duration_seconds=float(data.get("duration_seconds", 0) or 0),
        )


def inspect_archive_entries(filepath: str) -> List[str]:
    """Read the file list in a .zip archive without downloading it."""
    if os.path.splitext(filepath)[1].lower() == ".zip" and zipfile.is_zipfile(filepath):
        try:
            with zipfile.ZipFile(filepath, "r") as zf:
                return zf.namelist()[:15]
        except Exception:
            return []
    return []