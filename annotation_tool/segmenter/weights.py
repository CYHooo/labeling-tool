"""SAM2.1 base_plus weights: official URL + checksum, and a safe downloader.

The Windows exe does not bundle weights (keeps the download smaller and lets
upgrades reuse <exe>/checkpoint/); they are fetched on first few-shot use.
Download goes to ``<dest>.part`` and is renamed only after the SHA256 matches,
so an interrupted or corrupted download never looks like usable weights.
"""

from labeling_tool.core.net_download import DownloadCancelled, download_file

SAM2_WEIGHTS_URL = (
    "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_base_plus.pt")
SAM2_WEIGHTS_SHA256 = "a2345aede8715ab1d5d31b4a509fb160c5a4af1970f199d9054ccfb746c004c5"
SAM2_WEIGHTS_SIZE = 323_606_802

# SAM2.1 weights are fetched with the shared checksum-verified downloader.
download_weights = download_file
