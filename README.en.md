# LM Labeling Tool

[한국어](README.md) | **English** | [中文](README.zh-CN.md)

A labeling tool for **correcting, on your own PC**, the stitched images and crack masks produced by the AI server.
Edit crack masks, mark repair areas (OBB) and check the scale (px/cm), then upload the results back to the server (EC2).

Workflow: **Log in → Fetch data → Label → Upload to EC2**

---

## Download

[**Download the latest version (Releases)**](https://github.com/CYHooo/labeling-tool/releases/latest) — take **one** file for your system from the table at the top of the page.

| System | File | Size |
|---|---|---|
| Windows 10 / 11 (64-bit) | `LM_LabelingTool-Setup-v<version>.exe` | about 1.6 GB |
| Ubuntu 22.04 / 24.04 (64-bit) | `lm-labeling-tool_<version>_amd64.deb` | about 1.8 GB |

## Install

### Windows

1. Double-click the downloaded `LM_LabelingTool-Setup-v<version>.exe`.
2. If "Windows protected your PC" appears, click **More info → Run anyway**.
3. Go through the setup wizard with the defaults. No administrator rights are needed.
4. Start **LM_LabelingTool** from the **Start menu**.

### Ubuntu

```bash
sudo dpkg -i lm-labeling-tool_<version>_amd64.deb
```

Start **LM Labeling Tool** from the applications menu.

## Updates

The app checks for a new version **at startup and every 4 hours while running**. To check yourself, click "Check for updates" on the login screen.

- Small updates (a few MB) are downloaded in the background first, then offered. "Restart and update" applies them right away. On Ubuntu you enter your password once.
- While you are labeling, the app does not interrupt you; it asks when you close the job window.
- A large update that needs the full installer shows its size first and is never downloaded without your consent.
- If an update fails or the power goes out midway, the app returns to the previous version.

## How to use

After logging in, the jobs screen has two tabs.

| Tab | Purpose |
|---|---|
| **Labeling** | Fetch a new job from the server, or continue one already on this PC; label it and upload it. |
| **Few-shot labeling** | Multi-class labeling with SAM2.1. The model (about 308 MB) downloads once, the first time you open it. |

### 1. Log in and open a job

On the first screen, enter your **ID / password** and the **server** (`BASE URL`, `X-Viewer-Api-Key`), then click "Log in". The ID and server are saved and filled in next time; the password is never stored. For now the development account `admin` / `admin` is used (per-user accounts will come with server support).

After logging in, the jobs screen opens: **Local jobs** lists the jobs already on this PC, newest first. "Log out" returns to the first screen.

- **A new job**: "Fetch a new job" → pick the job and, if needed, the photo range with `fromNum` / `toNum` (0 = from the start / to the end) → "Fetch (download)". The labeling window opens once the photos are in.
- **A job you already have**: pick it in the list and click "Open" (or double-click). Uploads go to the server the job came from; with the Key empty, work is saved on this PC only.
- The list opens most recently modified first. Click a column header (job, inspection name, photos, last modified) to sort by it; click again to reverse.
- Fetching a job that is already on this PC asks "Open" or "Fetch again". Fetching again keeps your labeling and upload records. A same-numbered job fetched from another server can't be opened here.

### 2. Label

The top of the right panel shows the job ID, inspection name and photo count; "?" opens the shortcut help. The image list shows "No." (`job ID-photo number`, e.g. 49-3) and "File name", with "Previous" / "Next" / "Save" (A / D / S) below it. Under "Edit tools", click "View", "Brush", "SAM" or "Repair area": the selected tool is the editing mode ("View" edits nothing), and how to use it and its options appear right below. Crack / spalling is chosen in the brush options. "Display · Scale" holds the highlight / 15cm boundary toggles and the scale. "Upload to EC2" stays pinned at the bottom of the panel.

| Feature | What it does |
|---|---|
| **Brush** | Draw a crack roughly; when you release the mouse it becomes a 1 px centerline. Turn on "Fine (keep width)" to keep the drawn width. |
| **Repair area** | Mark repair regions with rotatable rectangles (OBB). Overlaps are counted once. |
| **Scale (px/cm)** | Uses the value the server computed. To correct it, use "Measure": click two points of a reference line and enter its real length. |
| **SAM segment (spalling)** | Left-click to include and right-click to exclude; the spalling region is found automatically. "Confirm" records it, Esc undoes the last point. |
| **Highlight / 15cm zone** | Preview the highlight around cracks and the 15 cm boundary around repair areas. |

Your work is saved automatically when you move to another image; "Save" (S) saves it on demand.

### 3. Upload to EC2

"Upload to EC2" uploads **only the photos you edited**, together with the mask, highlight and 15 cm boundary. After uploading, the app reads the server back to confirm every photo arrived and lists any that did not. Details are written to `vapi.log` in the job folder.

### Where data and logs are

| Item | Linux | Windows |
|---|---|---|
| Jobs (photos, labeling results) | `~/.local/share/lm-labeling-tool/data/session_<job ID>/` | `<install folder>\data\session_<job ID>\` |
| Job log | `vapi.log` in the job folder | `vapi.log` in the job folder |
| App log | `~/.local/share/lm-labeling-tool/logs/app.log` | `<install folder>\logs\app.log` |

The app log (`app.log`) records startup, sign-in, updates, unexpected errors and every job log line; it rotates at 1 MB and keeps the last five files. When something goes wrong, open the folder from "?" → "Open log folder" on the labeling screen and send `app.log`. Passwords and API keys are never logged.

## Language

Change the display language (한국어 / 中文 / English) with "Language:" at the bottom of the login screen or under "Settings" in the labeling window. Your choice is saved.

## Data location and uninstall

| | Data location | Uninstall |
|---|---|---|
| Windows | `%LOCALAPPDATA%\Programs\LM_LabelingTool` | Control Panel → Uninstall a program |
| Ubuntu | `~/.local/share/lm-labeling-tool/` | `sudo apt purge lm-labeling-tool` |

Your settings, downloaded jobs and model files **stay after uninstalling**, so a reinstall picks up where you left off.

---

## For developers

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
./run.sh                           # Windows: run.bat
```

- Tests: `pip install -r requirements-dev.txt`, then `QT_QPA_PLATFORM=offscreen python -m pytest tests labeling_tool/tests annotation_tool/tests -q`
- Few-shot tool: [`annotation_tool/USAGE.md`](annotation_tool/USAGE.md)
- Release process: [`docs/RELEASING.md`](docs/RELEASING.md) (Chinese)
- UI terminology: [`docs/i18n-glossary.md`](docs/i18n-glossary.md)
