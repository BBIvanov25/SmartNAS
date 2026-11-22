import os
import sys
import ctypes
from ctypes import wintypes

_ICON_PPM_CACHE: dict[tuple[str, int, int], bytes | None] = {}


def get_windows_icon_ppm(ext: str, width: int = 140, height: int = 84) -> bytes | None:
    """Extract the Windows icon for a file extension (for example, '.zip') as PPM."""
    if sys.platform != "win32":
        return None

    ext_key = (ext or ".bin").lower()
    if not ext_key.startswith("."):
        ext_key = "." + ext_key

    cache_key = (ext_key, width, height)
    if cache_key in _ICON_PPM_CACHE:
        return _ICON_PPM_CACHE[cache_key]

    try:
        class SHFILEINFOW(ctypes.Structure):
            _fields_ = [
                ("hIcon", wintypes.HICON),
                ("iIcon", ctypes.c_int),
                ("dwAttributes", wintypes.DWORD),
                ("szDisplayName", wintypes.WCHAR * 260),
                ("szTypeName", wintypes.WCHAR * 80),
            ]

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [
                ("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3),
            ]

        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        shell32.SHGetFileInfoW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(SHFILEINFOW), wintypes.UINT, wintypes.UINT
        ]
        shell32.SHGetFileInfoW.restype = ctypes.c_size_t

        user32.GetDC.argtypes = [wintypes.HWND]
        user32.GetDC.restype = wintypes.HDC
        user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        user32.ReleaseDC.restype = ctypes.c_int
        user32.DrawIconEx.argtypes = [
            wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HICON,
            ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.HBRUSH, wintypes.UINT
        ]
        user32.DrawIconEx.restype = wintypes.BOOL
        user32.DestroyIcon.argtypes = [wintypes.HICON]
        user32.DestroyIcon.restype = wintypes.BOOL

        gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi32.CreateCompatibleDC.restype = wintypes.HDC
        gdi32.DeleteDC.argtypes = [wintypes.HDC]
        gdi32.DeleteDC.restype = wintypes.BOOL
        gdi32.CreateDIBSection.argtypes = [
            wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD
        ]
        gdi32.CreateDIBSection.restype = wintypes.HBITMAP
        gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        gdi32.SelectObject.restype = wintypes.HGDIOBJ
        gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        gdi32.DeleteObject.restype = wintypes.BOOL
        gdi32.GdiFlush.argtypes = []
        gdi32.GdiFlush.restype = wintypes.BOOL

        SHGFI_ICON = 0x000000100
        SHGFI_LARGEICON = 0x000000000
        SHGFI_USEFILEATTRIBUTES = 0x000000010
        FILE_ATTRIBUTE_NORMAL = 0x00000080
        DI_NORMAL = 0x0003

        shfi = SHFILEINFOW()
        res = shell32.SHGetFileInfoW(
            f"dummy{ext_key}",
            FILE_ATTRIBUTE_NORMAL,
            ctypes.byref(shfi),
            ctypes.sizeof(shfi),
            SHGFI_ICON | SHGFI_LARGEICON | SHGFI_USEFILEATTRIBUTES,
        )
        if not res or not shfi.hIcon:
            _ICON_PPM_CACHE[cache_key] = None
            return None

        hicon = shfi.hIcon
        hdc_screen = user32.GetDC(None)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height  # top-down image
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0  # BI_RGB

        bits_ptr = ctypes.c_void_p()
        hbm = gdi32.CreateDIBSection(hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(bits_ptr), None, 0)

        try:
            if not hbm or not bits_ptr.value:
                return None

            # Fill the background with the card color (#252526 in BGRA).
            bg_fill = b"\x26\x25\x25\xff" * (width * height)
            ctypes.memmove(bits_ptr.value, bg_fill, len(bg_fill))

            old_bm = gdi32.SelectObject(hdc_mem, hbm)
            icon_sz = max(12, min(32, width - 4, height - 4))
            user32.DrawIconEx(
                hdc_mem,
                (width - icon_sz) // 2,
                (height - icon_sz) // 2,
                hicon,
                icon_sz,
                icon_sz,
                0,
                None,
                DI_NORMAL,
            )
            gdi32.GdiFlush()
            raw = ctypes.string_at(bits_ptr.value, width * height * 4)
            gdi32.SelectObject(hdc_mem, old_bm)

            # Convert BGRA to RGB; Tkinter reads PPM P6 directly without Pillow.
            rgb = bytearray(width * height * 3)
            rgb[0::3] = raw[2::4]
            rgb[1::3] = raw[1::4]
            rgb[2::3] = raw[0::4]
            ppm = f"P6\n{width} {height}\n255\n".encode("ascii") + bytes(rgb)
            _ICON_PPM_CACHE[cache_key] = ppm
            return ppm
        finally:
            if hbm:
                gdi32.DeleteObject(hbm)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(None, hdc_screen)
            user32.DestroyIcon(hicon)
    except Exception:
        _ICON_PPM_CACHE[cache_key] = None
        return None 

def get_windows_folder_icon_ppm(width: int = 140, height: int = 84) -> bytes | None:
    """Extract the Windows system icon for a folder or disk volume."""
    if sys.platform != "win32":
        return None

    cache_key = ("__folder__", width, height)
    if cache_key in _ICON_PPM_CACHE:
        return _ICON_PPM_CACHE[cache_key]

    try:
        class SHFILEINFOW(ctypes.Structure):
            _fields_ = [
                ("hIcon", wintypes.HICON),
                ("iIcon", ctypes.c_int),
                ("dwAttributes", wintypes.DWORD),
                ("szDisplayName", wintypes.WCHAR * 260),
                ("szTypeName", wintypes.WCHAR * 80),
            ]

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [
                ("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3),
            ]

        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        shell32.SHGetFileInfoW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(SHFILEINFOW), wintypes.UINT, wintypes.UINT
        ]
        shell32.SHGetFileInfoW.restype = ctypes.c_size_t

        SHGFI_ICON = 0x000000100
        SHGFI_LARGEICON = 0x000000000
        FILE_ATTRIBUTE_DIRECTORY = 0x00000010
        DI_NORMAL = 0x0003

        shfi = SHFILEINFOW()
        res = shell32.SHGetFileInfoW(
            os.environ.get("WINDIR", r"C:\Windows"),
            FILE_ATTRIBUTE_DIRECTORY,
            ctypes.byref(shfi),
            ctypes.sizeof(shfi),
            SHGFI_ICON | SHGFI_LARGEICON,
        )
        if not res or not shfi.hIcon:
            _ICON_PPM_CACHE[cache_key] = None
            return None

        hicon = shfi.hIcon
        hdc_screen = user32.GetDC(None)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0

        bits_ptr = ctypes.c_void_p()
        hbm = gdi32.CreateDIBSection(hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(bits_ptr), None, 0)
        try:
            if not hbm or not bits_ptr.value:
                return None
            bg_fill = b"\x26\x25\x25\xff" * (width * height)
            ctypes.memmove(bits_ptr.value, bg_fill, len(bg_fill))
            old_bm = gdi32.SelectObject(hdc_mem, hbm)
            icon_sz = max(12, min(32, width - 4, height - 4))
            user32.DrawIconEx(
                hdc_mem,
                (width - icon_sz) // 2,
                (height - icon_sz) // 2,
                hicon,
                icon_sz,
                icon_sz,
                0,
                None,
                DI_NORMAL,
            )
            gdi32.GdiFlush()
            raw = ctypes.string_at(bits_ptr.value, width * height * 4)
            gdi32.SelectObject(hdc_mem, old_bm)

            rgb = bytearray(width * height * 3)
            rgb[0::3] = raw[2::4]
            rgb[1::3] = raw[1::4]
            rgb[2::3] = raw[0::4]
            ppm = f"P6\n{width} {height}\n255\n".encode("ascii") + bytes(rgb)
            _ICON_PPM_CACHE[cache_key] = ppm
            return ppm
        finally:
            if hbm:
                gdi32.DeleteObject(hbm)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(None, hdc_screen)
            user32.DestroyIcon(hicon)
    except Exception:
        _ICON_PPM_CACHE[cache_key] = None
        return None