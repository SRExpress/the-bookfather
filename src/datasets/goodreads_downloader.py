"""Re-runnable downloader for the UCSD Goodreads Book Graph dataset.

Usage:
    python -m src.datasets.goodreads_downloader                  # metadata tier (default)
    python -m src.datasets.goodreads_downloader --tier metadata interactions
    python -m src.datasets.goodreads_downloader --status          # report only, no downloads

Idempotent: a file already present and at/above its expected minimum size is left alone
and reported as "cached". Downloads stream to a ``.part`` file and are only renamed into
place on success, so an interrupted run can simply be re-run.
"""

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from src.config import GOODREADS_DIR, get_logger
from src.datasets.goodreads_registry import DatasetFile, dest_path, files_for_tiers

logger = get_logger(__name__, log_filename="goodreads_download.log")

CHUNK_SIZE = 1024 * 1024  # 1 MiB
REQUEST_TIMEOUT_SECONDS = 30


@dataclass
class DownloadResult:
    file: DatasetFile
    status: str  # "cached" | "downloaded" | "failed"
    size_bytes: int
    duration_seconds: float
    error: str | None = None


def _is_cached(file: DatasetFile) -> bool:
    """A file counts as already downloaded if it exists and meets its size floor."""
    path = dest_path(file)
    logger.debug("Checking cache status for %s at %s", file.name, path)
    return path.exists() and path.stat().st_size >= file.min_expected_bytes


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}PB"


def download_file(file: DatasetFile) -> DownloadResult:
    """Stream one registry file to disk via a .part file, renamed on success."""
    GOODREADS_DIR.mkdir(parents=True, exist_ok=True)
    final_path = dest_path(file)

    if _is_cached(file):
        size = final_path.stat().st_size
        logger.info("SKIP (cached): %s already present (%s)", file.name, _human_size(size))
        return DownloadResult(file, "cached", size, 0.0)

    part_path = final_path.with_suffix(final_path.suffix + ".part")
    logger.info("Downloading %s -> %s", file.url, final_path)
    start = time.monotonic()
    try:
        with requests.get(file.url, stream=True, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            response.raise_for_status()
            downloaded = 0
            with open(part_path, "wb") as out:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if not chunk:
                        continue
                    out.write(chunk)
                    downloaded += len(chunk)
                    if downloaded % (CHUNK_SIZE * 200) == 0:
                        logger.debug("%s: %s downloaded so far", file.name, _human_size(downloaded))

        if downloaded < file.min_expected_bytes:
            raise IOError(
                f"downloaded size {_human_size(downloaded)} is below expected minimum "
                f"{_human_size(file.min_expected_bytes)} - likely a truncated/failed transfer"
            )

        part_path.rename(final_path)
        duration = time.monotonic() - start
        logger.info(
            "DONE: %s (%s in %.1fs)", file.name, _human_size(downloaded), duration
        )
        return DownloadResult(file, "downloaded", downloaded, duration)

    except Exception as exc:  # noqa: BLE001 - report and continue with remaining files
        duration = time.monotonic() - start
        logger.error("FAILED: %s - %s", file.name, exc)
        if part_path.exists():
            part_path.unlink(missing_ok=True)
        return DownloadResult(file, "failed", 0, duration, error=str(exc))


def print_report(results: list[DownloadResult]) -> None:
    header = f"{'File':<40} {'Status':<12} {'Size':>10} {'Time(s)':>9}"
    print(header)
    print("-" * len(header))
    for r in results:
        size_str = _human_size(r.size_bytes) if r.size_bytes else "-"
        time_str = f"{r.duration_seconds:.1f}" if r.duration_seconds else "-"
        print(f"{r.file.name:<40} {r.status:<12} {size_str:>10} {time_str:>9}")
        if r.error:
            print(f"    error: {r.error}")

    failed = [r for r in results if r.status == "failed"]
    missing = [r for r in results if r.status == "missing"]
    if failed:
        print(f"\n{len(failed)} file(s) failed - re-run this script to retry.")
    elif missing:
        print(f"\n{len(missing)} file(s) missing - run without --status to download.")
    else:
        print(f"\nAll {len(results)} file(s) present and accounted for.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download Goodreads Book Graph dataset files.")
    parser.add_argument(
        "--tier",
        nargs="+",
        default=["metadata"],
        choices=["metadata", "interactions", "reviews"],
        help="Which dataset tier(s) to fetch (default: metadata only).",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Only report cached/missing status for the selected tiers; do not download.",
    )
    args = parser.parse_args(argv)

    files = files_for_tiers(set(args.tier))
    logger.info("Selected tiers=%s -> %d file(s)", args.tier, len(files))

    results: list[DownloadResult] = []
    for file in files:
        if args.status:
            cached = _is_cached(file)
            size = dest_path(file).stat().st_size if dest_path(file).exists() else 0
            results.append(
                DownloadResult(file, "cached" if cached else "missing", size, 0.0)
            )
        else:
            results.append(download_file(file))

    print_report(results)
    return 1 if any(r.status == "failed" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
