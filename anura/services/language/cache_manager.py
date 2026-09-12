# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

from collections.abc import Callable
import contextlib
import os
from pathlib import Path
import shutil
import threading
import time

from loguru import logger

from anura.config import (
    TESSDATA_DIR,
    TESSDATA_SYSTEM_DIR,
)
from anura.services.settings import settings


class CacheManager:
    """
    Manages Tesseract language model cache and file I/O.
    Handles directory scanning, caching, and cleanup operations.
    """

    def __init__(self) -> None:
        self._downloaded_codes: list[str] = []
        self._need_update_cache = True
        self._cache_lock = threading.Lock()

    def _get_model_quality_dir(self, quality: str | None = None) -> Path:
        """Get the directory for the specified model quality."""
        if quality is None:
            quality = settings.get_string("tessdata-model")

        base_dir = Path(TESSDATA_DIR)
        if quality == "best":
            return base_dir / "tessdata_best"
        if quality == "standard":
            return base_dir / "tessdata"
        return base_dir

    def init_tessdata(self) -> None:
        """
        Ensures the tessdata directory exists and logs its status at startup.
        Also cleans up orphaned temporary files from interrupted downloads.
        """
        # Hardening: verify Tesseract binary availability at startup
        tess_bin = os.environ.get("TESSERACT_CMD", "tesseract")
        if not shutil.which(tess_bin):
            logger.critical(
                f"Anura: Tesseract binary '{tess_bin}' not found. "
                "OCR features will be unavailable. Please install Tesseract."
            )

        # Use lock to prevent race condition when multiple threads try to create directory
        with self._cache_lock:
            tess_path = Path(TESSDATA_DIR)
            if not tess_path.exists():
                logger.warning(
                    "Anura: tessdata directory not found. It will be created on first language download.",
                )
                with contextlib.suppress(FileExistsError):
                    # Another thread created it between check and makedirs
                    tess_path.mkdir(parents=True, exist_ok=True)

            # Security: Ensure tessdata directory has restrictive permissions (0700)
            if tess_path.exists():
                with contextlib.suppress(OSError):
                    tess_path.chmod(0o700)

        # Clean up orphaned temp files from crashed/interrupted downloads
        try:
            tess_path = Path(TESSDATA_DIR)
            # Scan root and standard quality subdirectories
            scan_dirs = [tess_path, tess_path / "tessdata", tess_path / "tessdata_best"]

            for scan_dir in scan_dirs:
                if not scan_dir.exists():
                    continue

                if not os.access(scan_dir, os.R_OK | os.X_OK):
                    logger.warning(f"Anura: Cannot read directory for cleanup: {scan_dir}")
                    continue

                for file_path in scan_dir.iterdir():
                    if file_path.is_file() and file_path.suffix == ".tmp":
                        try:
                            # Only delete .tmp files older than 1 hour to avoid
                            # interrupting active downloads from other instances.
                            if time.time() - file_path.stat().st_mtime > 3600:
                                file_path.unlink()
                                logger.warning(
                                    f"Anura: Cleaned up orphaned temporary file: {file_path.name}"
                                )
                        except PermissionError:
                            logger.error(
                                f"Anura: Permission denied removing orphaned file in {scan_dir.name}"
                            )
                        except OSError:
                            logger.error(
                                f"Anura: Failed to remove orphaned file in {scan_dir.name}"
                            )
        except OSError:
            logger.error("Anura: Error scanning for orphaned temporary language files")

        installed = self.get_downloaded_codes(force=True)
        logger.info(
            f"Anura: tessdata directory ready. {len(installed)} language model(s) installed: {installed or ['none']}",
        )

    def get_downloaded_codes(self, force: bool = False) -> list[str]:
        """Returns codes of all installed language models (user + system bundled).

        Args:
            force: Force cache refresh even if not needed

        Returns:
            Sorted list of language codes
        """
        with self._cache_lock:
            need_update = self._need_update_cache
            if need_update or force:
                codes: set[str] = set()
                quality = settings.get_string("tessdata-model")

                # Enhanced logging: Log paths being checked with directory status
                tess_path = self._get_model_quality_dir(quality)
                logger.debug(f"Anura CacheManager: Scanning user tessdata directory: {tess_path}")
                logger.debug(f"Anura CacheManager: Scanning system tessdata directory: {TESSDATA_SYSTEM_DIR}")

                # User-downloaded models
                if tess_path.exists():
                    try:
                        user_files = [
                            f.name
                            for f in tess_path.iterdir()
                            if f.name.endswith(".traineddata") and not f.name.startswith("osd")
                        ]
                        logger.debug(
                            f"Anura CacheManager: User directory scanned, "
                            f"{len(user_files)} models found: {user_files}",
                        )
                        codes.update(Path(f).stem for f in user_files)
                    except OSError as e:
                        logger.exception(f"Anura CacheManager: Error reading user tessdata directory: {e}")
                else:
                    logger.debug(f"Anura CacheManager: User tessdata directory does not exist: {TESSDATA_DIR}")

                # Bundled system models
                system_path = Path(TESSDATA_SYSTEM_DIR)
                if system_path.exists():
                    try:
                        system_files = [
                            f.name
                            for f in system_path.iterdir()
                            if f.name.endswith(".traineddata") and not f.name.startswith("osd")
                        ]
                        logger.debug(
                            f"Anura CacheManager: System directory scanned, "
                            f"{len(system_files)} models found: {system_files}",
                        )
                        codes.update(Path(f).stem for f in system_files)
                    except OSError as e:
                        logger.exception(f"Anura CacheManager: Error reading system tessdata directory: {e}")
                else:
                    logger.debug(
                        f"Anura CacheManager: System tessdata directory does not exist: {TESSDATA_SYSTEM_DIR}",
                    )

                total_models = len(codes)
                logger.info(f"Anura CacheManager: Total language models discovered: {total_models} - {list(codes)}")
                self._downloaded_codes = list(codes)
                self._need_update_cache = False
            return sorted(self._downloaded_codes)

    def get_downloaded_languages(self, get_language_name: Callable, force: bool = False) -> list[str]:
        """Returns the names of the installed languages.

        Args:
            force: Force cache refresh
            get_language_name: Function to convert code to human-readable name

        Returns:
            List of human-readable language names
        """
        codes = self.get_downloaded_codes(force)
        return [get_language_name(code) for code in codes]

    def invalidate_cache(self) -> None:
        """Mark the cache as needing an update."""
        with self._cache_lock:
            self._need_update_cache = True

    def remove_model_file(self, code: str) -> bool:
        """Remove a model file from the filesystem.

        Args:
            code: Language code to remove

        Returns:
            True if successful, False otherwise
        """
        quality = settings.get_string("tessdata-model")
        path = self._get_model_quality_dir(quality) / f"{code}.traineddata"
        if not path.exists():
            return False

        try:
            path.unlink()
            self.invalidate_cache()
            logger.info(f"Anura: Model '{code}' removed successfully.")
            return True
        except PermissionError as e:
            logger.error(f"Anura: Permission denied removing language '{code}': {e}")
            return False
        except OSError as e:
            logger.error(f"Anura: OS error removing language '{code}': {e}")
            return False
