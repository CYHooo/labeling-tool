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

Pick how you want to work from the tabs at the top of the login screen.

| Tab | Purpose |
|---|---|
| **Online labeling** | Fetch a job from the server, label it and upload it. |
| **Local jobs** | Continue a job you have already downloaded. |
| **Few-shot labeling** | Multi-class labeling with SAM2.1. The model (about 308 MB) downloads once, the first time you open it. |

### 1. Log in and fetch data

1. On the "Online labeling" tab, enter `BASE URL` and `X-Viewer-Api-Key`, then click "Next". The values are saved and filled in next time.
2. On the fetch screen, choose a session and, if needed, the photo range with `fromNum` / `toNum` (0 = from the start / to the end).
3. Click "Fetch (download)". The photos download and the labeling window opens.

To continue a job you already have, pick it on the "Local jobs" tab and click "Open".

### 2. Label

| Feature | What it does |
|---|---|
| **Brush** | Draw a crack roughly; when you release the mouse it becomes a 1 px centerline. Turn on "Fine annotation (keep width)" to keep the drawn width. |
| **Repair area** | Mark repair regions with rotatable rectangles (OBB). Overlaps are counted once. |
| **Scale (px/cm)** | Uses the value the server computed. To correct it, use "Manual Measure (fallback)": click two points of a reference line and enter its real length. |
| **SAM segment (spalling)** | Left-click to include and right-click to exclude; the spalling region is found automatically. "Confirm (write spalling)" records it, Esc undoes the last point. |
| **Show Highlight / Show 15cm Boundary** | Preview the highlight around cracks and the 15 cm boundary around repair areas. |

Your work is saved automatically when you move to another image; "Save Mask" saves it on demand.

### 3. Upload to EC2

"Upload to EC2" uploads **only the photos you edited**, together with the mask, highlight and 15 cm boundary. After uploading, the app reads the server back to confirm every photo arrived and lists any that did not. Details are written to `vapi.log` in the job folder.

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
