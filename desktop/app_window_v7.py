"""AWEC Desktop UI v7 - compact control center on top of v6."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QMessageBox, QProgressBar, QPushButton, QHBoxLayout, QVBoxLayout, QWidget

from desktop.app_window_v6 import AWECMainWindow as V6MainWindow


class AWECMainWindow(V6MainWindow):
    """Adds a lightweight control strip, progress indicator and safer controls."""

    def _dashboard(self):
        super()._dashboard()
        # The base dashboard already owns the main controls; add a compact live strip.
        page = self.pages.widget(0)
        layout = page.layout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("Crawl progress • %p%")
        layout.insertWidget(2, self.progress)
        strip = QHBoxLayout()
        self.health_label = QLabel("● READY")
        self.queue_label = QLabel("Queue: 0")
        self.retry_label = QLabel("Retries: 0")
        health = QPushButton("⚡ Health Check")
        health.clicked.connect(self.health_check)
        strip.addWidget(self.health_label)
        strip.addWidget(self.queue_label)
        strip.addWidget(self.retry_label)
        strip.addStretch()
        strip.addWidget(health)
        layout.insertLayout(3, strip)
        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._refresh_control_strip)
        self._ui_timer.start(1000)

    def _refresh_control_strip(self):
        if not hasattr(self, "progress"):
            return
        if not self.running:
            return
        queued = self.metrics.get("queued")
        urls = self.metrics.get("enqueued")
        try:
            q = int(queued.text().replace(",", "")) if queued else 0
            total = int(urls.text().replace(",", "")) if urls else 0
            self.queue_label.setText(f"Queue: {q:,}")
            if total > 0:
                done = max(0, total - q)
                self.progress.setValue(min(100, int(done * 100 / total)))
        except (ValueError, TypeError):
            pass

    def _stats(self, s):
        super()._stats(s)
        if hasattr(self, "queue_label"):
            self.queue_label.setText(f"Queue: {int(s.get('queued', 0)):,}")
        if hasattr(self, "retry_label"):
            self.retry_label.setText(f"Retries: {int(s.get('retries', 0)):,}")

    def health_check(self):
        """Fast local/runtime check; does not expose or persist secrets."""
        checks = []
        try:
            import PySide6  # noqa: F401
            checks.append("✓ PySide6")
        except Exception as exc:
            checks.append(f"✗ PySide6: {exc}")
        try:
            import boto3  # noqa: F401
            checks.append("✓ boto3")
        except Exception as exc:
            checks.append(f"✗ boto3: {exc}")
        c = self._cfg()
        checks.append("✓ Collection Name" if c.ia_collection else "✗ Collection Name missing")
        checks.append("✓ Item Name" if c.ia_identifier else "✗ Item Name missing")
        checks.append("✓ IA credentials" if c.ia_access_key and c.ia_secret_key else "⚠ IA credentials missing")
        checks.append("✓ Seed URL" if c.seeds else "✗ Seed URL missing")
        text = "AWEC Health Check\n\n" + "\n".join(checks)
        self.health_label.setText("● HEALTH CHECKED")
        self._log(text)
        QMessageBox.information(self, "AWEC • Health Check", text)

    def _finished(self, msg):
        super()._finished(msg)
        if hasattr(self, "progress"):
            self.progress.setValue(100)
        if hasattr(self, "health_label"):
            self.health_label.setText("● READY")
