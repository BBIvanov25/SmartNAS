# SmartNAS

## Overview

**SmartNAS** is a desktop application for secure file transfers to USB storage connected to a budget consumer router.

## The System We Broke

We selected a typical consumer router with USB storage/NAS functionality. The router receives files through FTP but has a limited RAM buffer and a slow USB write speed.

The simulator reproduces these constraints:
- A **16 MB** RAM buffer;
- **8 MB/s** USB write speed;
- Browser and upload activity competing for the router's limited resources.

During a direct upload of a **32 MB** file, the router receives the entire request as one transfer. The buffer overflows, the simulator writes partial or corrupted content, and returns:

```text
507 Router Buffer Overflow - File Corrupted
```

## How the Solution Works

1. The application splits a file into chunks of `512 KB`, `1024 KB`, or `2048 KB` (the user chooses the size in the app).
2. Each chunk is uploaded separately into a `.chunks` folder.
3. Small requests prevent the router RAM buffer from overflowing.
4. Slow responses trigger adaptive pauses for the router to "cool down".
5. Failed FTP transfers are retried with increasing delays.
6. Before uploading, the application lists existing chunk sizes and skips matching parts so transfers can resume automatically from the point they last reached.
7. Each chunk is protected with its own SHA-256 hash.
8. A JSON manifest stores the original filename, total size, total SHA-256 hash, chunk size, chunk list, thumbnail (if present), category, and archive contents.
9. During download, every chunk is verified before it is written to the reconstructed file.
10. The final restored file is compared with the manifest's total SHA-256 hash.

The application supports three storage modes:

- **Simulator** — HTTP backend connected to the weak router simulator at `127.0.0.1:8001`;
- **Local Folder** — local filesystem storage for offline testing;
- **Router (FTP)** — FTP connection to a real router or NAS.

## Features

- File and folder browsing;
- Upload and download progress;
- Sequential multi-file upload queue with overall batch progress;
- Cancelable transfers;
- Automatic transfer resume;
- Chunk integrity verification;
- Search and category filtering;
- Image and video previews;
- Large right-side preview and file metadata panel;
- Windows file and folder icons;
- Multiple storage backends;
- Direct-upload failure demonstration and SmartNAS proof test.

## Technologies

- Python 3;
- Tkinter and ttk;
- Standard `ftplib` FTP support;
- Python `http.server` weak-router simulator;
- JSON manifests;
- SHA-256 integrity checks;
- Pillow for image previews;
- OpenCV for video frame extraction;
- Windows shell icons;
- Threading for non-blocking UI operations.

## Release 1.0.0 - 22 November 2026

This is the first packaged release of SmartNAS. It is available as both a
Windows installer and standalone portable applications.

### Downloads

| Package | File | Use |
|---|---|---|
| Windows installer | [`release/installer/SmartNAS_Drive_Setup_v1.0.exe`](release/installer/SmartNAS_Drive_Setup_v1.0.exe) | Installs SmartNAS Explorer and optionally SmartNAS Test Lab for the current Windows user |
| Portable Explorer | [`release/portable/SmartNAS_Explorer_Portable.exe`](release/portable/SmartNAS_Explorer_Portable.exe) | Runs SmartNAS Explorer without installing it |
| Portable Test Lab | [`release/portable/SmartNAS_TestLab_Portable.exe`](release/portable/SmartNAS_TestLab_Portable.exe) | Runs the direct-upload and SmartNAS proof demo without installing it |

The installer and portable executables require Windows 10 or Windows 11. They
do not require a separate Python installation.

## Installation and Startup

### Requirements

- Windows 10 or Windows 11;
- Python 3.10 or newer;
- Pillow and OpenCV from `requirements.txt`;
- Optional FTP access and write permissions on a real router or NAS.

By default, the application opens the **Folder** storage mode and uses the local `router_usb_disk` directory.

You can choose a storage mode from the left sidebar:

- **Simulator** to test against the weak-router HTTP server;
- **Local Folder** to use a folder on your computer;
- **Router (FTP)** to enter the host, port, username, password, and starting folder for a real router.

To upload files:

1. Select a storage mode.
2. Open a destination folder.
3. Select a chunk size.
4. Click **Upload files**.

To download or delete a file:

1. Select a file in the file list.
2. Click **Download** or **Delete** (or alternatively double-click the file).

## Run the Test Lab

```powershell
python run_test_lab.py
```

The Test Lab starts the simulator at `http://127.0.0.1:8001` and creates or verifies `demo_4k_clip_32mb.mp4`.

1. Click **Try direct upload** to demonstrate the 32 MB buffer overflow.
2. Click **Use SmartNAS upload** to demonstrate chunked transfer.
3. Compare RAM usage, folder browsing, transfer speed, and SHA-256 verification in the results table.

## Project Structure

```text
core/           Chunking, manifests, thumbnails, and Windows icons
simulator/      Weak-router HTTP simulator
storage/        FTP, folder, and demo storage backends
ui/             SmartNAS Explorer and Test Lab interfaces
main.py         SmartNAS Explorer entry point
run_test_lab.py Test Lab entry point
```

## Team Pixel Velocity

| Member | Role |
|---|---|
| **bbivanov25** | Team lead; core chunking and manifest logic, thumbnails, Windows icons, UI design, and localization |
| **NIYordanov25** | Storage architecture; FTP, folder, and demo backends, weak-router simulator, and delete functionality |
| **RVVenev25** | Test Lab UI and stress-test visualization |
| **VSVasilev25** | SmartNAS Explorer UI and upload/download functionality |
| **MRBaranova25** | Application entry points, Test Lab launcher, and project dependencies |
