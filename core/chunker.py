import os
import math
import time
import hashlib
from typing import Callable, Optional
from core.manifest import FileManifest, inspect_archive_entries
from core.thumbnails import detect_file_category, generate_thumbnail_b64, inspect_media_metadata


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SmartTransferEngine:
    def __init__(self, backend):
        self.backend = backend
        self.cancel_flag = False

    def cancel(self):
        self.cancel_flag = True

    def upload_file(
        self,
        filepath: str,
        chunk_size: int = 1024 * 1024,
        on_progress: Optional[Callable[[float, int, str], None]] = None,
        remote_dir: str = "",
    ) -> FileManifest:
        self.cancel_flag = False
        filename = os.path.basename(filepath)
        total_size = os.path.getsize(filepath)
        total_chunks = max(1, math.ceil(total_size / chunk_size))
        folder_name = f"{filename}.chunks"
        prefix = f"{remote_dir.strip('/')}/" if remote_dir.strip("/") else ""
        remote_chunks_dir = f"{prefix}{folder_name}"

        # One check for auto-resume instead of thousands of SIZE requests.
        existing_chunks = self.backend.list_chunk_sizes(remote_chunks_dir)

        full_hash = hashlib.sha256()
        chunks_meta = []

        with open(filepath, "rb") as f:
            for idx in range(total_chunks):
                if self.cancel_flag:
                    raise InterruptedError("Upload cancelled. Completed parts are kept for auto-resume.")

                chunk = f.read(chunk_size)
                full_hash.update(chunk)
                c_hash = sha256_bytes(chunk)
                chunk_name = f"chunk_{idx:04d}.part"
                remote_path = f"{remote_chunks_dir}/{chunk_name}"

                already_uploaded = (
                    existing_chunks.get(chunk_name) == len(chunk)
                    if existing_chunks
                    else False
                )

                if already_uploaded:
                    rtt_ms = 0
                    status = "Auto-resume (already uploaded)"
                else:
                    t0 = time.time()
                    self.backend.upload_bytes(remote_path, chunk)
                    rtt = time.time() - t0
                    rtt_ms = int(rtt * 1000)

                    # Adaptive backpressure gives the router USB cache time to flush.
                    if rtt > 1.5:
                        pause = min(3.0, rtt * 0.4)
                        status = f"USB flush pause ({int(pause * 1000)} ms)"
                        time.sleep(pause)
                    elif rtt > 0.25:
                        pause = min(1.0, rtt * 0.35)
                        status = f"Backpressure pause ({int(pause * 1000)} ms)"
                        time.sleep(pause)
                    else:
                        status = "Normal transfer"

                chunks_meta.append({"index": idx, "name": chunk_name, "sha256": c_hash})
                if on_progress:
                    on_progress(((idx + 1) / total_chunks) * 100, rtt_ms, status)

        width, height, duration = inspect_media_metadata(filepath)
        manifest = FileManifest(
            original_filename=filename,
            category=detect_file_category(filename),
            total_size=total_size,
            total_sha256=full_hash.hexdigest(),
            chunk_size=chunk_size,
            chunks_folder=folder_name,
            chunks=chunks_meta,
            thumbnail_b64=generate_thumbnail_b64(filepath),
            archive_contents=inspect_archive_entries(filepath),
            width=width,
            height=height,
            duration_seconds=duration,
        )
        self.backend.upload_bytes(f"{prefix}{filename}.manifest.json", manifest.to_bytes())
        return manifest

    def download_and_reassemble(
        self,
        manifest: FileManifest,
        save_path: str,
        on_progress: Optional[Callable[[float, int, str], None]] = None,
        remote_dir: str = "",
    ):
        self.cancel_flag = False
        assembled_hash = hashlib.sha256()
        total = len(manifest.chunks)
        prefix = f"{remote_dir.strip('/')}/" if remote_dir.strip("/") else ""

        with open(save_path, "wb") as out:
            for idx, ch in enumerate(manifest.chunks):
                if self.cancel_flag:
                    raise InterruptedError("Download cancelled.")

                t0 = time.time()
                data = self.backend.download_bytes(f"{prefix}{manifest.chunks_folder}/{ch['name']}")
                rtt_ms = int((time.time() - t0) * 1000)

                if sha256_bytes(data) != ch["sha256"]:
                    raise ValueError(f"Corrupted part {ch['name']} — SHA-256 does not match.")

                out.write(data)
                assembled_hash.update(data)
                if on_progress:
                    on_progress(((idx + 1) / total) * 100, rtt_ms, f"Restoring part {idx + 1}/{total}")

        if assembled_hash.hexdigest() != manifest.total_sha256:
            raise ValueError("The restored file is corrupted.")