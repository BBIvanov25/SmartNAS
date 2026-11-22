import io
import time
import ftplib
import threading
from storage.base import StorageBackend


class FTPStorageBackend(StorageBackend):
    def __init__(self, host: str, port: int, user: str, password: str, base_dir: str = "/"):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.base_dir = "/" + base_dir.strip("/") if base_dir.strip("/") else "/"
        self.lock = threading.Lock()
        self._ftp: ftplib.FTP | None = None
        self._current_dir: str | None = None

    def _new_connection(self) -> ftplib.FTP:
        ftp = ftplib.FTP()
        ftp.encoding = "utf-8"
        ftp.connect(self.host, self.port, timeout=45)
        ftp.login(self.user, self.password)
        ftp.set_pasv(True)
        self._current_dir = "/"
        return ftp

    def _get_ftp(self) -> ftplib.FTP:
        if self._ftp is None:
            self._ftp = self._new_connection()
        return self._ftp

    def _reset_conn(self):
        if self._ftp is not None:
            try:
                self._ftp.close()
            except Exception:
                pass
            self._ftp = None
        self._current_dir = None

    def _full_dir(self, subpath: str = "") -> str:
        clean_sub = subpath.strip("/")
        if self.base_dir == "/":
            return f"/{clean_sub}" if clean_sub else "/"
        return f"{self.base_dir}/{clean_sub}" if clean_sub else self.base_dir

    def _navigate(self, ftp: ftplib.FTP, folder_path: str, create: bool = False):
        norm_target = "/" + folder_path.strip("/") if folder_path.strip("/") else "/"
        if self._current_dir == norm_target:
            return

        ftp.cwd("/")
        self._current_dir = "/"
        for part in norm_target.strip("/").split("/"):
            if not part:
                continue
            try:
                ftp.cwd(part)
            except ftplib.error_perm:
                if create:
                    ftp.mkd(part)
                    ftp.cwd(part)
                else:
                    raise
            self._current_dir = (self._current_dir.rstrip("/") + "/" + part)

    def _parse_list_lines(self, lines: list[str]) -> list[tuple[str, bool, int]]:
        """Return (name, is_dir, size_bytes) entries from a standard FTP LIST."""
        parsed = []
        for line in lines:
            name = ""
            is_dir = False
            size = -1
            if "<DIR>" in line:
                is_dir = True
                name = line.split("<DIR>", 1)[1].strip()
            else:
                parts = line.split(None, 8)
                if len(parts) >= 9:
                    name = parts[8].strip()
                    is_dir = line.startswith("d") or line.startswith("l")
                    if parts[4].isdigit():
                        size = int(parts[4])
            if name and name not in (".", ".."):
                parsed.append((name, is_dir, size))
        return parsed

    def list_items(self, subpath: str = "") -> tuple[list[str], list[str]]:
        with self.lock:
            target = self._full_dir(subpath)
            for attempt in range(3):
                try:
                    ftp = self._get_ftp()
                    self._navigate(ftp, target, create=False)
                    lines: list[str] = []
                    try:
                        ftp.retrlines("LIST", lines.append)
                    except ftplib.error_perm as e:
                        if "550" in str(e):
                            return [], []
                        raise

                    folders, manifests = [], []
                    for name, is_dir, _ in self._parse_list_lines(lines):
                        if name.endswith(".chunks"):
                            continue
                        if is_dir:
                            folders.append(name)
                        elif name.endswith(".manifest.json"):
                            manifests.append(name)

                    return sorted(folders, key=str.lower), sorted(manifests, key=str.lower)
                except Exception:
                    self._reset_conn()
                    if attempt == 2:
                        raise
                    time.sleep(1.5 * (attempt + 1))
            return [], []

    def list_chunk_sizes(self, folder_path: str) -> dict[str, int]:
        """Read all existing .part file sizes with one FTP command."""
        with self.lock:
            target = self._full_dir(folder_path)
            try:
                ftp = self._get_ftp()
                self._navigate(ftp, target, create=False)
                lines: list[str] = []
                ftp.retrlines("LIST", lines.append)
                return {
                    name: size
                    for name, is_dir, size in self._parse_list_lines(lines)
                    if not is_dir and name.endswith(".part")
                }
            except ftplib.error_perm:
                # The folder does not exist yet, so this is a fresh upload.
                return {}
            except Exception:
                self._reset_conn()
                return {}

    def upload_bytes(self, remote_path: str, data: bytes):
        with self.lock:
            full_path = f"{self._full_dir()}/{remote_path.lstrip('/')}".replace("//", "/")
            parts = full_path.strip("/").split("/")
            folder = "/".join(parts[:-1])
            filename = parts[-1]

            # Retry up to four times with an increasing pause so the router can flush its USB cache.
            for attempt in range(4):
                try:
                    ftp = self._get_ftp()
                    self._navigate(ftp, folder, create=True)
                    ftp.storbinary(f"STOR {filename}", io.BytesIO(data), blocksize=65536)
                    return
                except Exception:
                    self._reset_conn()
                    if attempt == 3:
                        raise
                    time.sleep(2.0 * (attempt + 1))

    def download_bytes(self, remote_path: str) -> bytes:
        with self.lock:
            full_path = f"{self._full_dir()}/{remote_path.lstrip('/')}".replace("//", "/")
            parts = full_path.strip("/").split("/")
            folder = "/".join(parts[:-1])
            filename = parts[-1]

            for attempt in range(4):
                try:
                    ftp = self._get_ftp()
                    self._navigate(ftp, folder, create=False)
                    buf = io.BytesIO()
                    ftp.retrbinary(f"RETR {filename}", buf.write, blocksize=65536)
                    return buf.getvalue()
                except Exception:
                    self._reset_conn()
                    if attempt == 3:
                        raise
                    time.sleep(2.0 * (attempt + 1))
            return b""

    def delete_path(self, remote_path: str):
        with self.lock:
            full_path = f"{self._full_dir()}/{remote_path.lstrip('/')}".replace("//", "/")
            for attempt in range(4):
                try:
                    ftp = self._get_ftp()
                    norm_path = "/" + full_path.strip("/")

                    try:
                        ftp.cwd(norm_path)
                        is_dir = True
                    except ftplib.error_perm:
                        is_dir = False

                    if is_dir:
                        self._delete_ftp_directory(ftp, norm_path)
                    else:
                        parts = norm_path.strip("/").split("/")
                        folder = "/" + "/".join(parts[:-1]) if len(parts) > 1 else "/"
                        filename = parts[-1]
                        self._navigate(ftp, folder, create=False)
                        ftp.delete(filename)
                    return
                except ftplib.error_perm as e:
                    if "550" in str(e):
                        raise FileNotFoundError(remote_path)
                    self._reset_conn()
                    if attempt == 3:
                        raise
                    time.sleep(1.5 * (attempt + 1))
                except Exception:
                    self._reset_conn()
                    if attempt == 3:
                        raise
                    time.sleep(1.5 * (attempt + 1))

    def _delete_ftp_directory(self, ftp: ftplib.FTP, folder_path: str):
        self._navigate(ftp, folder_path, create=False)
        lines: list[str] = []
        ftp.retrlines("LIST", lines.append)

        for name, is_dir, _ in self._parse_list_lines(lines):
            if name in (".", ".."):
                continue
            if is_dir:
                self._delete_ftp_directory(ftp, f"{folder_path.rstrip('/')}/{name}")
            else:
                ftp.delete(name)

        ftp.cwd("/")
        self._current_dir = "/"
        parent = folder_path.rstrip("/")
        parts = parent.strip("/").split("/")
        dirname = parts[-1]
        parent_folder = "/" + "/".join(parts[:-1]) if len(parts) > 1 else "/"
        self._navigate(ftp, parent_folder, create=False)
        ftp.rmd(dirname)

    def file_size(self, remote_path: str) -> int:
        with self.lock:
            full_path = f"{self._full_dir()}/{remote_path.lstrip('/')}".replace("//", "/")
            parts = full_path.strip("/").split("/")
            folder = "/".join(parts[:-1])
            filename = parts[-1]
            try:
                ftp = self._get_ftp()
                self._navigate(ftp, folder, create=False)
                ftp.voidcmd("TYPE I")
                sz = ftp.size(filename)
                return sz if sz is not None else -1
            except ftplib.error_perm:
                return -1
            except Exception:
                self._reset_conn()
                return -1