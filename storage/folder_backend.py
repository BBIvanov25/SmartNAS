import os
from storage.base import StorageBackend


class FolderStorageBackend(StorageBackend):
    def __init__(self, root_folder: str):
        self.root_folder = root_folder
        os.makedirs(self.root_folder, exist_ok=True)

    def _full(self, remote_path: str) -> str:
        clean = remote_path.strip("/")
        full = os.path.abspath(
            os.path.join(self.root_folder, *clean.split("/"))
        ) if clean else os.path.abspath(self.root_folder)
        root = os.path.abspath(self.root_folder)
        if os.path.commonpath([root, full]) != root:
            raise ValueError("Invalid storage path")
        return full

    def list_items(self, subpath: str = "") -> tuple[list[str], list[str]]:
        target = self._full(subpath)
        if not os.path.exists(target):
            return [], []
        folders, manifests = [], []
        for entry in os.listdir(target):
            if entry.endswith(".chunks"):
                continue
            full_entry = os.path.join(target, entry)
            if os.path.isdir(full_entry):
                folders.append(entry)
            elif entry.endswith(".manifest.json"):
                manifests.append(entry)
        return sorted(folders, key=str.lower), sorted(manifests, key=str.lower)

    def upload_bytes(self, remote_path: str, data: bytes):
        full = self._full(remote_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(data)

    def download_bytes(self, remote_path: str) -> bytes:
        with open(self._full(remote_path), "rb") as f:
            return f.read()

    def delete_path(self, remote_path: str):
        full = self._full(remote_path)
        if os.path.isdir(full):
            import shutil
            shutil.rmtree(full)
        elif os.path.isfile(full):
            os.remove(full)
        else:
            raise FileNotFoundError(remote_path)

    def file_size(self, remote_path: str) -> int:
        full = self._full(remote_path)
        return os.path.getsize(full) if os.path.exists(full) else -1