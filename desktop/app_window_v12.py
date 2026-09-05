"""AWEC Desktop v12 — clean light command center with responsive navigation."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Slot
from PySide6.QtWidgets import (
    QFileDialog, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QStackedWidget, QTextBrowser, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget, QSplitter, QProgressBar, QPlainTextEdit
)

from desktop.app_window_v11 import AWECMainWindow as V11MainWindow
from desktop.crawler_engine_v12 import find_resumable_crawls


class AWECMainWindow(V11MainWindow):
    """v12 UI: dashboard, crawler/FANTI, Resume Center and Archive Explorer."""

    SETTINGS_FILE = Path.home() / "AWEC" / "v12_settings.json"

    def __init__(self):
        self._v12 = {}
        super().__init__()
        self._build_archive_page()
        self._rebuild_sidebar()
        self._make_layout_responsive()
        self._load_v12_settings()
        self._refresh_resume_list()
        self._refresh_archive_explorer()
        self._resume_timer = QTimer(self)
        self._resume_timer.timeout.connect(self._refresh_resume_list)
        self._resume_timer.start(2500)
        self.setWindowTitle("AWEC v12 • Web Archive Command Center")

    # ------------------------------------------------------------------
    # Responsive shell / navigation
    # ------------------------------------------------------------------
    def _make_layout_responsive(self):
        self.setMinimumSize(1180, 760)
        self.resize(max(self.width(), 1380), max(self.height(), 860))
        side = self.findChild(QWidget, "sidebar")
        if side:
            side.setMinimumWidth(235)
            side.setMaximumWidth(300)
        pages = getattr(self, "pages", None)
        if pages:
            pages.setMinimumWidth(850)
        root = self.centralWidget()
        if not root:
            return
        for w in root.findChildren(QWidget):
            cls = w.metaObject().className()
            if cls in {"QLineEdit", "QComboBox", "QSpinBox", "QDoubleSpinBox"}:
                w.setMinimumWidth(max(w.minimumWidth(), 250))
            elif cls in {"QPlainTextEdit", "QTextEdit", "QTextBrowser", "QListWidget", "QTreeWidget"}:
                w.setMinimumWidth(max(w.minimumWidth(), 300))
            elif cls == "QGroupBox":
                w.setMinimumWidth(max(w.minimumWidth(), 500))
        for form in root.findChildren(QFormLayout):
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

    def _rebuild_sidebar(self):
        """Put every navigation item in one deliberate order; never stack inserts by position."""
        side = self.findChild(QWidget, "sidebar")
        if not side or not side.layout():
            return
        layout = side.layout()
        # Remove all existing nav buttons while keeping brand labels, spacers and status.
        buttons = []
        for key, button in list(getattr(self, "nav", {}).items()):
            layout.removeWidget(button)
            buttons.append(button)
        for attr in ("nav_v10", "nav_v12_resume", "nav_v12_archive"):
            button = getattr(self, attr, None)
            if button:
                layout.removeWidget(button)
                buttons.append(button)
        # Reuse the original navigation buttons and connect through one dispatcher.
        wanted = []
        for key in ("dashboard", "sites", "crawler", "ia", "logs"):
            button = getattr(self, "nav", {}).get(key)
            if button:
                wanted.append((key, button))
        language = getattr(self, "nav_v10", None)
        if language:
            language.setText("🌐 Languages & Names")
            wanted.append(("language", language))
        resume = getattr(self, "nav_v12_resume", None)
        if not resume:
            resume = QPushButton("♻️ Resume Center")
            resume.setObjectName("navButton")
            resume.setCheckable(True)
            resume.clicked.connect(lambda: self._page_v12("resume"))
            self.nav_v12_resume = resume
        wanted.append(("resume", resume))
        archive = getattr(self, "nav_v12_archive", None)
        if not archive:
            archive = QPushButton("🌐 Archive Explorer")
            archive.setObjectName("navButton")
            archive.setCheckable(True)
            archive.clicked.connect(lambda: self._page_v12("archive"))
            self.nav_v12_archive = archive
        wanted.append(("archive", archive))

        # Find the bottom status widget and insert the navigation immediately before it.
        status = getattr(self, "status", None)
        status_index = layout.indexOf(status) if status else -1
        for _, button in wanted:
            if status_index >= 0:
                layout.insertWidget(status_index, button)
                status_index += 1
            else:
                layout.addWidget(button)
        # Remove any duplicate/old nav buttons not in the desired set.
        keep = {id(button) for _, button in wanted}
        for button in buttons:
            if id(button) not in keep:
                button.setParent(None)
        self._set_nav_selection("dashboard")

    def _set_nav_selection(self, key):
        for button in getattr(self, "nav", {}).values():
            button.setChecked(False)
        for attr in ("nav_v10", "nav_v12_resume", "nav_v12_archive"):
            button = getattr(self, attr, None)
            if button:
                button.setChecked(False)
        if key in getattr(self, "nav", {}):
            self.nav[key].setChecked(True)
        elif key == "language" and hasattr(self, "nav_v10"):
            self.nav_v10.setChecked(True)
        elif key == "resume" and hasattr(self, "nav_v12_resume"):
            self.nav_v12_resume.setChecked(True)
        elif key == "archive" and hasattr(self, "nav_v12_archive"):
            self.nav_v12_archive.setChecked(True)

    # ------------------------------------------------------------------
    # Dashboard — rebuilt instead of inheriting the cramped v7/v11 inserts
    # ------------------------------------------------------------------
    def _dashboard(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(12)

        hero = QFrame()
        hero.setObjectName("v11Hero")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(22, 16, 22, 16)
        title = QLabel("AWEC v12 • ARCHIVE COMMAND CENTER")
        title.setObjectName("v11HeroTitle")
        subtitle = QLabel("Mirror the reachable public resource graph • WARC + local mirror • adaptive FANTI transport")
        subtitle.setObjectName("v11HeroSubtitle")
        hl.addWidget(title)
        hl.addWidget(subtitle)
        layout.addWidget(hero)

        status_row = QHBoxLayout()
        self.v11_mirror_card = QLabel("Mirror: ready")
        self.v11_mirror_card.setObjectName("v11Card")
        self.v11_archive_card = QLabel("Archive: WARC + local mirror")
        self.v11_archive_card.setObjectName("v11Card")
        self.v11_network_card = QLabel("Network: adaptive FANTI / standard")
        self.v11_network_card.setObjectName("v11Card")
        for card in (self.v11_mirror_card, self.v11_archive_card, self.v11_network_card):
            status_row.addWidget(card, 1)
        layout.addLayout(status_row)

        progress_box = QFrame()
        pb_layout = QVBoxLayout(progress_box)
        pb_layout.setContentsMargins(0, 0, 0, 0)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Crawl progress • %p%")
        pb_layout.addWidget(self.progress)
        layout.addWidget(progress_box)

        strip = QHBoxLayout()
        self.health_label = QLabel("● READY")
        self.queue_label = QLabel("Queue: 0")
        self.retry_label = QLabel("Retries: 0")
        strip.addWidget(self.health_label)
        strip.addSpacing(18)
        strip.addWidget(self.queue_label)
        strip.addSpacing(18)
        strip.addWidget(self.retry_label)
        strip.addStretch()
        health = QPushButton("⚡ Health Check")
        health.clicked.connect(self.health_check)
        strip.addWidget(health)
        layout.addLayout(strip)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        self.metrics = {}
        for i, (key, text) in enumerate((
            ("queued", "QUEUED"), ("enqueued", "URLS"), ("pages", "PAGES"), ("found", "FILES"),
            ("downloaded", "UPLOADED"), ("errors", "ERRORS"), ("active", "ACTIVE"), ("speed", "STATE"),
        )):
            card = QFrame()
            card.setObjectName("metricCard")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 10, 14, 10)
            cl.setSpacing(4)
            cl.addWidget(QLabel(text, objectName="metricTitle"))
            value = QLabel("0", objectName="metricValue")
            cl.addWidget(value)
            self.metrics[key] = value
            grid.addWidget(card, i // 4, i % 4)
        layout.addLayout(grid)

        quick = QGroupBox("🚀 Quick Start")
        qf = QFormLayout(quick)
        self.quick = QLineEdit()
        self.quick.setPlaceholderText("https://example.com")
        self.quick.returnPressed.connect(self.start_crawl)
        qf.addRow("Seed URL", self.quick)
        self.domain = QLabel("—")
        qf.addRow("Active domain", self.domain)
        layout.addWidget(quick)

        actions = QHBoxLayout()
        self.start_btn = QPushButton("▶  Start Crawl")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.clicked.connect(self.start_crawl)
        self.pause_btn = QPushButton("⏸  Pause")
        self.pause_btn.setObjectName("warningButton")
        self.pause_btn.clicked.connect(self.pause_crawl)
        self.stop_btn = QPushButton("■  Stop")
        self.stop_btn.setObjectName("dangerButton")
        self.stop_btn.clicked.connect(self.stop_crawl)
        for button in (self.start_btn, self.pause_btn, self.stop_btn):
            actions.addWidget(button, 1)
        layout.addLayout(actions)

        log_box = QGroupBox("Live Activity")
        log_layout = QVBoxLayout(log_box)
        self.dashboard_log = QPlainTextEdit()
        self.dashboard_log.setReadOnly(True)
        self.dashboard_log.setMinimumHeight(150)
        self.dashboard_log.setPlaceholderText("Engine messages appear here…")
        log_layout.addWidget(self.dashboard_log)
        layout.addWidget(log_box, 1)
        self.pages.addWidget(page)

        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._refresh_control_strip)
        self._ui_timer.start(1000)

        # Resume Center and Archive Explorer are intentionally separate pages.
        self._build_resume_page()

    def _refresh_control_strip(self):
        if not hasattr(self, "progress") or not self.running:
            return
        try:
            q = int(self.metrics["queued"].text().replace(",", ""))
            total = int(self.metrics["enqueued"].text().replace(",", ""))
            self.queue_label.setText(f"Queue: {q:,}")
            if total > 0:
                self.progress.setValue(min(100, max(0, int((total - q) * 100 / total))))
        except (ValueError, TypeError, KeyError):
            pass

    @staticmethod
    def _fmt_bytes(n: int) -> str:
        value = float(max(0, n))
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{n} B"

    def health_check(self):
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

    # ------------------------------------------------------------------
    # Crawler / FANTI
    # ------------------------------------------------------------------
    def _crawler(self):
        super()._crawler()
        page = self.pages.widget(2)
        scroll = page.findChild(QScrollArea)
        if scroll and scroll.widget() and scroll.widget().layout():
            host, cl = scroll.widget(), scroll.widget().layout()
        else:
            host = QWidget()
            cl = QVBoxLayout(host)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(host)
            page.layout().addWidget(scroll, 1)

        scope = QGroupBox("🕸️ Site Copy / Link Policy")
        sf = QFormLayout(scope)
        self.v12_follow_links = QCheckBox("Follow links found inside pages")
        self.v12_follow_links.setChecked(True)
        sf.addRow(self.v12_follow_links)
        self.v12_external = QCheckBox("Also crawl external navigation links")
        self.v12_external.setChecked(False)
        sf.addRow(self.v12_external)
        self.v12_embedded = QCheckBox("Always fetch embedded assets — images, CSS, JS, video, audio, iframes, fonts and files")
        self.v12_embedded.setChecked(True)
        self.v12_embedded.setEnabled(False)
        sf.addRow(self.v12_embedded)
        note = QLabel("www, apex and subdomains are treated as the same site. External embedded resources are fetched even when external navigation is off. No authentication/CAPTCHA/paywall/access-control bypass is attempted.")
        note.setWordWrap(True)
        sf.addRow(note)
        cl.addWidget(scope)

        storage = QGroupBox("💾 TMPCRAWL • Local Storage Governor")
        f = QFormLayout(storage)
        self.v12_tmp = QLineEdit(str(Path.home() / "AWEC" / "tmpcrawl"))
        f.addRow("Temporary folder", self.v12_tmp)
        choose = QPushButton("Choose…")
        choose.clicked.connect(self._choose_tmp)
        f.addRow("", choose)
        self.v12_limit = QSpinBox(); self.v12_limit.setRange(0, 1024 * 1024); self.v12_limit.setValue(0); self.v12_limit.setSuffix(" MB")
        f.addRow("TMP limit (0 = unlimited)", self.v12_limit)
        self.v12_reserve = QSpinBox(); self.v12_reserve.setRange(256, 1024 * 1024); self.v12_reserve.setValue(2048); self.v12_reserve.setSuffix(" MB")
        f.addRow("Minimum free disk reserve", self.v12_reserve)
        self.v12_keep = QCheckBox("Keep local mirror after crawl"); self.v12_keep.setChecked(True); f.addRow(self.v12_keep)
        self.v12_purge = QCheckBox("After verified IA upload, purge payload from TMPCRAWL"); self.v12_purge.setChecked(False); f.addRow(self.v12_purge)
        cl.addWidget(storage)

        ia = QGroupBox("☁️ Internet Archive • Live Publisher")
        f2 = QFormLayout(ia)
        self.v12_live = QCheckBox("Upload each successfully fetched resource to IA immediately"); self.v12_live.setChecked(True); f2.addRow(self.v12_live)
        self.v12_verify = QCheckBox("Verify remote object after upload"); self.v12_verify.setChecked(True); f2.addRow(self.v12_verify)
        n = QLabel("IA publishing is asynchronous: crawl throughput is not blocked by individual uploads and failed uploads remain visible in logs."); n.setWordWrap(True); f2.addRow(n)
        cl.addWidget(ia)

        fanti = QGroupBox("⚡ FANTI • Advanced Transport Settings")
        fl = QGridLayout(fanti); fl.setHorizontalSpacing(22); fl.setVerticalSpacing(10)
        self.fanti_widgets = {}
        def combo(row, col, label, key, values):
            w = QComboBox()
            for text, data in values: w.addItem(text, data)
            self.fanti_widgets[key] = w
            fl.addWidget(QLabel(label), row, col * 2); fl.addWidget(w, row, col * 2 + 1)
        def spin(row, col, label, key, lo, hi, val, step=1, suffix=""):
            w = QDoubleSpinBox() if isinstance(val, float) else QSpinBox()
            w.setRange(lo, hi); w.setValue(val); w.setSingleStep(step); w.setSuffix(suffix)
            self.fanti_widgets[key] = w
            fl.addWidget(QLabel(label), row, col * 2); fl.addWidget(w, row, col * 2 + 1)
        def check(row, col, label, key, val):
            w = QCheckBox(label); w.setChecked(val); self.fanti_widgets[key] = w
            fl.addWidget(w, row, col * 2, 1, 2)
        combo(0, 0, "UA profile", "fanti_user_agent_profile", [("Archive", "archive"), ("Desktop", "desktop"), ("Custom", "custom")])
        combo(0, 1, "Header profile", "fanti_header_profile", [("Default Archive", "Default Archive"), ("Browser-like", "Browser-like"), ("Minimal", "Minimal")])
        spin(1, 0, "Minimum delay", "fanti_min_delay", 0.0, 120.0, 0.05, 0.01, " s")
        spin(1, 1, "Maximum delay", "fanti_max_delay", 0.0, 600.0, 8.0, 0.1, " s")
        spin(2, 0, "Initial delay", "fanti_initial_delay", 0.0, 120.0, 0.15, 0.01, " s")
        spin(2, 1, "Delay jitter", "delay_jitter_sec", 0.0, 60.0, 0.25, 0.01, " s")
        check(3, 0, "Adaptive pacing", "fanti_adaptive_pacing", True); check(3, 1, "Adaptive concurrency", "fanti_adaptive_concurrency", True)
        spin(4, 0, "Minimum concurrency", "fanti_min_concurrency", 1, 512, 1)
        spin(4, 1, "Initial concurrency", "fanti_initial_concurrency", 1, 512, 8)
        spin(5, 0, "Maximum concurrency", "fanti_max_concurrency", 1, 1024, 32)
        spin(5, 1, "Max retries", "fanti_max_retries", 0, 100, 5)
        combo(6, 0, "Backoff strategy", "fanti_backoff_strategy", [(x, x) for x in ("full_jitter", "equal_jitter", "decorrelated", "fixed", "exponential")])
        spin(6, 1, "Base retry delay", "fanti_base_retry_delay", 0.0, 600.0, 1.0, 0.1, " s")
        spin(7, 0, "Max retry delay", "fanti_max_retry_delay", 0.0, 3600.0, 60.0, 1.0, " s")
        check(7, 1, "Circuit breaker enabled", "fanti_circuit_breaker_enabled", True)
        spin(8, 0, "Failure threshold", "fanti_circuit_breaker_threshold", 1, 1000, 5)
        spin(8, 1, "Breaker cooldown", "fanti_circuit_breaker_cooldown", 0.0, 3600.0, 30.0, 1.0, " s")
        spin(9, 0, "Max connections", "fanti_max_connections", 1, 4096, 160)
        spin(9, 1, "Connections / host", "fanti_max_connections_per_host", 1, 1024, 32)
        spin(10, 0, "Keep-alive timeout", "fanti_keepalive_timeout", 0.0, 3600.0, 30.0, 1.0, " s")
        spin(10, 1, "DNS timeout", "fanti_dns_timeout", 0.1, 600.0, 10.0, 0.1, " s")
        spin(11, 0, "Connect timeout", "fanti_connect_timeout", 0.1, 600.0, 10.0, 0.1, " s")
        spin(11, 1, "Read timeout", "fanti_read_timeout", 0.1, 3600.0, 30.0, 0.1, " s")
        spin(12, 0, "Total timeout", "fanti_total_timeout", 0.1, 3600.0, 60.0, 0.1, " s")
        spin(12, 1, "Max redirects", "fanti_max_redirects", 0, 100, 10)
        check(13, 0, "Allow cross-domain redirects", "fanti_allow_cross_domain_redirects", True)
        combo(13, 1, "Cookie policy", "fanti_cookie_policy", [(x, x) for x in ("disabled", "per-request", "per-host", "per-job", "persistent")])
        spin(14, 0, "Bandwidth limit", "fanti_bandwidth_limit_bytes_per_sec", 0, 1024 * 1024 * 1024, 0, 1024, " B/s")
        spin(14, 1, "Browser timeout", "fanti_browser_timeout", 0.1, 600.0, 30.0, 0.1, " s")
        check(15, 0, "Enable browser rendering", "fanti_enable_browser_rendering", False)
        check(15, 1, "Diagnostic mode", "fanti_diagnostic_mode", False)
        help_text = QLabel("FANTI controls transport resilience, pacing, connection pooling, retries, cookies and diagnostics. It does not bypass authentication, CAPTCHA, paywalls, robots restrictions or access controls.")
        help_text.setWordWrap(True); fl.addWidget(help_text, 16, 0, 1, 4)
        cl.addWidget(fanti)
        cl.addStretch()
        scroll.setWidgetResizable(True)
        self._make_layout_responsive()

    # ------------------------------------------------------------------
    # Resume Center
    # ------------------------------------------------------------------
    def _build_resume_page(self):
        if hasattr(self, "_resume_page"):
            return
        p = QWidget(); l = QVBoxLayout(p); l.setContentsMargins(30, 24, 30, 24); l.setSpacing(12)
        title = QLabel("♻️ Resume Center"); title.setObjectName("pageHeader"); l.addWidget(title)
        sub = QLabel("Continue interrupted crawls from their existing state database without restarting the frontier."); sub.setObjectName("pageSubtitle"); sub.setWordWrap(True); l.addWidget(sub)
        self.resume_summary = QLabel("Scanning TMPCRAWL…"); self.resume_summary.setObjectName("infoBadge"); l.addWidget(self.resume_summary)
        self.resume_table = QTreeWidget(); self.resume_table.setHeaderLabels(["Crawl", "Pending", "In progress", "Completed", "Failed", "Storage path"])
        self.resume_table.setMinimumHeight(360); self.resume_table.setRootIsDecorated(False); self.resume_table.itemDoubleClicked.connect(lambda *_: self._resume_selected())
        self.resume_table.setColumnWidth(0, 180); self.resume_table.setColumnWidth(1, 100); self.resume_table.setColumnWidth(2, 110); self.resume_table.setColumnWidth(3, 110); self.resume_table.setColumnWidth(4, 90)
        l.addWidget(self.resume_table, 1)
        row = QHBoxLayout()
        b = QPushButton("♻️ Resume Selected"); b.setObjectName("primaryButton"); b.clicked.connect(self._resume_selected); row.addWidget(b)
        r = QPushButton("↻ Refresh Now"); r.clicked.connect(self._refresh_resume_list); row.addWidget(r)
        o = QPushButton("📂 Open TMPCRAWL"); o.clicked.connect(self._open_resume_storage); row.addWidget(o); row.addStretch(); l.addLayout(row)
        self.pages.addWidget(p); self._resume_page = p

    def _page(self, k):
        super()._page(k)
        self._set_nav_selection(k)

    def _page_v10_language(self):
        super()._page_v10_language()
        self._set_nav_selection("language")

    def _page_v12(self, key):
        if key == "archive":
            self.pages.setCurrentWidget(self._archive_page); self._set_nav_selection("archive"); self._refresh_archive_explorer()
        elif key == "resume":
            self.pages.setCurrentWidget(self._resume_page); self._set_nav_selection("resume"); self._refresh_resume_list()

    def _open_resume_storage(self):
        path = Path(self.v12_tmp.text()); path.mkdir(parents=True, exist_ok=True); self._open_path(path)

    @staticmethod
    def _open_path(path):
        try:
            if sys.platform.startswith("win"): os.startfile(str(path))
            elif sys.platform == "darwin": subprocess.Popen(["open", str(path)])
            else: subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Archive Explorer
    # ------------------------------------------------------------------
    def _build_archive_page(self):
        p = QWidget(); l = QVBoxLayout(p); l.setContentsMargins(30, 24, 30, 24); l.setSpacing(12)
        h = QHBoxLayout(); title = QLabel("🌐 Archive Explorer"); title.setObjectName("pageHeader"); h.addWidget(title); h.addStretch(); refresh = QPushButton("↻ Refresh"); refresh.clicked.connect(self._refresh_archive_explorer); h.addWidget(refresh); l.addLayout(h)
        sub = QLabel("Browse the local resource mirror, preview downloaded files, and open the configured Internet Archive item."); sub.setObjectName("pageSubtitle"); sub.setWordWrap(True); l.addWidget(sub)
        split = QSplitter(Qt.Orientation.Horizontal); split.setChildrenCollapsible(False)
        self.archive_tree = QTreeWidget(); self.archive_tree.setHeaderLabels(["Downloaded site / resource"]); self.archive_tree.setMinimumWidth(430); self.archive_tree.itemDoubleClicked.connect(self._preview_selected); split.addWidget(self.archive_tree)
        right = QWidget(); right.setMinimumWidth(520); rl = QVBoxLayout(right); self.archive_info = QLabel("Select a crawl or file."); self.archive_info.setWordWrap(True); rl.addWidget(self.archive_info); self.archive_preview = QTextBrowser(); self.archive_preview.setOpenExternalLinks(True); rl.addWidget(self.archive_preview, 1)
        br = QHBoxLayout(); self.open_local = QPushButton("📄 Open Preview"); self.open_local.clicked.connect(self._preview_selected); br.addWidget(self.open_local); self.open_ia = QPushButton("☁️ Open IA Item"); self.open_ia.clicked.connect(self._open_ia); br.addWidget(self.open_ia); br.addStretch(); rl.addLayout(br); split.addWidget(right); split.setStretchFactor(0, 1); split.setStretchFactor(1, 2); split.setSizes([500, 900]); l.addWidget(split, 1)
        self.pages.addWidget(p); self._archive_page = p

    def _refresh_archive_explorer(self):
        if not hasattr(self, "archive_tree"):
            return
        self.archive_tree.clear(); root = Path(self.v12_tmp.text()) if hasattr(self, "v12_tmp") else Path.home() / "AWEC" / "tmpcrawl"
        for site in sorted(root.glob("crawls/*/site"), key=lambda p: p.parent.stat().st_mtime, reverse=True):
            top = QTreeWidgetItem([f"🗂 {site.parent.name} • {site}"]); top.setData(0, Qt.ItemDataRole.UserRole, str(site)); self.archive_tree.addTopLevelItem(top); count = 0
            try:
                for f in site.rglob("*"):
                    if f.is_file():
                        it = QTreeWidgetItem([str(f.relative_to(site))]); it.setData(0, Qt.ItemDataRole.UserRole, str(f)); top.addChild(it); count += 1
                        if count >= 20000: break
            except OSError:
                pass
            top.setText(0, top.text(0) + f" • {count:,} files")
        self.archive_tree.expandToDepth(0)

    def _preview_selected(self, *_):
        it = self.archive_tree.currentItem()
        if not it: return
        p = Path(it.data(0, Qt.ItemDataRole.UserRole) or "")
        if p.is_dir(): return
        try: size = p.stat().st_size
        except OSError: size = 0
        self.archive_info.setText(f"📄 {p}\nSize: {size:,} bytes")
        if p.suffix.lower() in {".html", ".htm", ".xhtml"}:
            self.archive_preview.setSource(QUrl.fromLocalFile(str(p)))
        else:
            try: self.archive_preview.setPlainText(p.read_text(encoding="utf-8", errors="replace")[:500000])
            except Exception: self.archive_preview.setPlainText(f"Binary resource: {p.name}")

    def _open_ia(self):
        c = self._cfg(); ident = str(getattr(c, "ia_identifier", "")).strip()
        if not ident:
            QMessageBox.information(self, "AWEC", "Configure an Internet Archive Item Name first."); return
        self._open_path(Path("https://archive.org/details/" + ident))

    # ------------------------------------------------------------------
    # Settings / config
    # ------------------------------------------------------------------
    def _choose_tmp(self):
        p = QFileDialog.getExistingDirectory(self, "Choose TMPCRAWL folder", self.v12_tmp.text())
        if p:
            self.v12_tmp.setText(p); self._save_v12_settings(); self._refresh_resume_list(); self._refresh_archive_explorer()

    def _load_v12_settings(self):
        try: self._v12 = json.loads(self.SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception: self._v12 = {}
        if not hasattr(self, "v12_tmp"):
            return
        self.v12_tmp.setText(self._v12.get("tmpcrawl_dir", self.v12_tmp.text()))
        self.v12_limit.setValue(int(self._v12.get("max_local_storage_mb", 0)))
        self.v12_reserve.setValue(int(self._v12.get("min_free_space_mb", 2048)))
        self.v12_keep.setChecked(bool(self._v12.get("keep_local_mirror", True)))
        self.v12_purge.setChecked(bool(self._v12.get("purge_local_files_after_upload", False)))
        self.v12_live.setChecked(bool(self._v12.get("archive_upload_live", True)))
        self.v12_verify.setChecked(bool(self._v12.get("archive_verify_uploads", True)))
        self.v12_follow_links.setChecked(bool(self._v12.get("follow_links", True)))
        self.v12_external.setChecked(bool(self._v12.get("follow_external_domains", False)))
        for key, w in getattr(self, "fanti_widgets", {}).items():
            if key not in self._v12: continue
            try:
                val = self._v12[key]
                if isinstance(w, QComboBox):
                    idx = w.findData(val); w.setCurrentIndex(idx if idx >= 0 else 0)
                elif isinstance(w, QCheckBox): w.setChecked(bool(val))
                else: w.setValue(val)
            except Exception: pass

    def _save_v12_settings(self):
        if not hasattr(self, "v12_tmp"):
            return
        self._v12 = {
            "tmpcrawl_dir": self.v12_tmp.text(),
            "max_local_storage_mb": self.v12_limit.value(),
            "min_free_space_mb": self.v12_reserve.value(),
            "keep_local_mirror": self.v12_keep.isChecked(),
            "purge_local_files_after_upload": self.v12_purge.isChecked(),
            "archive_upload_live": self.v12_live.isChecked(),
            "archive_verify_uploads": self.v12_verify.isChecked(),
            "follow_links": self.v12_follow_links.isChecked(),
            "follow_external_domains": self.v12_external.isChecked(),
            "resume_dir": self._v12.get("resume_dir", ""),
        }
        for key, w in getattr(self, "fanti_widgets", {}).items():
            self._v12[key] = w.currentData() if isinstance(w, QComboBox) else (w.isChecked() if isinstance(w, QCheckBox) else w.value())
        self.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.SETTINGS_FILE.write_text(json.dumps(self._v12, ensure_ascii=False, indent=2), encoding="utf-8")

    def _cfg(self):
        c = super()._cfg(); self._save_v12_settings()
        for k, v in self._v12.items(): setattr(c, k, v)
        c.fallback_dir = self.v12_tmp.text()
        c.follow_links = self.v12_follow_links.isChecked()
        c.follow_external_domains = self.v12_external.isChecked()
        c.download_discovered_files = True
        c.file_types = ["*"]
        c.max_file_size = -1
        return c

    def start_crawl(self):
        self._save_v12_settings()
        super().start_crawl()
        QTimer.singleShot(500, self._refresh_resume_list)

    # ------------------------------------------------------------------
    # Resume / stats / lifecycle
    # ------------------------------------------------------------------
    def _resume_selected(self):
        item = self.resume_table.currentItem() if hasattr(self, "resume_table") else None
        path = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if not path and hasattr(self, "resume_list"):
            item = self.resume_list.currentItem(); path = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not path:
            return
        self._v12["resume_dir"] = path; self._save_v12_settings(); self._log(f"♻️ Resume requested: {path}"); self.start_crawl()

    def _refresh_resume_list(self):
        if not hasattr(self, "resume_table"):
            return
        root = Path(self.v12_tmp.text()) if hasattr(self, "v12_tmp") else Path.home() / "AWEC" / "tmpcrawl"
        try: items = find_resumable_crawls(root)
        except Exception as exc: items = []; self._log(f"⚠️ Resume scan failed: {exc}")
        self.resume_table.clear(); total_pending = total_active = total_done = total_failed = 0
        for x in items:
            counts = x.get("counts", {}); path = x.get("path", "")
            pending = int(counts.get("pending", 0)); active = int(counts.get("in_progress", 0)); done = int(counts.get("completed", 0)); failed = int(counts.get("failed", 0))
            total_pending += pending; total_active += active; total_done += done; total_failed += failed
            ti = QTreeWidgetItem([x.get("crawl_id", "unknown"), f"{pending:,}", f"{active:,}", f"{done:,}", f"{failed:,}", path]); ti.setData(0, Qt.ItemDataRole.UserRole, path); self.resume_table.addTopLevelItem(ti)
        if not items:
            ti = QTreeWidgetItem(["No interrupted crawls", "0", "0", "0", "0", str(root)]); self.resume_table.addTopLevelItem(ti)
        if hasattr(self, "resume_summary"):
            self.resume_summary.setText(f"{len(items):,} resumable crawl(s) • pending {total_pending:,} • in progress {total_active:,} • completed {total_done:,} • failed {total_failed:,}")

    @Slot(dict)
    def _stats(self, s):
        super()._stats(s)
        if hasattr(self, "queue_label"): self.queue_label.setText(f"Queue: {int(s.get('queued', 0)):,}")
        if hasattr(self, "retry_label"): self.retry_label.setText(f"Retries: {int(s.get('retries', 0)):,}")
        if hasattr(self, "v11_mirror_card"): self.v11_mirror_card.setText(f"Mirror: {int(s.get('mirrored', 0)):,} resources • {self._fmt_bytes(int(s.get('mirror_bytes', 0)))}")
        if hasattr(self, "v11_network_card"): self.v11_network_card.setText(f"Network: {s.get('status', 'ready')} • FANTI adaptive transport")

    @Slot(str)
    def _finished(self, msg):
        super()._finished(msg)
        if hasattr(self, "progress"): self.progress.setValue(100)
        if hasattr(self, "health_label"): self.health_label.setText("● READY")
        self._v12["resume_dir"] = ""; self._save_v12_settings()
        QTimer.singleShot(200, self._refresh_resume_list); QTimer.singleShot(500, self._refresh_archive_explorer)

    def closeEvent(self, event):
        try:
            if hasattr(self, "_resume_timer"): self._resume_timer.stop()
        except Exception: pass
        super().closeEvent(event)
