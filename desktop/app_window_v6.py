"""AWEC Desktop UI v6 - hardened orchestration layer over the runtime-safe v5 UI."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtWidgets import QMessageBox

from desktop.app_window_v5 import AWECMainWindow as V5MainWindow
from awec.archive.ia import IAUploader


class AWECMainWindow(V5MainWindow):
    """Adds a mandatory IA preflight gate and safer start behavior."""

    def _ia_preflight(self):
        c = self._cfg()
        if not getattr(c, "destination_archive", True):
            return True, "ARCHIVE_DESTINATION_DISABLED"
        if not c.ia_access_key or not c.ia_secret_key:
            return False, "IA_CREDENTIALS_MISSING"
        if not c.ia_collection:
            return False, "COLLECTION_NAME_REQUIRED"
        if not c.ia_identifier:
            return False, "ITEM_NAME_REQUIRED"
        uploader = IAUploader(
            c.ia_access_key,
            c.ia_secret_key,
            c.ia_identifier,
            c.ia_endpoint or "https://s3.us.archive.org",
            collection=c.ia_collection,
            title=c.ia_title,
            creator=c.ia_creator,
            description=c.ia_description,
        )
        return uploader.validate_destination(force=True)

    def start_crawl(self):
        if self.running:
            return super().start_crawl()
        try:
            ok, msg = self._ia_preflight()
        except Exception as exc:
            ok, msg = False, f"IA_PREFLIGHT_FAILED: {exc}"
        self._log(("✓ " if ok else "✗ ") + msg)
        self.ia_status.setText(("✓ " if ok else "✗ ") + msg)
        if not ok:
            self._page("ia")
            QMessageBox.warning(self, "AWEC • Internet Archive", msg)
            return
        try:
            self.config = self._cfg()
            self.config.save(Path.home() / "AWEC" / "config.json")
        except Exception as exc:
            self._log(f"⚠️ Could not save config before start: {exc}")
        return super().start_crawl()

    def check_ia(self):
        """Force a fresh destination check instead of using cached state."""
        c = self._cfg()
        if not c.ia_access_key or not c.ia_secret_key:
            self.ia_status.setText("✗ IA_CREDENTIALS_MISSING")
            self._log("✗ IA_CREDENTIALS_MISSING")
            return
        if not c.ia_collection or not c.ia_identifier:
            self.ia_status.setText("⚠ Collection Name and Item Name are required")
            return
        try:
            uploader = IAUploader(
                c.ia_access_key, c.ia_secret_key, c.ia_identifier,
                c.ia_endpoint or "https://s3.us.archive.org",
                collection=c.ia_collection, title=c.ia_title,
                creator=c.ia_creator, description=c.ia_description,
            )
            ok, msg = uploader.validate_destination(force=True)
            self.ia_status.setText(("✓ " if ok else "✗ ") + msg)
            self._log(("✓ " if ok else "✗ ") + msg)
        except Exception as exc:
            self.ia_status.setText("✗ IA CHECK FAILED: " + str(exc))
            self._log("❌ IA check failed: " + str(exc))
