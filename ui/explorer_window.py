import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from core.manifest import FileManifest
from core.chunker import SmartTransferEngine
from core.thumbnails import create_tk_preview
from storage.ftp_backend import FTPStorageBackend
from storage.folder_backend import FolderStorageBackend
from core.win_icons import get_windows_icon_ppm, get_windows_folder_icon_ppm

# Minimalist Obsidian Palette
BG_CANVAS = "#09090b"
BG_PANEL = "#0e0e11"
BG_ELEVATED = "#141418"
BG_HOVER = "#1b1b22"
BG_SELECTED = "#152238"
BORDER = "#1e1e24"
TEXT_PRIMARY = "#f4f4f5"
TEXT_SECONDARY = "#a1a1aa"
TEXT_MUTED = "#71717a"
ACCENT = "#3b82f6"
ACCENT_HOVER = "#2563eb"
DANGER_BG = "#261316"
DANGER_FG = "#f87171"


class SmartNASExplorer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SmartNAS Explorer")
        self.geometry("1280x760")
        self.minsize(1000, 620)
        self.configure(bg=BG_CANVAS)

        self.mode = tk.StringVar(value="FOLDER")
        self.current_subpath = ""
        self.address_var = tk.StringVar(value="smb://router_usb_disk/")
        self.search_var = tk.StringVar()
        self.filter_cat = tk.StringVar(value="all")
        self.chunk_kb = tk.IntVar(value=1024)

        self.ftp_host = tk.StringVar(value="192.168.1.1")
        self.ftp_port = tk.StringVar(value="21")
        self.ftp_user = tk.StringVar(value="admin")
        self.ftp_pass = tk.StringVar(value="")
        self.ftp_base = tk.StringVar(value="/")
        self.local_dir = tk.StringVar(value=os.path.abspath("./router_usb_disk"))

        self.folders: list[str] = []
        self.manifests: list[FileManifest] = []
        self.selected_manifest: FileManifest | None = None
        self.thumb_refs = []
        self.engine: SmartTransferEngine | None = None
        self.item_map = {}
        self.tree_icon_refs: list[tk.PhotoImage] = []

        self.source_buttons: dict[str, tuple[tk.Frame, tk.Button, tk.Label]] = {}
        self.filter_buttons: dict[str, tk.Button] = {}
        self.sort_key = "name"
        self.sort_reverse = False

        self._style()
        self._build_layout()
        self._sync_sidebar_states()
        self._clear_details()
        self.bind("<Control-f>", lambda _e: self._focus_search())
        self.bind("<Control-u>", lambda _e: self.upload_dialog())
        self.bind("<F5>", lambda _e: self.refresh_files())
        self.bind("<Escape>", lambda _e: self._clear_search())
        self.bind("<Alt-Up>", lambda _e: self._go_up())
        self.bind("<Delete>", lambda _e: self.delete_selected())
        self.after(200, self.refresh_files)

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        self.option_add("*TCombobox*Listbox*Background", BG_ELEVATED)
        self.option_add("*TCombobox*Listbox*Foreground", TEXT_PRIMARY)
        self.option_add("*TCombobox*Listbox*selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox*selectForeground", "#ffffff")

        s.configure("TFrame", background=BG_CANVAS)
        s.configure("Panel.TFrame", background=BG_PANEL)
        s.configure("Elevated.TFrame", background=BG_ELEVATED)

        s.configure("TLabel", background=BG_CANVAS, foreground=TEXT_PRIMARY, font=("Segoe UI", 9))
        s.configure("Panel.TLabel", background=BG_PANEL, foreground=TEXT_SECONDARY, font=("Segoe UI", 9))
        s.configure("Muted.TLabel", background=BG_PANEL, foreground=TEXT_MUTED, font=("Segoe UI", 8))
        s.configure("Brand.TLabel", background=BG_PANEL, foreground=TEXT_PRIMARY, font=("Segoe UI", 10, "bold"))

        s.configure(
            "TButton",
            background=BG_ELEVATED,
            foreground=TEXT_PRIMARY,
            bordercolor=BORDER,
            lightcolor=BG_ELEVATED,
            darkcolor=BG_ELEVATED,
            focuscolor=BG_ELEVATED,
            relief="flat",
            borderwidth=1,
            font=("Segoe UI", 9),
            padding=(10, 5),
        )
        s.map(
            "TButton",
            background=[("disabled", BG_PANEL), ("active", BG_HOVER)],
            foreground=[("disabled", TEXT_MUTED), ("active", TEXT_PRIMARY)],
            bordercolor=[("active", "#2e2e38")],
        )

        s.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#ffffff",
            bordercolor=ACCENT,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            focuscolor=ACCENT,
            font=("Segoe UI", 9, "bold"),
            padding=(12, 5),
        )
        s.map(
            "Accent.TButton",
            background=[("disabled", "#1e3a5f"), ("active", ACCENT_HOVER)],
            bordercolor=[("active", ACCENT_HOVER)],
        )

        s.configure(
            "Danger.TButton",
            background=DANGER_BG,
            foreground=DANGER_FG,
            bordercolor="#3f1d22",
            lightcolor=DANGER_BG,
            darkcolor=DANGER_BG,
            focuscolor=DANGER_BG,
            padding=(10, 5),
        )
        s.map(
            "Danger.TButton",
            background=[("disabled", BG_PANEL), ("active", "#3b181d")],
            foreground=[("disabled", TEXT_MUTED)],
        )

        s.configure(
            "TEntry",
            fieldbackground=BG_CANVAS,
            foreground=TEXT_PRIMARY,
            insertcolor=TEXT_PRIMARY,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=(8, 5),
        )
        s.map(
            "TEntry",
            fieldbackground=[("readonly", BG_CANVAS)],
            foreground=[("readonly", TEXT_SECONDARY)],
            bordercolor=[("focus", ACCENT)],
        )

        s.configure(
            "TCombobox",
            fieldbackground=BG_ELEVATED,
            background=BG_ELEVATED,
            foreground=TEXT_PRIMARY,
            arrowcolor=TEXT_SECONDARY,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=(6, 4),
        )
        s.map(
            "TCombobox",
            fieldbackground=[("readonly", BG_ELEVATED)],
            selectbackground=[("readonly", BG_ELEVATED)],
            selectforeground=[("readonly", TEXT_PRIMARY)],
            bordercolor=[("focus", ACCENT)],
        )

        s.configure(
            "Treeview",
            background=BG_CANVAS,
            fieldbackground=BG_CANVAS,
            foreground=TEXT_PRIMARY,
            rowheight=36,
            borderwidth=0,
            relief="flat",
            font=("Segoe UI", 9),
        )
        s.configure(
            "Treeview.Heading",
            background=BG_CANVAS,
            foreground=TEXT_MUTED,
            bordercolor=BORDER,
            relief="flat",
            font=("Segoe UI", 8, "bold"),
            padding=(8, 6),
        )
        s.map("Treeview.Heading", background=[("active", BG_PANEL)], foreground=[("active", TEXT_PRIMARY)])
        s.map("Treeview", background=[("selected", BG_SELECTED)], foreground=[("selected", "#ffffff")])

        s.configure(
            "Vertical.TScrollbar",
            background="#27272e",
            troughcolor=BG_CANVAS,
            bordercolor=BG_CANVAS,
            arrowcolor=BG_CANVAS,
            relief="flat",
            width=8,
        )
        s.map("Vertical.TScrollbar", background=[("active", "#3f3f4a")])

        s.configure(
            "Horizontal.TProgressbar",
            troughcolor="#1c1c22",
            background=ACCENT,
            bordercolor=BG_PANEL,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            thickness=5,
        )

    def _hairline(self, parent, orient="horizontal"):
        if orient == "horizontal":
            return tk.Frame(parent, bg=BORDER, height=1)
        return tk.Frame(parent, bg=BORDER, width=1)

    def _build_layout(self):
        # 1. Unified Top Bar
        top_bar = ttk.Frame(self, style="Panel.TFrame", padding=(14, 10))
        top_bar.pack(fill="x")

        ttk.Label(top_bar, text="SmartNAS Explorer", style="Brand.TLabel").pack(side="left", padx=(0, 18))

        self.btn_up = ttk.Button(top_bar, text="↑ Up", command=self._go_up, state="disabled", width=6)
        self.btn_up.pack(side="left", padx=(0, 6))

        addr_entry = ttk.Entry(top_bar, textvariable=self.address_var, state="readonly", font=("Consolas", 9))
        addr_entry.pack(side="left", fill="x", expand=True, padx=(0, 14))

        ttk.Button(top_bar, text="Upload files", style="Accent.TButton", command=self.upload_dialog).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(top_bar, text="Connection", command=self.open_connection_dialog).pack(side="right")

        self._hairline(self).pack(fill="x")

        # 2. Main 3-Pane Body
        body = ttk.Frame(self, style="TFrame")
        body.pack(fill="both", expand=True)

        # Left Sidebar
        sidebar = ttk.Frame(body, style="Panel.TFrame", width=232, padding=(12, 16))
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        ttk.Label(sidebar, text="Storage locations", style="Muted.TLabel").pack(anchor="w", padx=6, pady=(0, 6))
        for label, mode_val, proto in [
            ("Local folder", "FOLDER", "LOCAL"),
            ("Router (FTP)", "FTP", "FTP"),
        ]:
            row = tk.Frame(sidebar, bg=BG_PANEL)
            row.pack(fill="x", pady=1)
            btn = tk.Button(
                row,
                text=label,
                anchor="w",
                bg=BG_PANEL,
                fg=TEXT_SECONDARY,
                activebackground=BG_HOVER,
                activeforeground=TEXT_PRIMARY,
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Segoe UI", 9),
                padx=8,
                pady=6,
                command=lambda m=mode_val: self._switch_source(m),
            )
            btn.pack(side="left", fill="x", expand=True)
            tag = tk.Label(row, text=proto, bg=BG_PANEL, fg=TEXT_MUTED, font=("Consolas", 8), padx=6)
            tag.pack(side="right")
            self.source_buttons[mode_val] = (row, btn, tag)

        ttk.Label(sidebar, text="Filter by file type", style="Muted.TLabel").pack(anchor="w", padx=6, pady=(20, 6))
        for label, cat in [
            ("All items", "all"),
            ("Videos", "video"),
            ("Images", "image"),
            ("Archives (.zip / .rar / .7z)", "archive"),
            ("Documents & other", "document"),
        ]:
            btn = tk.Button(
                sidebar,
                text=label,
                anchor="w",
                bg=BG_PANEL,
                fg=TEXT_SECONDARY,
                activebackground=BG_HOVER,
                activeforeground=TEXT_PRIMARY,
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Segoe UI", 9),
                padx=8,
                pady=6,
                command=lambda c=cat: self._select_category(c),
            )
            btn.pack(fill="x", pady=1)
            self.filter_buttons[cat] = btn

        storage_box = ttk.Frame(sidebar, style="Panel.TFrame")
        storage_box.pack(side="bottom", fill="x", pady=(12, 0))
        self._hairline(storage_box).pack(fill="x", pady=(0, 10))
        self.sidebar_storage = ttk.Label(storage_box, text="", style="Muted.TLabel", justify="left")
        self.sidebar_storage.pack(anchor="w", padx=6)

        self._hairline(body, orient="vertical").pack(side="left", fill="y")

        # Center File Workspace
        center_wrap = ttk.Frame(body, style="TFrame")
        center_wrap.pack(side="left", fill="both", expand=True)

        list_bar = ttk.Frame(center_wrap, style="TFrame", padding=(14, 8))
        list_bar.pack(fill="x")

        ttk.Button(list_bar, text="Download", command=self.download_selected).pack(side="left", padx=(0, 6))
        ttk.Button(list_bar, text="Delete", style="Danger.TButton", command=self.delete_selected).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(list_bar, text="Refresh", command=self.refresh_files).pack(side="left")

        search_entry = ttk.Entry(list_bar, textvariable=self.search_var, width=22)
        search_entry.pack(side="right")
        search_entry.bind("<KeyRelease>", lambda _e: self._render_grid())
        ttk.Label(list_bar, text="Search", foreground=TEXT_MUTED).pack(side="right", padx=(12, 6))
        ttk.Button(list_bar, text="×", width=2, command=self._clear_search).pack(side="right", padx=(4, 0))
        self.search_entry = search_entry

        chunk_box = ttk.Combobox(list_bar, values=["512 KB", "1024 KB", "2048 KB"], width=9, state="readonly")
        chunk_box.current(1)
        chunk_box.bind("<<ComboboxSelected>>", lambda _e: self.chunk_kb.set(int(chunk_box.get().split()[0])))
        chunk_box.pack(side="right")
        ttk.Label(list_bar, text="Part size", foreground=TEXT_MUTED).pack(side="right", padx=(0, 6))

        self._hairline(center_wrap).pack(fill="x")

        table_frame = ttk.Frame(center_wrap, style="TFrame")
        table_frame.pack(fill="both", expand=True)

        columns = ("type", "parts", "size")
        self.file_tree = ttk.Treeview(
            table_frame, columns=columns, show=("tree", "headings"), selectmode="browse"
        )
        self.file_tree.heading("#0", text="Name", anchor="w", command=lambda: self._sort_grid("name"))
        self.file_tree.column("#0", width=340, anchor="w", stretch=True)
        for col, title, width, anchor in [
            ("type", "Type", 90, "w"),
            ("parts", "Parts", 110, "e"),
            ("size", "Size", 95, "e"),
        ]:
            self.file_tree.heading(col, text=title, anchor=anchor, command=lambda c=col: self._sort_grid(c))
            self.file_tree.column(col, width=width, anchor=anchor)

        self.file_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.file_tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=self._on_tree_scroll)
        self.file_tree.pack(side="left", fill="both", expand=True, padx=(6, 0))
        self.tree_scrollbar.pack_forget()

        self._hairline(body, orient="vertical").pack(side="right", fill="y")

        # Right details pane
        details = ttk.Frame(body, style="Panel.TFrame", width=320, padding=(14, 14))
        details.pack(side="right", fill="y")
        details.pack_propagate(False)

        self.preview_border = tk.Frame(
            details,
            bg=BG_ELEVATED,
            width=292,
            height=176,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self.preview_border.pack(fill="x", pady=(0, 12))
        self.preview_border.pack_propagate(False)
        self.preview_label = tk.Label(
            self.preview_border,
            text="Pick an item for more details",
            bg=BG_ELEVATED,
            fg=TEXT_MUTED,
            font=("Segoe UI", 9),
        )
        self.preview_label.pack(fill="both", expand=True)

        self.detail_name = ttk.Label(details, text="", style="Panel.TLabel", wraplength=288)
        self.detail_name.pack(anchor="w", pady=(0, 10))

        self.detail_rows: dict[str, ttk.Label] = {}
        self.detail_row_widgets: dict[str, ttk.Frame] = {}
        for key, label in [
            ("type", "Type"),
            ("size", "Size"),
            ("dimensions", "Dimensions"),
            ("duration", "Duration"),
            ("chunks", "Chunks"),
            ("category", "Category"),
            ("location", "Location"),
            ("sha256", "SHA-256"),
        ]:
            row = ttk.Frame(details, style="Panel.TFrame")
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, style="Muted.TLabel", width=11).pack(side="left")
            value = ttk.Label(row, text="—", style="Panel.TLabel", wraplength=195)
            value.pack(side="left", fill="x", expand=True)
            self.detail_rows[key] = value
            self.detail_row_widgets[key] = row
        ttk.Button(
            self.detail_row_widgets["sha256"],
            text="Copy",
            width=6,
            command=lambda: self._copy_sha256(),
        ).pack(side="right")

        self.archive_label = ttk.Label(details, text="Archive contents", style="Muted.TLabel")
        self.archive_label.pack(anchor="w", pady=(10, 4))
        self.archive_border = tk.Frame(details, bg=BG_CANVAS, highlightbackground=BORDER, highlightthickness=1)
        self.archive_border.pack(fill="both", expand=True)
        self.archive_list = tk.Text(
            self.archive_border,
            height=5,
            bg=BG_CANVAS,
            fg=TEXT_SECONDARY,
            relief="flat",
            bd=0,
            font=("Consolas", 8),
            padx=8,
            pady=6,
            wrap="none",
            state="disabled",
        )
        self.archive_list.pack(fill="both", expand=True)

        # 3. Bottom Status & Transfer Bar
        self._hairline(self).pack(fill="x")
        transfer_bar = ttk.Frame(self, style="Panel.TFrame", padding=(14, 7))
        transfer_bar.pack(fill="x", side="bottom")

        self.status_lbl = ttk.Label(transfer_bar, text="Ready", style="Panel.TLabel")
        self.status_lbl.pack(side="left")

        self.btn_cancel = ttk.Button(
            transfer_bar, text="Cancel upload", command=self._cancel_transfer, state="disabled"
        )
        self.btn_cancel.pack(side="right", padx=(10, 0))

        self.progress_percent = ttk.Label(transfer_bar, text="0%", style="Panel.TLabel", width=5, anchor="e")
        self.progress_percent.pack(side="right", padx=(10, 0))

        self.progress = ttk.Progressbar(transfer_bar, mode="determinate", maximum=100, length=320)
        self.progress.pack(side="right")

    def _sync_sidebar_states(self):
        active_mode = self.mode.get()
        for m, (row, btn, tag) in self.source_buttons.items():
            is_active = m == active_mode
            bg = BG_HOVER if is_active else BG_PANEL
            row.configure(bg=bg)
            btn.configure(bg=bg, fg=TEXT_PRIMARY if is_active else TEXT_SECONDARY)
            tag.configure(bg=bg, fg=ACCENT if is_active else TEXT_MUTED)

        active_cat = self.filter_cat.get()
        for c, btn in self.filter_buttons.items():
            is_active = c == active_cat
            btn.configure(
                bg=BG_HOVER if is_active else BG_PANEL,
                fg=TEXT_PRIMARY if is_active else TEXT_SECONDARY,
            )

    def _select_category(self, cat: str):
        self.filter_cat.set(cat)
        self._sync_sidebar_states()
        self._render_grid()

    def _focus_search(self):
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, tk.END)

    def _clear_search(self):
        self.search_var.set("")
        self._render_grid()
        if hasattr(self, "search_entry"):
            self.search_entry.focus_set()

    def _copy_sha256(self):
        if not self.selected_manifest:
            return
        self.clipboard_clear()
        self.clipboard_append(self.selected_manifest.total_sha256)
        self.status_lbl.configure(text="SHA-256 copied to clipboard.")

    def _update_address_bar(self):
        m = self.mode.get()
        sub = f"{self.current_subpath}/" if self.current_subpath else ""
        if m == "FTP":
            base = self.ftp_base.get().strip("/")
            prefix = f"{base}/" if base else ""
            self.address_var.set(f"ftp://{self.ftp_host.get()}:{self.ftp_port.get()}/{prefix}{sub}")
        elif m == "FOLDER":
            self.address_var.set(f"{os.path.abspath(self.local_dir.get())}\\{sub}" if sub else os.path.abspath(self.local_dir.get()))
        else:
            self.address_var.set(sub)
        self.btn_up.configure(state="normal" if self.current_subpath else "disabled")

    def _get_backend(self):
        m = self.mode.get()
        if m == "FTP":
            return FTPStorageBackend(
                self.ftp_host.get(), int(self.ftp_port.get()), self.user_val(), self.ftp_pass.get(), self.ftp_base.get()
            )
        if m == "FOLDER":
            return FolderStorageBackend(self.local_dir.get())
        raise ValueError("Unknown storage location")

    def user_val(self) -> str:
        return self.ftp_user.get().strip() or "anonymous"

    def _switch_source(self, mode_val: str):
        self.mode.set(mode_val)
        self.current_subpath = ""
        self._sync_sidebar_states()
        self._update_address_bar()
        self.refresh_files()

    def _open_folder(self, folder_name: str):
        self.current_subpath = f"{self.current_subpath}/{folder_name}".strip("/")
        self._update_address_bar()
        self.refresh_files()

    def _go_up(self):
        if not self.current_subpath:
            return
        parts = self.current_subpath.split("/")
        self.current_subpath = "/".join(parts[:-1])
        self._update_address_bar()
        self.refresh_files()

    def open_connection_dialog(self):
        win = tk.Toplevel(self)
        win.title("Connection settings")
        win.geometry("470x390")
        win.resizable(False, False)
        win.configure(bg=BG_PANEL)
        win.transient(self)
        win.grab_set()

        wrap = ttk.Frame(win, style="Panel.TFrame", padding=18)
        wrap.pack(fill="both", expand=True)

        ttk.Label(wrap, text="Router FTP address & port", style="Muted.TLabel").pack(anchor="w", pady=(0, 4))
        row1 = ttk.Frame(wrap, style="Panel.TFrame")
        row1.pack(fill="x", pady=(0, 10))
        ttk.Entry(row1, textvariable=self.ftp_host, font=("Consolas", 9)).pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        ttk.Entry(row1, textvariable=self.ftp_port, width=8, font=("Consolas", 9)).pack(side="right")

        ttk.Label(wrap, text="FTP username & password (blank for anonymous)", style="Muted.TLabel").pack(
            anchor="w", pady=(0, 4)
        )
        row2 = ttk.Frame(wrap, style="Panel.TFrame")
        row2.pack(fill="x", pady=(0, 10))
        ttk.Entry(row2, textvariable=self.ftp_user, font=("Consolas", 9)).pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        ttk.Entry(row2, textvariable=self.ftp_pass, show="*", font=("Consolas", 9)).pack(
            side="right", fill="x", expand=True
        )

        ttk.Label(wrap, text="Starting FTP folder", style="Muted.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Entry(wrap, textvariable=self.ftp_base, font=("Consolas", 9)).pack(fill="x", pady=(0, 10))

        ttk.Label(wrap, text="Network or local folder", style="Muted.TLabel").pack(anchor="w", pady=(0, 4))
        local_row = ttk.Frame(wrap, style="Panel.TFrame")
        local_row.pack(fill="x", pady=(0, 16))
        ttk.Entry(local_row, textvariable=self.local_dir, font=("Consolas", 9)).pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )

        def browse_local():
            selected = filedialog.askdirectory(title="Choose local storage folder", initialdir=self.local_dir.get())
            if selected:
                self.local_dir.set(selected)

        ttk.Button(local_row, text="Browse", command=browse_local).pack(side="right")

        def save_and_reload():
            self.current_subpath = ""
            self._update_address_bar()
            win.destroy()
            self.refresh_files()

        actions = ttk.Frame(wrap, style="Panel.TFrame")
        actions.pack(fill="x", side="bottom")
        if self.mode.get() == "FTP":
            ttk.Button(
                actions,
                text="Test connection",
                command=lambda: self._test_ftp_connection(actions),
            ).pack(side="left")
        ttk.Button(actions, text="Save and refresh", style="Accent.TButton", command=save_and_reload).pack(
            side="right"
        )
        ttk.Button(actions, text="Cancel", command=win.destroy).pack(side="right", padx=(0, 8))

    def _test_ftp_connection(self, parent):
        def worker():
            try:
                backend = FTPStorageBackend(
                    self.ftp_host.get(),
                    int(self.ftp_port.get()),
                    self.user_val(),
                    self.ftp_pass.get(),
                    self.ftp_base.get(),
                )
                backend.list_items("")
                self.after(0, lambda: messagebox.showinfo("Connection successful", "The FTP server is reachable."))
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda msg=err_msg: messagebox.showerror("Connection failed", msg))

        threading.Thread(target=worker, daemon=True).start()

    def refresh_files(self):
        self.status_lbl.configure(text="Loading folders and files...")
        sub = self.current_subpath

        def worker():
            try:
                backend = self._get_backend()
                folders, names = backend.list_items(sub)
                prefix = f"{sub}/" if sub else ""
                loaded = [FileManifest.from_bytes(backend.download_bytes(f"{prefix}{n}")) for n in names]
                self.folders = folders
                self.manifests = loaded
                self.selected_manifest = None
                self.after(0, self._render_grid)
                self.after(0, self._clear_details)
                self.after(
                    0,
                    lambda: self.status_lbl.configure(
                        text=f"Found {len(folders)} folders and {len(loaded)} protected files."
                    ),
                )
            except Exception as e:
                err_msg = str(e)
                self.after(
                    0, lambda msg=err_msg: self.status_lbl.configure(text=f"Could not connect to storage: {msg}")
                )

        threading.Thread(target=worker, daemon=True).start()

    def _render_grid(self):
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
        self.item_map.clear()
        self.tree_icon_refs.clear()
        query = self.search_var.get().strip().lower()
        cat = self.filter_cat.get()

        visible_folders = [f for f in self.folders if query in f.lower()] if cat == "all" else []
        filtered_files = [
            m
            for m in self.manifests
            if (cat == "all" or m.category == cat) and (query in m.original_filename.lower())
        ]

        if self.sort_key == "name":
            visible_folders.sort(key=str.lower, reverse=self.sort_reverse)
            filtered_files.sort(key=lambda m: m.original_filename.lower(), reverse=self.sort_reverse)
        elif self.sort_key == "type":
            filtered_files.sort(key=lambda m: m.category, reverse=self.sort_reverse)
        elif self.sort_key == "parts":
            filtered_files.sort(key=lambda m: len(m.chunks), reverse=self.sort_reverse)
        elif self.sort_key == "size":
            filtered_files.sort(key=lambda m: m.total_size, reverse=self.sort_reverse)

        for folder_name in visible_folders:
            iid = f"folder:{folder_name}"
            self.item_map[iid] = ("folder", folder_name)
            self.file_tree.insert(
                "", "end", iid=iid, image=self._tree_icon(folder=True),
                text=folder_name, values=("Folder", "—", "—"),
            )

        for m in filtered_files:
            size_mb = m.total_size / (1024 * 1024)
            iid = f"file:{m.original_filename}"
            self.item_map[iid] = ("file", m)
            self.file_tree.insert(
                "",
                "end",
                iid=iid,
                image=self._tree_icon(extension=os.path.splitext(m.original_filename)[1]),
                text=m.original_filename,
                values=(
                    m.category.title(),
                    f"{len(m.chunks)} × {m.chunk_size // 1024} KB",
                    f"{size_mb:.2f} MB",
                ),
            )

        total_mb = sum(m.total_size for m in self.manifests) / (1024 * 1024)
        self.sidebar_storage.configure(text=f"{len(self.manifests)} protected files · {total_mb:.2f} MB")

    def _sort_grid(self, key: str):
        if self.sort_key == key:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_key = key
            self.sort_reverse = False
        self._render_grid()

    def _tree_icon(self, folder: bool = False, extension: str = "") -> tk.PhotoImage | None:
        if folder:
            ppm = get_windows_folder_icon_ppm(width=20, height=20)
            if not ppm:
                ppm = get_windows_icon_ppm(".folder", width=20, height=20)
        else:
            ppm = get_windows_icon_ppm(extension, width=20, height=20)
            if not ppm:
                ppm = get_windows_icon_ppm(".bin", width=20, height=20)
        if not ppm:
            return None
        try:
            image = tk.PhotoImage(data=ppm)
        except tk.TclError:
            return None
        self.tree_icon_refs.append(image)
        return image

    def _on_tree_scroll(self, first: str, last: str):
        needs_scrollbar = float(first) > 0.0 or float(last) < 1.0
        is_visible = self.tree_scrollbar.winfo_ismapped()
        if needs_scrollbar and not is_visible:
            self.tree_scrollbar.pack(side="right", fill="y", padx=(0, 2))
        elif not needs_scrollbar and is_visible:
            self.tree_scrollbar.pack_forget()

    def _on_tree_select(self, _event=None):
        selected = self.file_tree.selection()
        if not selected:
            return
        item = self.item_map.get(selected[0])
        if not item:
            return
        if item[0] == "folder":
            self._select_folder(item[1])
        else:
            self._select_manifest(item[1])

    def _on_tree_double_click(self, _event=None):
        selected = self.file_tree.selection()
        item = self.item_map.get(selected[0]) if selected else None
        if not item:
            return
        if item[0] == "folder":
            self._open_folder(item[1])
        else:
            self.download_selected()

    def _select_folder(self, folder_name: str):
        self.selected_manifest = None
        self._clear_details()

    def _select_manifest(self, m: FileManifest):
        self.selected_manifest = m
        self._show_details(m)

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        if size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def _format_duration(self, duration: float) -> str:
        if duration <= 0:
            return "—"
        total_seconds = int(round(duration))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def _set_archive_contents(self, entries: list[str]):
        self.archive_list.configure(state="normal")
        self.archive_list.delete("1.0", "end")
        self.archive_list.insert("1.0", "\n".join(entries) if entries else "No archive entries")
        self.archive_list.configure(state="disabled")

    def _clear_details(self):
        self.detail_name.configure(text="")
        self.detail_name.pack_forget()
        for value in self.detail_rows.values():
            value.configure(text="—")
        for row in self.detail_row_widgets.values():
            row.pack_forget()
        self.archive_label.pack_forget()
        self.archive_border.pack_forget()
        self.preview_border.pack(fill="x", pady=(0, 12))
        self.preview_label.configure(image="", text="Pick an item for more details")
        self.preview_label.image = None
        self._set_archive_contents([])

    def _show_details(self, m: FileManifest):
        ext = os.path.splitext(m.original_filename)[1].lower() or "Unknown"
        self.detail_name.configure(text=m.original_filename)
        self.detail_name.pack(anchor="w", pady=(0, 10))
        for row in self.detail_row_widgets.values():
            row.pack(fill="x", pady=2)
        self.archive_label.pack(anchor="w", pady=(10, 4))
        self.archive_border.pack(fill="both", expand=True)
        self.detail_rows["type"].configure(text=ext.lstrip(".").upper() or "Unknown")
        self.detail_rows["size"].configure(text=self._format_size(m.total_size))
        dimensions = f"{m.width} × {m.height}" if m.width and m.height else "Not available"
        self.detail_rows["dimensions"].configure(text=dimensions)
        self.detail_rows["duration"].configure(text=self._format_duration(m.duration_seconds))
        self.detail_rows["chunks"].configure(text=f"{len(m.chunks)} × {m.chunk_size // 1024} KB")
        self.detail_rows["category"].configure(text=m.category.title())
        location = self.address_var.get().rstrip("/")
        self.detail_rows["location"].configure(text=location)
        self.detail_rows["sha256"].configure(text=m.total_sha256)
        self._set_archive_contents(m.archive_contents)

        if m.category not in ("image", "video"):
            preview = create_tk_preview(m.thumbnail_b64, m.category, ext)
        else:
            try:
                preview = tk.PhotoImage(data=m.thumbnail_b64) if m.thumbnail_b64 else None
            except tk.TclError:
                preview = None
            if preview is None:
                preview = create_tk_preview("", m.category, ext)

        try:
            preview = preview.zoom(2, 2)
        except (AttributeError, tk.TclError):
            pass
        self.thumb_refs = [preview]
        self.preview_label.configure(image=preview, text="")
        self.preview_label.image = preview

    def upload_dialog(self):
        if self.mode.get() == "FTP" and not self.current_subpath and self.folders:
            messagebox.showinfo(
                "Choose a folder",
                f"You are at the router root.\nDouble-click one of these folders ({', '.join(self.folders)}) before uploading.",
            )
            return

        files = filedialog.askopenfilenames(title="Choose files to upload")
        if not files:
            return
        files = tuple(files)
        self.btn_cancel.configure(state="normal")
        self.progress.configure(value=0)
        self.progress_percent.configure(text="0%")
        self.status_lbl.configure(text=f"Queued {len(files)} file{'s' if len(files) != 1 else ''} for upload.")
        self.engine = SmartTransferEngine(self._get_backend())
        chunk_bytes = self.chunk_kb.get() * 1024
        target_dir = self.current_subpath

        def worker():
            try:
                file_sizes = [os.path.getsize(path) for path in files]
                total_size = sum(file_sizes)
                completed_size = 0

                for index, (path, file_size) in enumerate(zip(files, file_sizes), start=1):
                    name = os.path.basename(path)

                    def on_file_progress(
                        pct,
                        rtt,
                        status,
                        filename=name,
                        file_index=index,
                        size=file_size,
                        completed_before_file=completed_size,
                    ):
                        overall_pct = (
                            (completed_before_file + size * pct / 100) / total_size * 100
                            if total_size
                            else ((file_index - 1 + pct / 100) / len(files) * 100)
                        )
                        self.after(
                            0,
                            self._update_upload_progress,
                            filename,
                            file_index,
                            len(files),
                            overall_pct,
                            pct,
                            len(files) - file_index,
                            rtt,
                            status,
                        )

                    self.engine.upload_file(
                        path,
                        chunk_size=chunk_bytes,
                        remote_dir=target_dir,
                        on_progress=on_file_progress,
                    )
                    completed_size += file_size
                    overall_pct = completed_size / total_size * 100 if total_size else index / len(files) * 100
                    self.after(
                        0,
                        lambda p=overall_pct: (
                            self.progress.configure(value=p),
                            self.progress_percent.configure(text=f"{p:.0f}%"),
                        ),
                    )
                self.after(
                    0,
                    lambda: (
                        self.progress.configure(value=100),
                        self.progress_percent.configure(text="100%"),
                        self.status_lbl.configure(text="All files uploaded successfully."),
                    ),
                )
                self.refresh_files()
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda msg=err_msg: self.status_lbl.configure(text=msg))
            finally:
                self.after(0, lambda: self.btn_cancel.configure(state="disabled"))

        threading.Thread(target=worker, daemon=True).start()

    def _update_upload_progress(
        self,
        filename: str,
        file_index: int,
        file_count: int,
        overall_pct: float,
        file_pct: float,
        queued_count: int,
        rtt_ms: int,
        status: str,
    ):
        overall_pct = min(overall_pct, 99.9)
        queue_text = f" | {queued_count} queued" if queued_count else ""
        self.progress.configure(value=overall_pct)
        self.progress_percent.configure(text=f"{overall_pct:.0f}%")
        self.status_lbl.configure(
            text=f"Uploading {file_index}/{file_count}: {filename} ({file_pct:.0f}%)"
            f"{queue_text} | Router: {rtt_ms} ms | {status}"
        )

    def download_selected(self):
        if not self.selected_manifest:
            messagebox.showinfo("Select a file", "Select a file in the main window to download it.")
            return
        m = self.selected_manifest
        save_path = filedialog.asksaveasfilename(
            title="Save downloaded file", initialfile=m.original_filename
        )
        if not save_path:
            return

        self.btn_cancel.configure(state="normal")
        self.progress.configure(value=0)
        self.progress_percent.configure(text="0%")
        self.engine = SmartTransferEngine(self._get_backend())
        target_dir = self.current_subpath

        def worker():
            try:
                self.engine.download_and_reassemble(
                    m,
                    save_path,
                    remote_dir=target_dir,
                    on_progress=lambda pct, rtt, st: self.after(
                        0,
                        lambda: (
                            self.progress.configure(value=pct),
                            self.progress_percent.configure(text=f"{pct:.0f}%"),
                            self.status_lbl.configure(text=f"{st} ({pct:.0f}%) | {rtt} ms"),
                        ),
                    ),
                )
                self.after(
                    0,
                    lambda: (
                        self.status_lbl.configure(text="File downloaded and verified successfully."),
                        messagebox.showinfo(
                            "Download complete", f"'{m.original_filename}' was restored and verified."
                        ),
                    ),
                )
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda msg=err_msg: messagebox.showerror("Transfer error", msg))
            finally:
                self.after(0, lambda: self.btn_cancel.configure(state="disabled"))

        threading.Thread(target=worker, daemon=True).start()

    def delete_selected(self):
        if not self.selected_manifest:
            messagebox.showinfo("Select a file", "Select a file in the main window to delete it.")
            return

        m = self.selected_manifest
        confirmed = messagebox.askyesno(
            "Delete file",
            f"Delete '{m.original_filename}' and all of its stored parts?",
            icon="warning",
        )
        if not confirmed:
            return

        backend = self._get_backend()
        target_dir = self.current_subpath
        prefix = f"{target_dir.strip('/')}/" if target_dir.strip("/") else ""
        chunks_prefix = f"{prefix}{m.chunks_folder}"
        manifest_path = f"{prefix}{m.original_filename}.manifest.json"
        total_steps = len(m.chunks) + 2
        self.progress.configure(value=0)

        def worker():
            completed = 0

            def report_progress(stage: str):
                percent = completed / total_steps * 100
                self.after(
                    0,
                    lambda pct=percent, text=stage: (
                        self.progress.configure(value=pct),
                        self.status_lbl.configure(text=f"{text} ({pct:.0f}%)"),
                    ),
                )

            try:
                for chunk in m.chunks:
                    backend.delete_path(f"{chunks_prefix}/{chunk['name']}")
                    completed += 1
                    report_progress(f"Deleting parts for '{m.original_filename}'")

                backend.delete_path(chunks_prefix)
                completed += 1
                report_progress("Removing parts folder")

                backend.delete_path(manifest_path)
                completed += 1
                report_progress("Removing file manifest")
                self.after(
                    0,
                    lambda: (
                        self.status_lbl.configure(text=f"Deleted '{m.original_filename}'."),
                        self.refresh_files(),
                    ),
                )
            except Exception as e:
                err_msg = str(e)
                self.after(
                    0,
                    lambda msg=err_msg: (
                        self.status_lbl.configure(text=f"Delete failed: {msg}"),
                        messagebox.showerror("Delete failed", msg),
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _cancel_transfer(self):
        if self.engine:
            self.engine.cancel()