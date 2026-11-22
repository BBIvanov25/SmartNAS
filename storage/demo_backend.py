import json
import urllib.parse
import urllib.request
from storage.base import StorageBackend


class DemoHTTPBackend(StorageBackend):
    def __init__(self, base_url: str = "http://127.0.0.1:8001"):
        self.base_url = base_url.rstrip("/")

    def _file_url(self, remote_path: str) -> str:
        encoded = urllib.parse.quote(remote_path.lstrip("/"), safe="/")
        return f"{self.base_url}/files/{encoded}"

    def list_items(self, subpath: str = "") -> tuple[list[str], list[str]]:
        raw = urllib.request.urlopen(f"{self.base_url}/list", timeout=5).read()
        files = json.loads(raw.decode("utf-8")).get("files", [])
        prefix = f"{subpath.strip('/')}/" if subpath.strip("/") else ""

        folders_set = set()
        manifests = []
        for f in files:
            norm = f.replace("\\", "/").lstrip("/")
            if prefix and not norm.startswith(prefix):
                continue
            rel = norm[len(prefix):]
            if "/" in rel:
                top_folder = rel.split("/", 1)[0]
                if not top_folder.endswith(".chunks"):
                    folders_set.add(top_folder)
            elif rel.endswith(".manifest.json"):
                manifests.append(rel)

        return sorted(folders_set, key=str.lower), sorted(manifests, key=str.lower)

    def upload_bytes(self, remote_path: str, data: bytes):
        req = urllib.request.Request(self._file_url(remote_path), data=data, method="PUT")
        urllib.request.urlopen(req, timeout=15)

    def download_bytes(self, remote_path: str) -> bytes:
        return urllib.request.urlopen(self._file_url(remote_path), timeout=15).read()

    def delete_path(self, remote_path: str):
        req = urllib.request.Request(self._file_url(remote_path), method="DELETE")
        urllib.request.urlopen(req, timeout=15)

    def file_size(self, remote_path: str) -> int:
        try:
            return len(self.download_bytes(remote_path))
        except Exception:
            return -1