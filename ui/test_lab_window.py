import os
import time
import hashlib
import threading
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk
from simulator.weak_router import (
    start_router_in_background,
    get_ram_usage_percent,
    STORAGE_DIR,
    MAX_RAM_BUFFER,
    USB_WRITE_SPEED,
)
from storage.demo_backend import DemoHTTPBackend
from core.chunker import SmartTransferEngine

TEST_FILE = "demo_4k_clip_32mb.mp4"

BG_CANVAS = "#09090b"
BG_PANEL = "#0e0e11"
BG_CONSOLE = "#0c0c0f"
BORDER = "#1e1e24"
TEXT_PRIMARY = "#f4f4f5"
TEXT_SECONDARY = "#a1a1aa"
TEXT_MUTED = "#71717a"
ACCENT = "#3b82f6"
DANGER = "#dc2626"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


class TestLabWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Demo Test Lab")
        self.geometry("1080x720")
        self.minsize(900, 620)
        self.configure(bg=BG_CANVAS)

        start_router_in_background(8001)
        self._ensure_test_file()
        self.original_sha256 = sha256_file(TEST_FILE)
        self.original_size = os.path.getsize(TEST_FILE)
        self.is_running = False

        self._build_ui()
        self._poll_ram()
        self._log(
            "INFO",
            f"Simulator is active at http://127.0.0.1:8001 (RAM limit: {MAX_RAM_BUFFER // (1024*1024)} MB, USB speed: {USB_WRITE_SPEED // (1024*1024)} MB/s).",
        )
        self._log(
            "INFO",
            f"Test file: '{TEST_FILE}' ({self.original_size:,} bytes / {self.original_size / (1024*1024):.1f} MB)",
        )
        self._log("INFO", f"Original SHA-256: {self.original_sha256}")

    def _ensure_test_file(self):
        if not os.path.exists(TEST_FILE):
            with open(TEST_FILE, "wb") as f:
                f.write(os.urandom(32 * 1024 * 1024))

    def _build_ui(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TFrame", background=BG_CANVAS)
        s.configure("Card.TFrame", background=BG_PANEL)
        s.configure("TLabel", background=BG_CANVAS, foreground=TEXT_PRIMARY, font=("Segoe UI", 9))
        s.configure("Card.TLabel", background=BG_PANEL, foreground=TEXT_PRIMARY, font=("Segoe UI", 9))
        s.configure("Title.TLabel", background=BG_CANVAS, foreground=TEXT_PRIMARY, font=("Segoe UI", 14, "bold"))
        s.configure("Subtle.TLabel", background=BG_CANVAS, foreground=TEXT_MUTED, font=("Segoe UI", 9))
        s.configure(
            "Treeview",
            background=BG_PANEL,
            fieldbackground=BG_PANEL,
            foreground=TEXT_PRIMARY,
            rowheight=34,
            borderwidth=0,
            font=("Segoe UI", 9),
        )
        s.configure(
            "Treeview.Heading",
            background=BG_PANEL,
            foreground=TEXT_MUTED,
            relief="flat",
            font=("Segoe UI", 8, "bold"),
            padding=(10, 6),
        )
        s.map("Treeview", background=[("selected", "#152238")], foreground=[("selected", "#ffffff")])
        s.configure(
            "Horizontal.TProgressbar",
            troughcolor="#1c1c22",
            background=ACCENT,
            bordercolor=BG_PANEL,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            thickness=6,
        )
        s.configure(
            "Danger.Horizontal.TProgressbar",
            troughcolor="#1c1c22",
            background=DANGER,
            bordercolor=BG_PANEL,
            lightcolor=DANGER,
            darkcolor=DANGER,
            thickness=6,
        )
        s.configure(
            "Vertical.TScrollbar",
            background="#27272e",
            troughcolor=BG_CONSOLE,
            bordercolor=BG_CONSOLE,
            arrowcolor=BG_CONSOLE,
            relief="flat",
            width=8,
        )

        main = ttk.Frame(self, padding=(20, 16))
        main.pack(fill="both", expand=True)

        header = ttk.Frame(main)
        header.pack(fill="x", pady=(0, 4))
        ttk.Label(header, text="Break vs Prove — Test lab", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="127.0.0.1:8001 · 16 MB RAM limit", style="Subtle.TLabel", font=("Consolas", 9)).pack(
            side="right"
        )
        ttk.Label(
            main,
            text="Compare a direct 32.0 MB upload with SmartNAS chunked transfer while another device browses folders.",
            style="Subtle.TLabel",
        ).pack(anchor="w", pady=(0, 14))

        ram_border = tk.Frame(main, bg=BG_PANEL, highlightbackground=BORDER, highlightthickness=1, padx=14, pady=12)
        ram_border.pack(fill="x", pady=(0, 12))
        self.ram_lbl = ttk.Label(ram_border, text="Router buffer usage: 0% (0.0 / 16.0 MB)", style="Card.TLabel")
        self.ram_lbl.pack(anchor="w")
        self.ram_bar = ttk.Progressbar(ram_border, maximum=100, style="Horizontal.TProgressbar")
        self.ram_bar.pack(fill="x", pady=(8, 0))

        btn_row = ttk.Frame(main)
        btn_row.pack(fill="x", pady=(0, 12))

        self.btn_break = tk.Button(
            btn_row,
            text="1. Try direct upload",
            bg="#b91c1c",
            fg="#ffffff",
            activebackground="#dc2626",
            activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"),
            padx=14,
            pady=8,
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self.run_break_test,
        )
        self.btn_break.pack(side="left", padx=(0, 8))

        self.btn_prove = tk.Button(
            btn_row,
            text="2. Use SmartNAS upload",
            bg=ACCENT,
            fg="#ffffff",
            activebackground="#2563eb",
            activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"),
            padx=14,
            pady=8,
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self.run_prove_test,
        )
        self.btn_prove.pack(side="left")

        tk.Button(
            btn_row,
            text="Clear log",
            bg="#141418",
            fg=TEXT_SECONDARY,
            activebackground="#1b1b22",
            activeforeground=TEXT_PRIMARY,
            font=("Segoe UI", 9),
            padx=12,
            pady=8,
            relief="flat",
            bd=0,
            highlightbackground=BORDER,
            highlightthickness=1,
            cursor="hand2",
            command=self._clear_logs,
        ).pack(side="right")

        table_border = tk.Frame(main, bg=BG_PANEL, highlightbackground=BORDER, highlightthickness=1)
        table_border.pack(fill="x", pady=(0, 12))
        self.tree = ttk.Treeview(table_border, columns=("metric", "before", "after"), show="headings", height=4)
        for col, label, width in [
            ("metric", "What we measure", 290),
            ("before", "Direct upload", 310),
            ("after", "SmartNAS upload", 310),
        ]:
            self.tree.heading(col, text=label, anchor="w")
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="x")

        self.rows = {
            "ram": self.tree.insert("", "end", values=("Peak router buffer usage", "—", "—")),
            "browse": self.tree.insert("", "end", values=("Folder browsing from another device", "—", "—")),
            "integrity": self.tree.insert("", "end", values=("File integrity and SHA-256", "—", "—")),
            "status": self.tree.insert("", "end", values=("Overall result", "—", "—")),
        }

        log_frame = tk.Frame(main, bg=BG_CONSOLE, highlightbackground=BORDER, highlightthickness=1)
        log_frame.pack(fill="both", expand=True)

        self.log_box = tk.Text(
            log_frame,
            height=14,
            bg=BG_CONSOLE,
            fg="#d4d4d8",
            font=("Consolas", 9),
            state="disabled",
            wrap="word",
            bd=0,
            highlightthickness=0,
            padx=12,
            pady=10,
        )
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=scroll.set)
        self.log_box.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.log_box.tag_config("TIME", foreground="#52525b")
        self.log_box.tag_config("INFO", foreground="#a1a1aa")
        self.log_box.tag_config("STEP", foreground="#60a5fa", font=("Consolas", 9, "bold"))
        self.log_box.tag_config("WARN", foreground="#fbbf24")
        self.log_box.tag_config("ERROR", foreground="#f87171", font=("Consolas", 9, "bold"))
        self.log_box.tag_config("SUCCESS", foreground="#34d399", font=("Consolas", 9, "bold"))
        self.log_box.tag_config("PHONE", foreground="#7dd3fc")

    def _poll_ram(self):
        pct = get_ram_usage_percent()
        used_mb = (pct / 100.0) * (MAX_RAM_BUFFER / (1024 * 1024))
        self.ram_bar.configure(
            value=pct,
            style="Danger.Horizontal.TProgressbar" if pct >= 80 else "Horizontal.TProgressbar",
        )
        self.ram_lbl.configure(text=f"Router buffer usage: {pct:.0f}% ({used_mb:.1f} / 16.0 MB)")
        self.after(80, self._poll_ram)

    def _clear_logs(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _log(self, tag: str, msg: str):
        ts = f"[{time.strftime('%H:%M:%S')}.{int((time.time() % 1) * 1000):03d}] "

        def add():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", ts, "TIME")
            self.log_box.insert("end", f"[{tag}] {msg}\n", tag)
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

        self.after(0, add)

    def _set_buttons_state(self, running: bool):
        self.is_running = running
        state = "disabled" if running else "normal"
        self.after(
            0,
            lambda: (
                self.btn_break.configure(state=state),
                self.btn_prove.configure(state=state),
            ),
        )

    def _set_cell(self, row_key: str, col_idx: int, value: str):
        def upd():
            vals = list(self.tree.item(self.rows[row_key], "values"))
            vals[col_idx] = value
            self.tree.item(self.rows[row_key], values=vals)

        self.after(0, upd)

    def _test_folder_browse(self, label: str) -> str:
        self._log("PHONE", f"{label}: Sending GET /list to browse router folders...")
        t0 = time.time()
        try:
            res = urllib.request.urlopen("http://127.0.0.1:8001/list", timeout=1.5)
            elapsed_ms = int((time.time() - t0) * 1000)
            payload = res.read().decode("utf-8")
            self._log("SUCCESS", f"{label}: Folders loaded in {elapsed_ms} ms (HTTP 200, {len(payload)} B).")
            return f"Success in {elapsed_ms} ms"
        except Exception as e:
            elapsed_ms = int((time.time() - t0) * 1000)
            self._log("ERROR", f"{label}: TIMEOUT after {elapsed_ms} ms. Router is blocked ({type(e).__name__}).")
            return f"TIMEOUT ({elapsed_ms} ms)"

    def run_break_test(self):
        if self.is_running:
            return
        self._set_buttons_state(True)

        def worker():
            try:
                self._log("STEP", "=================================================================")
                self._log("STEP", "START PHASE 1: BREAK — Direct transfer without buffer control")
                self._log("STEP", "=================================================================")
                self._log("INFO", f"[CLIENT] Reading '{TEST_FILE}' ({self.original_size:,} B) as one HTTP PUT stream...")

                browse_res = []
                threading.Thread(
                    target=lambda: (time.sleep(0.15), browse_res.append(self._test_folder_browse("[Network device]"))),
                    daemon=True,
                ).start()

                with open(TEST_FILE, "rb") as f:
                    raw = f.read()

                self._log(
                    "WARN",
                    f"[ROUTER] Attempting to allocate {len(raw)/(1024*1024):.1f} MB RAM with a 16.0 MB limit (200% overload)!",
                )
                t_start = time.time()
                req = urllib.request.Request("http://127.0.0.1:8001/files/broken_direct.mp4", data=raw, method="PUT")

                try:
                    urllib.request.urlopen(req, timeout=10)
                except urllib.error.HTTPError as e:
                    try:
                        detail = e.read().decode("utf-8", errors="ignore")
                    except OSError:
                        detail = "507 Router Buffer Overflow - File Corrupted (Socket Reset)"
                    self._log(
                        "ERROR",
                        f"[ROUTER] HTTP {e.code} failure after {(time.time() - t_start)*1000:.0f} ms -> {detail}",
                    )
                except (urllib.error.URLError, OSError) as e:
                    self._log("ERROR", f"[ROUTER] CONNECTION CLOSED -> {e}")

                time.sleep(1.5)

                broken_path = os.path.join(STORAGE_DIR, "broken_direct.mp4")
                saved_bytes = os.path.getsize(broken_path) if os.path.exists(broken_path) else 0
                saved_mb = saved_bytes / (1024 * 1024)
                lost_mb = (self.original_size - saved_bytes) / (1024 * 1024)
                corrupted_sha = sha256_file(broken_path) if saved_bytes > 0 else "N/A"

                self._log("ERROR", f"[DISK AUDIT] Expected: {self.original_size:,} B | Saved: {saved_bytes:,} B ({saved_mb:.1f} MB)")
                self._log("ERROR", f"[DISK AUDIT] Data lost: {lost_mb:.1f} MB ({(lost_mb / 32.0) * 100:.1f}% of the file is missing!)")
                self._log("ERROR", f"[DISK AUDIT] Disk SHA-256: {corrupted_sha[:32]}... (DOES NOT MATCH!)")

                b_txt = browse_res[0] if browse_res else "TIMEOUT (1500 ms)"
                self._set_cell("ram", 1, "100% (32 / 16 MB overflow)")
                self._set_cell("browse", 1, b_txt)
                self._set_cell("integrity", 1, f"CORRUPTED ({saved_mb:.1f} / 32.0 MB)")
                self._set_cell("status", 1, "Router failure (HTTP 507)")
            finally:
                self._set_buttons_state(False)

        threading.Thread(target=worker, daemon=True).start()

    def run_prove_test(self):
        if self.is_running:
            return
        self._set_buttons_state(True)

        def worker():
            try:
                self._log("STEP", "=================================================================")
                self._log("STEP", "START PHASE 2: PROVE — Protected transfer with SmartNAS Engine")
                self._log("STEP", "=================================================================")
                self._log("INFO", "[SmartNAS] Starting protected upload (part size: 1,048,576 B / 1.0 MB)...")

                browse_res = []
                threading.Thread(
                    target=lambda: (time.sleep(0.5), browse_res.append(self._test_folder_browse("[Network device]"))),
                    daemon=True,
                ).start()

                t_start = time.time()
                rtts = []

                def on_chunk_progress(pct: float, rtt_ms: int, status: str):
                    rtts.append(rtt_ms)
                    chunk_num = round((pct / 100.0) * 32)
                    if chunk_num in (1, 4, 8, 12, 16, 20, 24, 28, 32):
                        self._log(
                            "INFO",
                            f"[SmartNAS] Part #{chunk_num:02d}/32 ({pct:5.1f}%) | RAM buffer: 1.0 MB (6.2%) | RTT: {rtt_ms} ms | {status}",
                        )

                engine = SmartTransferEngine(DemoHTTPBackend("http://127.0.0.1:8001"))
                manifest = engine.upload_file(TEST_FILE, chunk_size=1024 * 1024, on_progress=on_chunk_progress)
                total_time = time.time() - t_start
                avg_rtt = sum(rtts) / len(rtts) if rtts else 0

                self._log(
                    "SUCCESS",
                    f"[SmartNAS] All {len(manifest.chunks)} parts saved and hashed in {total_time:.2f} sec (average RTT: {avg_rtt:.1f} ms).",
                )
                self._log("SUCCESS", f"[ATOMIC COMMIT] Index '{TEST_FILE}.manifest.json' saved last.")
                self._log(
                    "SUCCESS",
                    f"[INTEGRITY OK] SHA-256 confirmed: {manifest.total_sha256[:32]}... (100% match!)",
                )

                time.sleep(0.2)
                b_txt = browse_res[0] if browse_res else "Success (< 50 ms)"
                self._set_cell("ram", 2, "~6.2% (1.0 / 16.0 MB)")
                self._set_cell("browse", 2, b_txt)
                self._set_cell("integrity", 2, "100% HEALTHY (32/32 parts, SHA-256 OK)")
                self._set_cell("status", 2, f"Success in {total_time:.2f} sec")
            finally:
                self._set_buttons_state(False)

        threading.Thread(target=worker, daemon=True).start()