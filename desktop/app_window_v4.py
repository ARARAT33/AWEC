"""AWEC Desktop UI v4.

A cleaner, smaller and more reliable PySide6 UI.  The UI deliberately keeps
configuration close to the action that uses it and exposes Internet Archive
as: Collection Name + Item Name + credentials + metadata.
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QWidget
)

from desktop.config_schema import AWECConfig
from desktop.engine import Engine
from awec.archive.ia import IAUploader


class AWECMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = AWECConfig()
        self.engine: Engine | None = None
        self.thread: QThread | None = None
        self.running = False
        self.setWindowTitle("AWEC • Web Archive Engine")
        self.resize(1280, 820)
        self.setMinimumSize(1050, 700)
        self._build()
        self._load_config()

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_l = QHBoxLayout(root)
        root_l.setContentsMargins(0, 0, 0, 0)
        root_l.setSpacing(0)

        side = QFrame(objectName="sidebar")
        side.setFixedWidth(225)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(18, 22, 18, 18)
        title = QLabel("AWEC", objectName="brandTitle")
        subtitle = QLabel("Web Archive Engine", objectName="brandSubtitle")
        sl.addWidget(title)
        sl.addWidget(subtitle)
        sl.addSpacing(22)
        self.nav = {}
        for key, text in [("dashboard", "Dashboard"), ("sites", "Sites"), ("crawler", "Crawler"), ("ia", "Internet Archive"), ("logs", "Live Logs")]:
            b = QPushButton(text, objectName="navButton")
            b.setCheckable(True)
            b.clicked.connect(lambda _, k=key: self._page(k))
            self.nav[key] = b
            sl.addWidget(b)
        sl.addStretch()
        self.status = QLabel("● READY", objectName="statusBadgeStopped")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(self.status)
        root_l.addWidget(side)

        self.pages = QStackedWidget()
        root_l.addWidget(self.pages, 1)
        self._dashboard()
        self._sites()
        self._crawler()
        self._ia()
        self._logs()
        self._page("dashboard")

    def _page_shell(self, title: str, subtitle: str):
        p = QWidget()
        l = QVBoxLayout(p)
        l.setContentsMargins(30, 26, 30, 26)
        l.setSpacing(16)
        h = QLabel(title, objectName="pageHeader")
        s = QLabel(subtitle, objectName="pageSubtitle")
        l.addWidget(h)
        l.addWidget(s)
        return p, l

    def _dashboard(self):
        p, l = self._page_shell("Dashboard", "Start a crawl, watch the counters and see the current domain.")
        grid = QGridLayout(); grid.setSpacing(12)
        self.metrics = {}
        for i, (key, label) in enumerate([("queued", "Queued"), ("enqueued", "URLs"), ("pages", "Pages"), ("found", "Files"), ("downloaded", "Uploaded"), ("errors", "Errors"), ("active", "Active"), ("speed", "State")]):
            card = QFrame(objectName="metricCard"); cl = QVBoxLayout(card)
            a = QLabel(label.upper(), objectName="metricTitle"); v = QLabel("0", objectName="metricValue")
            cl.addWidget(a); cl.addWidget(v); self.metrics[key] = v
            grid.addWidget(card, i // 4, i % 4)
        l.addLayout(grid)
        box = QGroupBox("Quick Start")
        f = QFormLayout(box)
        self.quick = QLineEdit(); self.quick.setPlaceholderText("https://example.com")
        self.quick.returnPressed.connect(self.start_crawl)
        f.addRow("Seed URL", self.quick)
        self.domain = QLabel("—")
        f.addRow("Active domain", self.domain)
        l.addWidget(box)
        row = QHBoxLayout()
        self.start_btn = QPushButton("▶  Start Crawl", objectName="primaryButton"); self.start_btn.clicked.connect(self.start_crawl)
        self.pause_btn = QPushButton("⏸  Pause", objectName="warningButton"); self.pause_btn.clicked.connect(self.pause_crawl)
        self.stop_btn = QPushButton("■  Stop", objectName="dangerButton"); self.stop_btn.clicked.connect(self.stop_crawl)
        row.addWidget(self.start_btn); row.addWidget(self.pause_btn); row.addWidget(self.stop_btn)
        l.addLayout(row)
        self.dashboard_log = QPlainTextEdit(); self.dashboard_log.setReadOnly(True); self.dashboard_log.setPlaceholderText("Engine messages appear here…")
        l.addWidget(self.dashboard_log, 1)
        self.pages.addWidget(p)

    def _sites(self):
        p, l = self._page_shell("Seed Sites", "Add the sites AWEC is allowed to crawl.")
        self.site_list = QListWidget(); l.addWidget(self.site_list, 1)
        row = QHBoxLayout(); self.site_input = QLineEdit(); self.site_input.setPlaceholderText("example.com or https://example.com")
        self.site_input.returnPressed.connect(self.add_site)
        add = QPushButton("＋ Add Site", objectName="primaryButton"); add.clicked.connect(self.add_site)
        row.addWidget(self.site_input, 1); row.addWidget(add); l.addLayout(row)
        row2 = QHBoxLayout(); rem = QPushButton("Remove Selected"); rem.clicked.connect(self.remove_site); clear = QPushButton("Clear All"); clear.clicked.connect(self.site_list.clear)
        row2.addWidget(rem); row2.addWidget(clear); row2.addStretch(); l.addLayout(row2)
        self.pages.addWidget(p)

    def _crawler(self):
        p, l = self._page_shell("Crawler", "Only the controls that affect the crawl are shown here.")
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        c = QWidget(); cl = QVBoxLayout(c); cl.setSpacing(14)
        general = QGroupBox("General") ; f = QFormLayout(general)
        self.workers = QSpinBox(); self.workers.setRange(1, 512); f.addRow("Workers", self.workers)
        self.depth = QSpinBox(); self.depth.setRange(0, 100); f.addRow("Max depth", self.depth)
        self.max_urls = QSpinBox(); self.max_urls.setRange(0, 2000000000); f.addRow("Max URLs (0 = unlimited)", self.max_urls)
        self.delay = QDoubleSpinBox(); self.delay.setRange(0, 120); self.delay.setDecimals(2); f.addRow("Per-host delay (s)", self.delay)
        self.timeout = QSpinBox(); self.timeout.setRange(1, 600); f.addRow("Timeout (s)", self.timeout)
        self.retries = QSpinBox(); self.retries.setRange(0, 20); f.addRow("Retries", self.retries)
        self.same_domain = QCheckBox("Stay on seed domains"); f.addRow(self.same_domain)
        self.robots = QCheckBox("Respect robots.txt"); f.addRow(self.robots)
        cl.addWidget(general)
        net = QGroupBox("Network / FANTI") ; nf = QFormLayout(net)
        self.net_mode = QComboBox(); self.net_mode.addItem("STANDARD", "standard"); self.net_mode.addItem("FANTI", "fanti"); nf.addRow("Mode", self.net_mode)
        self.ua = QLineEdit(); nf.addRow("User-Agent", self.ua)
        self.ua_rotate = QCheckBox("Rotate User-Agent pool"); nf.addRow(self.ua_rotate)
        self.jitter = QDoubleSpinBox(); self.jitter.setRange(0, 30); self.jitter.setDecimals(2); nf.addRow("Delay jitter (s)", self.jitter)
        self.cookies = QCheckBox("Persistent cookie sessions"); nf.addRow(self.cookies)
        self.ssl = QCheckBox("Verify TLS certificates"); nf.addRow(self.ssl)
        self.proxy = QLineEdit(); self.proxy.setPlaceholderText("optional HTTP/SOCKS proxy") ; nf.addRow("Proxy", self.proxy)
        cl.addWidget(net)
        scroll.setWidget(c); l.addWidget(scroll, 1)
        self.pages.addWidget(p)

    def _ia(self):
        p, l = self._page_shell("Internet Archive", "Collection must already exist. A missing item is created automatically by the first upload.")
        box = QGroupBox("Archive Destination") ; f = QFormLayout(box)
        self.ia_collection = QLineEdit(); self.ia_collection.setPlaceholderText("collection-name")
        self.ia_item = QLineEdit(); self.ia_item.setPlaceholderText("item-name")
        self.ia_title = QLineEdit(); self.ia_title.setPlaceholderText("Human-readable item title")
        self.ia_creator = QLineEdit(); self.ia_creator.setPlaceholderText("Creator")
        self.ia_desc = QPlainTextEdit(); self.ia_desc.setMaximumHeight(72)
        self.ia_access = QLineEdit(); self.ia_access.setEchoMode(QLineEdit.EchoMode.Password)
        self.ia_secret = QLineEdit(); self.ia_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.ia_endpoint = QLineEdit(); self.ia_endpoint.setText("https://s3.us.archive.org")
        f.addRow("Collection Name", self.ia_collection)
        f.addRow("Item Name", self.ia_item)
        f.addRow("Item Title", self.ia_title)
        f.addRow("Creator", self.ia_creator)
        f.addRow("Description", self.ia_desc)
        f.addRow("S3 Access Key", self.ia_access)
        f.addRow("S3 Secret Key", self.ia_secret)
        f.addRow("S3 Endpoint", self.ia_endpoint)
        l.addWidget(box)
        self.ia_status = QLabel("● Not checked", objectName="infoBadge")
        l.addWidget(self.ia_status)
        row = QHBoxLayout()
        check = QPushButton("✓ Check Collection / Item"); check.clicked.connect(self.check_ia)
        save = QPushButton("Save Settings", objectName="primaryButton"); save.clicked.connect(self.save_config)
        row.addWidget(check); row.addWidget(save); row.addStretch(); l.addLayout(row)
        hint = QLabel("Flow: Collection check → Item check → if item is missing, first upload creates it → crawl continues.", objectName="hint")
        hint.setWordWrap(True); l.addWidget(hint)
        l.addStretch()
        self.pages.addWidget(p)

    def _logs(self):
        p, l = self._page_shell("Live Logs", "Full engine output and errors.")
        self.logs = QPlainTextEdit(); self.logs.setReadOnly(True); l.addWidget(self.logs, 1)
        b = QPushButton("Clear Logs"); b.clicked.connect(self.logs.clear); l.addWidget(b, 0, Qt.AlignmentFlag.AlignRight)
        self.pages.addWidget(p)

    def _page(self, key):
        idx = {"dashboard": 0, "sites": 1, "crawler": 2, "ia": 3, "logs": 4}[key]
        self.pages.setCurrentIndex(idx)
        for k, b in self.nav.items(): b.setChecked(k == key)

    def add_site(self):
        u = self.site_input.text().strip()
        if not u: return
        if not u.startswith(("http://", "https://")): u = "https://" + u
        if not any(self.site_list.item(i).text() == u for i in range(self.site_list.count())): self.site_list.addItem(u)
        self.site_input.clear()

    def remove_site(self):
        r = self.site_list.currentRow()
        if r >= 0: self.site_list.takeItem(r)

    def _config_from_ui(self):
        seeds = [self.site_list.item(i).text() for i in range(self.site_list.count())]
        if self.quick.text().strip():
            u = self.quick.text().strip(); u = u if u.startswith(("http://", "https://")) else "https://" + u
            if u not in seeds: seeds.append(u)
        return AWECConfig(
            seeds=seeds, network_mode=self.net_mode.currentData(), workers=self.workers.value(), max_depth=self.depth.value(),
            max_urls=self.max_urls.value(), per_host_delay=self.delay.value(), request_timeout=self.timeout.value(),
            max_retries=self.retries.value(), same_domain_only=self.same_domain.isChecked(), respect_robots=self.robots.isChecked(),
            custom_user_agent=self.ua.text(), ua_rotation_enabled=self.ua_rotate.isChecked(), delay_jitter_sec=self.jitter.value(),
            cookie_jar_enabled=self.cookies.isChecked(), verify_ssl=self.ssl.isChecked(), proxy_url=self.proxy.text(),
            ia_collection=self.ia_collection.text().strip(), ia_identifier=self.ia_item.text().strip(), ia_title=self.ia_title.text().strip(),
            ia_creator=self.ia_creator.text().strip(), ia_description=self.ia_desc.toPlainText().strip(), ia_access_key=self.ia_access.text(),
            ia_secret_key=self.ia_secret.text(), ia_endpoint=self.ia_endpoint.text().strip() or "https://s3.us.archive.org",
            language="en"
        )

    def _load_config(self):
        cfg_path = Path.home() / "AWEC" / "config.json"
        try:
            self.config = AWECConfig.load(cfg_path)
        except Exception:
            self.config = AWECConfig()
        c = self.config
        for u in c.seeds: self.site_list.addItem(u)
        self.workers.setValue(c.workers); self.depth.setValue(c.max_depth); self.max_urls.setValue(c.max_urls); self.delay.setValue(c.per_host_delay)
        self.timeout.setValue(c.request_timeout); self.retries.setValue(c.max_retries); self.same_domain.setChecked(c.same_domain_only); self.robots.setChecked(c.respect_robots)
        self.net_mode.setCurrentIndex(1 if c.network_mode == "fanti" else 0); self.ua.setText(c.custom_user_agent); self.ua_rotate.setChecked(c.ua_rotation_enabled)
        self.jitter.setValue(c.delay_jitter_sec); self.cookies.setChecked(c.cookie_jar_enabled); self.ssl.setChecked(c.verify_ssl); self.proxy.setText(c.proxy_url)
        self.ia_collection.setText(c.ia_collection); self.ia_item.setText(c.ia_identifier); self.ia_title.setText(c.ia_title); self.ia_creator.setText(c.ia_creator)
        self.ia_desc.setPlainText(c.ia_description); self.ia_access.setText(c.ia_access_key); self.ia_secret.setText(c.ia_secret_key); self.ia_endpoint.setText(c.ia_endpoint)

    def save_config(self):
        try:
            c = self._config_from_ui(); p = Path.home() / "AWEC" / "config.json"; c.save(p); self.config = c
            self.ia_status.setText("✓ Settings saved locally")
            self._log("💾 Configuration saved")
        except Exception as e: QMessageBox.critical(self, "AWEC", f"Could not save configuration:\n{e}")

    def check_ia(self):
        collection = self.ia_collection.text().strip(); item = self.ia_item.text().strip()
        if not collection or not item:
            self.ia_status.setText("⚠ Collection Name and Item Name are required")
            return
        if not self.ia_access.text() or not self.ia_secret.text():
            self.ia_status.setText("⚠ S3 credentials are required")
            return
        try:
            uploader = IAUploader(self.ia_access.text(), self.ia_secret.text(), item, self.ia_endpoint.text().strip() or "https://s3.us.archive.org", collection=collection)
            ok, msg = uploader.validate_destination()
            self.ia_status.setText(("✓ " if ok else "✗ ") + msg)
            self._log(("✓ " if ok else "✗ ") + msg)
        except Exception as e:
            self.ia_status.setText("✗ IA CHECK FAILED: " + str(e))
            self._log("❌ IA check failed: " + str(e))

    def start_crawl(self):
        if self.running:
            if self.engine and self.engine.is_paused:
                self.engine.is_paused = False; self.status.setText("● RUNNING"); self._log("▶ Crawl resumed")
            return
        if self.quick.text().strip(): self.add_quick_seed()
        if self.site_list.count() == 0:
            QMessageBox.warning(self, "AWEC", "Add at least one seed URL."); return
        try: cfg = self._config_from_ui()
        except Exception as e: QMessageBox.critical(self, "AWEC", str(e)); return
        self.engine = Engine(cfg); self.thread = QThread(); self.engine.moveToThread(self.thread)
        self.thread.started.connect(self.engine.start); self.engine.log.connect(self._log); self.engine.stats.connect(self._stats); self.engine.finished.connect(self._finished)
        self.thread.start(); self.running = True; self.status.setText("● RUNNING"); self.start_btn.setEnabled(False); self._log("🚀 AWEC engine started")

    def add_quick_seed(self):
        u = self.quick.text().strip(); u = u if u.startswith(("http://", "https://")) else "https://" + u
        if not any(self.site_list.item(i).text() == u for i in range(self.site_list.count())): self.site_list.addItem(u)

    def pause_crawl(self):
        if self.engine: self.engine.is_paused = True; self.status.setText("● PAUSED"); self._log("⏸ Crawl paused"); self.start_btn.setEnabled(True)

    def stop_crawl(self):
        if self.engine: self.engine.stop(); self.status.setText("● STOPPING"); self._log("🛑 Stop requested")

    @Slot(dict)
    def _stats(self, s):
        for k, v in s.items():
            if k in self.metrics: self.metrics[k].setText(f"{v:,}" if isinstance(v, (int, float)) else str(v))
        if "active_domain" in s: self.domain.setText(str(s["active_domain"]))

    @Slot(str)
    def _log(self, msg):
        self.logs.appendPlainText(msg); self.dashboard_log.appendPlainText(msg)

    @Slot(str)
    def _finished(self, msg):
        self.running = False; self.start_btn.setEnabled(True); self.status.setText("● READY")
        self._log("🏁 Crawl finished: " + msg)
        if self.thread:
            self.thread.quit()

    def closeEvent(self, event):
        if self.engine: self.engine.stop()
        if self.thread and self.thread.isRunning(): self.thread.quit(); self.thread.wait(2000)
        event.accept()
