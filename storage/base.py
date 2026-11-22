class StorageBackend:
    def upload_bytes(self, remote_path: str, data: bytes):
        raise NotImplementedError

    def download_bytes(self, remote_path: str) -> bytes:
        raise NotImplementedError

    def delete_path(self, remote_path: str):
        """Delete a file or recursively delete a folder."""
        raise NotImplementedError

    def list_items(self, subpath: str = "") -> tuple[list[str], list[str]]:
        raise NotImplementedError

    def list_manifests(self, subpath: str = "") -> list[str]:
        _, manifests = self.list_items(subpath)
        return manifests

    def list_chunk_sizes(self, folder_path: str) -> dict[str, int]:
        """Return {chunk_name: size_in_bytes} for auto-resume in one request."""
        return {}

    def file_size(self, remote_path: str) -> int:
        raise NotImplementedError