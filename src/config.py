"""Shared paths, constants, and logging setup for The Bookfather pipeline."""

import logging
import logging.handlers
from pathlib import Path

# --- Directory layout -------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR
PROCESSED_DIR = DATA_DIR / "processed"
ARTIFACTS_DIR = DATA_DIR / "artifacts"
LOG_DIR = PROJECT_ROOT / "logs"
DB_PATH = DATA_DIR / "bookfather.db"

BOOKS_DATASET_01_DIR = RAW_DIR / "books-dataset-01"
BOOKS_DATASET_02_DIR = RAW_DIR / "books-dataset-02"
BEST_BOOKS_EVER_DIR = RAW_DIR / "best-books-ever-dataset"
GOODREADS_DIR = RAW_DIR / "good-reads-book-graph-dataset"

for _dir in (PROCESSED_DIR, ARTIFACTS_DIR, LOG_DIR):
    _dir.mkdir(parents=True, exist_ok=True)


def get_logger(name: str, log_filename: str = "bookfather.log") -> logging.Logger:
    """Return a module-scoped logger that writes INFO+ to stdout and DEBUG+ to a rotating file.

    Reused across every script so log formatting/handlers stay consistent (SOLID: single
    place owns logging configuration; callers only ask for a named logger).
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        # Already configured (e.g. re-imported within the same process) - avoid duplicate handlers.
        return logger

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(fmt)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / log_filename, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger
