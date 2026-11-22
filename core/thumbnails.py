import os
import io
import base64
import shutil
import subprocess
import tempfile
import tkinter as tk
from core.win_icons import get_windows_icon_ppm

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz"}


def detect_file_category(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in ARCHIVE_EXTS:
        return "archive"
    return "document"


def generate_thumbnail_b64(filepath: str) -> str:
    """Generate a PNG thumbnail (140x84) as base64 for Tkinter."""
    ext = os.path.splitext(filepath)[1].lower()

    if ext in VIDEO_EXTS:
        try:
            import cv2
            cap = cv2.VideoCapture(filepath)
            cap.set(cv2.CAP_PROP_POS_MSEC, 1500)
            ok, frame = cap.read()
            cap.release()
            if ok:
                resized = cv2.resize(frame, (140, 84))
                ok_enc, buf = cv2.imencode(".png", resized)
                if ok_enc:
                    return base64.b64encode(buf.tobytes()).decode("ascii")
        except Exception:
            pass

        if shutil.which("ffmpeg"):
            try:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = tmp.name
                subprocess.run(
                    ["ffmpeg", "-y", "-ss", "00:00:01", "-i", filepath, "-vframes", "1", "-vf", "scale=140:84", tmp_path],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
                )
                if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                    with open(tmp_path, "rb") as f:
                        data = f.read()
                    os.remove(tmp_path)
                    return base64.b64encode(data).decode("ascii")
            except Exception:
                pass

    if ext in IMAGE_EXTS:
        try:
            from PIL import Image
            with Image.open(filepath) as img:
                img.thumbnail((140, 84))
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="PNG")
                return base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            pass

    return ""


def inspect_media_metadata(filepath: str) -> tuple[int, int, float]:
    """Return width, height, and duration for supported images and videos."""
    ext = os.path.splitext(filepath)[1].lower()

    if ext in IMAGE_EXTS:
        try:
            from PIL import Image
            with Image.open(filepath) as img:
                width, height = img.size
                return width, height, 0.0
        except Exception:
            return 0, 0, 0.0

    if ext in VIDEO_EXTS:
        try:
            import cv2
            cap = cv2.VideoCapture(filepath)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            cap.release()
            duration = frame_count / fps if fps > 0 else 0.0
            return width, height, duration
        except Exception:
            return 0, 0, 0.0

    return 0, 0, 0.0


def create_tk_preview(b64_data: str, category: str, ext: str) -> tk.PhotoImage:
    """Use a streamed thumbnail, then a Windows icon, then a color fallback."""
    if b64_data:
        try:
            return tk.PhotoImage(data=b64_data)
        except Exception:
            pass

    ppm_icon = get_windows_icon_ppm(ext, width=140, height=84)
    if ppm_icon:
        try:
            return tk.PhotoImage(data=ppm_icon)
        except Exception:
            pass

    palette = {
        "video": ("#1f6feb", "#58a6ff"),
        "image": ("#238636", "#3fb950"),
        "archive": ("#9e6a03", "#d29922"),
        "document": ("#30363d", "#8b949e"),
    }
    bg, accent = palette.get(category, ("#30363d", "#8b949e"))
    img = tk.PhotoImage(width=140, height=84)
    img.put(bg, to=(0, 0, 140, 84))
    img.put(accent, to=(0, 0, 140, 5))
    return img