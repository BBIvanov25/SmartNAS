import os
import json
import shutil
import time
import threading
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

STORAGE_DIR = "./router_usb_disk"
MAX_RAM_BUFFER = 16 * 1024 * 1024  # 16 MB router limit
USB_WRITE_SPEED = 8 * 1024 * 1024  # 8 MB/s USB disk speed

os.makedirs(STORAGE_DIR, exist_ok=True)
ram_lock = threading.Lock()
current_ram_used = 0

CLIENT_DISCONNECT_ERRORS = (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)


def get_ram_usage_percent() -> float:
    return min(100.0, (current_ram_used / MAX_RAM_BUFFER) * 100.0)


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        pass


class WeakRouterHandler(BaseHTTPRequestHandler):
    def _safe_path(self, url_path: str):
        rel = urllib.parse.unquote(url_path[len("/files/"):]).lstrip("/")
        full = os.path.abspath(os.path.join(STORAGE_DIR, rel))
        return full if full.startswith(os.path.abspath(STORAGE_DIR)) else None

    def _send_bytes(self, status: int, body: bytes, content_type: str = "text/plain", close_conn: bool = False):
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if close_conn:
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        except CLIENT_DISCONNECT_ERRORS:
            pass

    def do_GET(self):
        if self.path == "/list":
            if current_ram_used > MAX_RAM_BUFFER * 0.65:
                time.sleep(3.5)
            files = []
            for root, _, filenames in os.walk(STORAGE_DIR):
                for f in filenames:
                    rel_path = os.path.relpath(os.path.join(root, f), STORAGE_DIR).replace("\\", "/")
                    files.append(rel_path)
            body = json.dumps({"files": files}).encode("utf-8")
            self._send_bytes(200, body, content_type="application/json")
            return

        if self.path.startswith("/files/"):
            fp = self._safe_path(self.path)
            if not fp or not os.path.exists(fp):
                self._send_bytes(404, b"File not found")
                return
            with open(fp, "rb") as f:
                data = f.read()
            self._send_bytes(200, data, content_type="application/octet-stream")
            return

        self._send_bytes(400, b"Bad request")

    def do_PUT(self):
        global current_ram_used
        if not self.path.startswith("/files/"):
            self._send_bytes(400, b"Bad request")
            return

        length = int(self.headers.get("Content-Length", 0))
        fp = self._safe_path(self.path)
        if not fp:
            self._send_bytes(403, b"Invalid path")
            return

        os.makedirs(os.path.dirname(fp), exist_ok=True)

        with ram_lock:
            current_ram_used += length
            overloaded = current_ram_used > MAX_RAM_BUFFER

        try:
            if overloaded:
                read_len = min(length, MAX_RAM_BUFFER // 4)
                corrupted = self.rfile.read(read_len) if read_len > 0 else b""
                with open(fp, "wb") as f:
                    f.write(corrupted)
                time.sleep(0.6)
                self._send_bytes(
                    507,
                    b"507 Router Buffer Overflow - File Corrupted",
                    close_conn=True,
                )
                return

            data = self.rfile.read(length) if length > 0 else b""
            time.sleep(len(data) / USB_WRITE_SPEED)
            with open(fp, "wb") as f:
                f.write(data)
            self._send_bytes(200, b"OK")
        except CLIENT_DISCONNECT_ERRORS:
            pass
        finally:
            with ram_lock:
                current_ram_used = max(0, current_ram_used - length)

    def do_DELETE(self):
        if not self.path.startswith("/files/"):
            self._send_bytes(400, b"Bad request")
            return

        fp = self._safe_path(self.path)
        if not fp:
            self._send_bytes(403, b"Invalid path")
            return
        if not os.path.exists(fp):
            self._send_bytes(404, b"Path not found")
            return

        try:
            if os.path.isdir(fp):
                shutil.rmtree(fp)
            else:
                os.remove(fp)
            self._send_bytes(200, b"OK")
        except Exception as e:
            self._send_bytes(500, str(e).encode("utf-8"))

    def log_message(self, format, *args):
        pass


def start_router_in_background(port: int = 8001):
    try:
        server = QuietThreadingHTTPServer(("127.0.0.1", port), WeakRouterHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server
    except OSError:
        return None


if __name__ == "__main__":
    print("Weak router simulator is running at http://127.0.0.1:8001")
    QuietThreadingHTTPServer(("127.0.0.1", 8001), WeakRouterHandler).serve_forever()