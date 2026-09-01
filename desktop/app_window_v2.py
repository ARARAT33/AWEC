"""AWEC Modern Desktop 3.0 UI Application Window.

Features complete UI rewrite:
- Multi-tab side panel: Dashboard, Seed Sites, Crawler & Deep Settings, Storage & IA, Languages & Editor, Live Logs.
- Dynamic translation switching for 10 languages across every widget.
- Complete deep configuration controls (workers, depth, rate limits, proxy, user-agent, custom headers JSON, IA S3 keys, extensions).
- Full signal integration with AWEC engine for live metrics, status badges, progress bars, and log streaming.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
    QWidget
)

from desktop.config_schema import AWECConfig
from desktop.i18n import LANGUAGES, TRANSLATIONS, get_translation, load_language_pack
from desktop.awec_desktop import Engine


class AWECMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = AWECConfig()
        self.lang = "en"
        self.t = get_translation("en")
        self.custom_langs: dict[str, dict[str, str]] = {}

        self.engine: Engine | None = None
        self.thread: QThread | None = None
        self.status_state = "stopped"

        self.setWindowTitle("AWEC Desktop 3.0 — Web Archive Engine")
        self.resize(1320, 880)
        self.setMinimumSize(1080, 720)

        self._build_ui()
        self._retranslate_ui()

    def _build_ui(self):
        root_widget = QWidget()
        self.setCentralWidget(root_widget)
        main_layout = QHBoxLayout(root_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Sidebar Navigation ──────────────────────────────────
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(240)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(18, 22, 18, 18)
        sidebar_layout.setSpacing(10)

        brand_label = QLabel("AWEC")
        brand_label.setObjectName("brandTitle")
        brand_sub = QLabel("Web Archive Engine 3.0")
        brand_sub.setObjectName("brandSubtitle")
        sidebar_layout.addWidget(brand_label)
        sidebar_layout.addWidget(brand_sub)
        sidebar_layout.addSpacing(15)

        self.nav_buttons: dict[str, QPushButton] = {}
        nav_items = [
            ("dashboard", "Dashboard"),
            ("sites", "Seed Sites"),
            ("crawler", "Crawler & Deep Settings"),
            ("storage", "Storage & S3"),
            ("languages", "Languages & Editor"),
            ("logs", "Live Logs")
        ]

        for key, default_text in nav_items:
            btn = QPushButton(default_text)
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, k=key: self.switch_page(k))
            self.nav_buttons[key] = btn
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch()

        self.sidebar_status = QLabel("READY")
        self.sidebar_status.setObjectName("statusBadgeStopped")
        self.sidebar_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(self.sidebar_status)

        main_layout.addWidget(sidebar)

        # ── Main Content Area ───────────────────────────────────
        self.pages_stack = QStackedWidget()
        main_layout.addWidget(self.pages_stack, 1)

        self._build_dashboard_page()
        self._build_sites_page()
        self._build_crawler_page()
        self._build_storage_page()
        self._build_languages_page()
        self._build_logs_page()

        self.switch_page("dashboard")

    def _create_page_wrapper(self, title_key: str) -> tuple[QWidget, QVBoxLayout, QLabel]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QLabel()
        header.setObjectName("pageHeader")
        layout.addWidget(header)
        return page, layout, header

    # ── 1. Dashboard Page ──────────────────────────────────────
    def _build_dashboard_page(self):
        page, layout, self.dashboard_header = self._create_page_wrapper("dashboard")

        # Metric Cards Grid
        grid = QGridLayout()
        grid.setSpacing(14)
        self.metric_cards: dict[str, tuple[QLabel, QLabel]] = {}

        metric_keys = ["queued", "enqueued", "pages", "found", "downloaded", "errors", "active", "speed"]
        for idx, key in enumerate(metric_keys):
            card = QFrame()
            card.setObjectName("metricCard")
            clayout = QVBoxLayout(card)
            clayout.setContentsMargins(12, 12, 12, 12)

            title_lbl = QLabel(key.upper())
            title_lbl.setObjectName("metricTitle")
            val_lbl = QLabel("0")
            val_lbl.setObjectName("metricValue")

            clayout.addWidget(title_lbl)
            clayout.addWidget(val_lbl)

            self.metric_cards[key] = (title_lbl, val_lbl)
            grid.addWidget(card, idx // 4, idx % 4)

        layout.addLayout(grid)

        # Current status & Live domain
        status_box = QGroupBox("Active Crawl Diagnostics")
        self.dashboard_group_boxes = [status_box]
        slayout = QFormLayout(status_box)

        self.domain_val_lbl = QLabel("—")
        self.domain_val_lbl.setStyleSheet("font-weight: bold; color: #3b71fe;")
        slayout.addRow("Active Domain:", self.domain_val_lbl)

        layout.addWidget(status_box)

        # Action Control Buttons
        action_layout = QHBoxLayout()
        action_layout.setSpacing(12)

        self.btn_start = QPushButton("Start Crawl")
        self.btn_start.setObjectName("primaryButton")
        self.btn_start.setMinimumHeight(42)
        self.btn_start.clicked.connect(self.start_crawl)

        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setObjectName("warningButton")
        self.btn_pause.setMinimumHeight(42)
        self.btn_pause.clicked.connect(self.pause_crawl)

        self.btn_stop = QPushButton("Stop Crawl")
        self.btn_stop.setObjectName("dangerButton")
        self.btn_stop.setMinimumHeight(42)
        self.btn_stop.clicked.connect(self.stop_crawl)

        action_layout.addWidget(self.btn_start)
        action_layout.addWidget(self.btn_pause)
        action_layout.addWidget(self.btn_stop)

        layout.addLayout(action_layout)

        # Log preview
        self.dash_logs = QPlainTextEdit()
        self.dash_logs.setReadOnly(True)
        self.dash_logs.setMaximumHeight(180)
        layout.addWidget(self.dash_logs)

        self.pages_stack.addWidget(page)

    # ── 2. Seed Sites Page ──────────────────────────────────────
    def _build_sites_page(self):
        page, layout, self.sites_header = self._create_page_wrapper("sites")

        self.site_list_widget = QListWidget()
        layout.addWidget(self.site_list_widget, 1)

        input_layout = QHBoxLayout()
        self.site_input = QLineEdit()
        self.site_input.setPlaceholderText("https://example.com")
        self.site_input.returnPressed.connect(self.add_seed_site)

        btn_add = QPushButton("Add Site")
        btn_add.setObjectName("primaryButton")
        btn_add.clicked.connect(self.add_seed_site)

        input_layout.addWidget(self.site_input, 1)
        input_layout.addWidget(btn_add)
        layout.addLayout(input_layout)

        ctrl_layout = QHBoxLayout()
        btn_remove = QPushButton("Remove Selected")
        btn_remove.clicked.connect(self.remove_seed_site)

        btn_clear = QPushButton("Clear All")
        btn_clear.clicked.connect(self.site_list_widget.clear)

        btn_import = QPushButton("Import TXT/JSON/DOCX")
        btn_import.clicked.connect(self.import_sites_file)

        ctrl_layout.addWidget(btn_remove)
        ctrl_layout.addWidget(btn_clear)
        ctrl_layout.addWidget(btn_import)
        ctrl_layout.addStretch()

        layout.addLayout(ctrl_layout)
        self.pages_stack.addWidget(page)

    # ── 3. Crawler & Deep Settings Page ─────────────────────────
    def _build_crawler_page(self):
        page, layout, self.crawler_header = self._create_page_wrapper("crawler")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(16)

        # General Group
        gen_group = QGroupBox("General Crawl Settings")
        gen_form = QFormLayout(gen_group)

        self.spin_workers = QSpinBox()
        self.spin_workers.setRange(1, 512)
        self.spin_workers.setValue(self.config.workers)
        gen_form.addRow("Workers:", self.spin_workers)

        self.spin_depth = QSpinBox()
        self.spin_depth.setRange(0, 100)
        self.spin_depth.setValue(self.config.max_depth)
        gen_form.addRow("Max Depth:", self.spin_depth)

        self.spin_max_urls = QSpinBox()
        self.spin_max_urls.setRange(0, 2000000000)
        self.spin_max_urls.setValue(self.config.max_urls)
        gen_form.addRow("Max URLs (0=Unlimited):", self.spin_max_urls)

        self.spin_delay = QDoubleSpinBox()
        self.spin_delay.setRange(0.0, 120.0)
        self.spin_delay.setDecimals(3)
        self.spin_delay.setValue(self.config.per_host_delay)
        gen_form.addRow("Per-Host Delay (sec):", self.spin_delay)

        self.input_max_file = QLineEdit(str(self.config.max_file_size))
        gen_form.addRow("Max File Size (Bytes):", self.input_max_file)

        self.input_ext = QPlainTextEdit(" ".join(self.config.file_types))
        self.input_ext.setMaximumHeight(60)
        gen_form.addRow("Extensions:", self.input_ext)

        self.chk_robots = QCheckBox("Respect robots.txt Rules")
        self.chk_robots.setChecked(self.config.respect_robots)
        gen_form.addRow(self.chk_robots)

        self.chk_same_domain = QCheckBox("Restrict Crawl to Seed Domains Only")
        self.chk_same_domain.setChecked(self.config.same_domain_only)
        gen_form.addRow(self.chk_same_domain)

        self.chk_download_files = QCheckBox("Automatically Download Matching Files")
        self.chk_download_files.setChecked(self.config.download_discovered_files)
        gen_form.addRow(self.chk_download_files)

        scroll_layout.addWidget(gen_group)

        # Deep Anti-Blocking & Network Group
        net_group = QGroupBox("Anti-Blocking & Deep Network Settings")
        net_form = QFormLayout(net_group)

        self.input_ua = QLineEdit(self.config.custom_user_agent)
        net_form.addRow("User-Agent:", self.input_ua)

        self.input_proxy = QLineEdit(self.config.proxy_url)
        self.input_proxy.setPlaceholderText("e.g. http://127.0.0.1:8080 or socks5://127.0.0.1:9050")
        net_form.addRow("Proxy URL:", self.input_proxy)

        self.input_headers = QPlainTextEdit(self.config.custom_headers_json)
        self.input_headers.setMaximumHeight(80)
        net_form.addRow("Custom Headers (JSON):", self.input_headers)

        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(1, 600)
        self.spin_timeout.setValue(self.config.request_timeout)
        net_form.addRow("Timeout (sec):", self.spin_timeout)

        self.spin_retries = QSpinBox()
        self.spin_retries.setRange(0, 20)
        self.spin_retries.setValue(self.config.max_retries)
        net_form.addRow("Max Retries:", self.spin_retries)

        self.spin_backoff = QDoubleSpinBox()
        self.spin_backoff.setRange(1.0, 10.0)
        self.spin_backoff.setDecimals(1)
        self.spin_backoff.setValue(self.config.retry_backoff_factor)
        net_form.addRow("Backoff Factor:", self.spin_backoff)

        scroll_layout.addWidget(net_group)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        self.pages_stack.addWidget(page)

    # ── 4. Storage & S3 Page ───────────────────────────────────
    def _build_storage_page(self):
        page, layout, self.storage_header = self._create_page_wrapper("storage")

        ia_group = QGroupBox("Internet Archive S3 Upload Credentials")
        ia_form = QFormLayout(ia_group)

        self.input_collection = QLineEdit(self.config.ia_collection)
        ia_form.addRow("IA Collection:", self.input_collection)

        self.input_identifier = QLineEdit(self.config.ia_identifier)
        ia_form.addRow("IA Identifier (Bucket):", self.input_identifier)

        self.input_creator = QLineEdit(self.config.ia_creator)
        ia_form.addRow("Creator:", self.input_creator)

        self.input_title = QLineEdit(self.config.ia_title)
        ia_form.addRow("Title:", self.input_title)

        self.input_access = QLineEdit(self.config.ia_access_key)
        self.input_access.setEchoMode(QLineEdit.EchoMode.Password)
        ia_form.addRow("S3 Access Key:", self.input_access)

        self.input_secret = QLineEdit(self.config.ia_secret_key)
        self.input_secret.setEchoMode(QLineEdit.EchoMode.Password)
        ia_form.addRow("S3 Secret Key:", self.input_secret)

        self.input_endpoint = QLineEdit(self.config.ia_endpoint)
        ia_form.addRow("S3 Endpoint URL:", self.input_endpoint)

        layout.addWidget(ia_group)

        fb_group = QGroupBox("Local Fallback Directory")
        fb_form = QFormLayout(fb_group)

        fb_row = QHBoxLayout()
        self.input_fallback = QLineEdit(self.config.fallback_dir)
        btn_browse = QPushButton("Browse")
        btn_browse.clicked.connect(self.browse_fallback_folder)
        fb_row.addWidget(self.input_fallback)
        fb_row.addWidget(btn_browse)

        fb_form.addRow("Fallback Folder:", fb_row)
        layout.addWidget(fb_group)

        layout.addStretch()
        self.pages_stack.addWidget(page)

    # ── 5. Languages & Editor Page ──────────────────────────────
    def _build_languages_page(self):
        page, layout, self.languages_header = self._create_page_wrapper("languages")

        top_row = QHBoxLayout()
        self.combo_lang = QComboBox()
        for code, name in LANGUAGES.items():
            self.combo_lang.addItem(f"{name} ({code})", code)
        self.combo_lang.addItem("Custom Language", "custom")
        self.combo_lang.currentIndexChanged.connect(self.on_language_changed)

        top_row.addWidget(self.combo_lang, 1)

        btn_import_lang = QPushButton("Import .awec.language")
        btn_import_lang.clicked.connect(self.import_language_file)
        btn_save_lang = QPushButton("Save Custom Pack")
        btn_save_lang.clicked.connect(self.export_language_file)

        top_row.addWidget(btn_import_lang)
        top_row.addWidget(btn_save_lang)
        layout.addLayout(top_row)

        editor_group = QGroupBox("Live Translation Pack Editor")
        elayout = QVBoxLayout(editor_group)

        self.editor_lang = QPlainTextEdit()
        self.editor_lang.setPlainText(json.dumps(self.t, ensure_ascii=False, indent=2))
        elayout.addWidget(self.editor_lang)

        btn_apply_custom = QPushButton("Apply Custom Editor Changes")
        btn_apply_custom.setObjectName("primaryButton")
        btn_apply_custom.clicked.connect(self.apply_custom_editor)
        elayout.addWidget(btn_apply_custom)

        layout.addWidget(editor_group)
        self.pages_stack.addWidget(page)

    # ── 6. Live Logs Page ───────────────────────────────────────
    def _build_logs_page(self):
        page, layout, self.logs_header = self._create_page_wrapper("logs")

        self.full_logs = QPlainTextEdit()
        self.full_logs.setReadOnly(True)
        layout.addWidget(self.full_logs, 1)

        btn_clear_logs = QPushButton("Clear Logs")
        btn_clear_logs.clicked.connect(self.full_logs.clear)
        layout.addWidget(btn_clear_logs)

        self.pages_stack.addWidget(page)

    # ── Navigation & Retranslation ──────────────────────────────
    def switch_page(self, page_key: str):
        for k, btn in self.nav_buttons.items():
            btn.setChecked(k == page_key)

        index_map = {
            "dashboard": 0, "sites": 1, "crawler": 2,
            "storage": 3, "languages": 4, "logs": 5
        }
        if page_key in index_map:
            self.pages_stack.setCurrentIndex(index_map[page_key])

    def _retranslate_ui(self):
        t = self.t
        self.setWindowTitle(t.get("title", "AWEC Desktop 3.0"))

        # Navigation buttons
        for k, btn in self.nav_buttons.items():
            btn.setText(t.get(k, k.title()))

        # Headers
        self.dashboard_header.setText(t.get("dashboard", "Dashboard"))
        self.sites_header.setText(t.get("sites", "Seed Sites"))
        self.crawler_header.setText(t.get("crawler", "Crawler & Deep Settings"))
        self.storage_header.setText(t.get("storage", "Storage & S3"))
        self.languages_header.setText(t.get("languages", "Languages & Editor"))
        self.logs_header.setText(t.get("logs", "Live Logs"))

        # Metric Titles
        for k, (title_lbl, _) in self.metric_cards.items():
            title_lbl.setText(t.get(k, k.upper()))

        # Action Buttons
        self.btn_start.setText(t.get("start", "Start Crawl"))
        self.btn_pause.setText(t.get("pause", "Pause"))
        self.btn_stop.setText(t.get("stop", "Stop Crawl"))

        # Status Sidebar
        self.update_status_badge(self.status_state)

    # ── Actions & Slots ─────────────────────────────────────────
    def update_status_badge(self, state: str):
        self.status_state = state
        t = self.t
        if state == "running":
            self.sidebar_status.setText(t.get("running", "RUNNING"))
            self.sidebar_status.setObjectName("statusBadgeRunning")
        elif state == "paused":
            self.sidebar_status.setText(t.get("paused", "PAUSED"))
            self.sidebar_status.setObjectName("statusBadgePaused")
        else:
            self.sidebar_status.setText(t.get("stopped", "READY"))
            self.sidebar_status.setObjectName("statusBadgeStopped")
        self.sidebar_status.setStyle(self.sidebar_status.style())

    def add_seed_site(self):
        url = self.site_input.text().strip()
        if url:
            if not any(self.site_list_widget.item(i).text() == url for i in range(self.site_list_widget.count())):
                self.site_list_widget.addItem(url)
            self.site_input.clear()

    def remove_seed_site(self):
        row = self.site_list_widget.currentRow()
        if row >= 0:
            self.site_list_widget.takeItem(row)

    def import_sites_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Sites", "", "Sites Files (*.txt *.json *.docx);;All Files (*)"
        )
        if not path:
            return
        p = Path(path)
        try:
            if p.suffix.lower() == ".json":
                data = json.loads(p.read_text(encoding="utf-8"))
                urls = data if isinstance(data, list) else data.get("seeds", [])
                for u in urls:
                    if isinstance(u, str):
                        self.site_list_widget.addItem(u.strip())
            else:
                lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
                for line in lines:
                    line = line.strip()
                    if line.startswith(("http://", "https://")):
                        self.site_list_widget.addItem(line)
        except Exception as e:
            QMessageBox.warning(self, "Import Error", f"Failed to import sites: {e}")

    def browse_fallback_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Fallback Directory")
        if folder:
            self.input_fallback.setText(folder)

    def on_language_changed(self, index: int):
        code = self.combo_lang.itemData(index) or self.combo_lang.currentData()
        if code == "custom":
            return
        if code in LANGUAGES:
            self.lang = code
            self.t = get_translation(code)
            self.editor_lang.setPlainText(json.dumps(self.t, ensure_ascii=False, indent=2))
            self._retranslate_ui()

    def apply_custom_editor(self):
        try:
            custom_data = json.loads(self.editor_lang.toPlainText())
            self.t = custom_data
            self._retranslate_ui()
            QMessageBox.information(self, "AWEC", "Custom language applied successfully!")
        except Exception as e:
            QMessageBox.warning(self, "JSON Error", f"Invalid JSON translation format: {e}")

    def import_language_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Language Pack", "", "AWEC Language (*.awec.language *.json);;All Files (*)"
        )
        if not path:
            return
        try:
            pack = load_language_pack(path)
            self.t = pack
            self.editor_lang.setPlainText(json.dumps(pack, ensure_ascii=False, indent=2))
            self._retranslate_ui()
            QMessageBox.information(self, "AWEC", "Language pack imported and applied!")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not load language pack: {e}")

    def export_language_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Language Pack", "custom.awec.language", "AWEC Language (*.awec.language)"
        )
        if not path:
            return
        try:
            Path(path).write_text(self.editor_lang.toPlainText(), encoding="utf-8")
            QMessageBox.information(self, "AWEC", f"Saved language pack to {path}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save language pack: {e}")

    def build_config_from_ui(self) -> AWECConfig:
        seeds = [self.site_list_widget.item(i).text() for i in range(self.site_list_widget.count())]
        exts = [x.strip() for x in self.input_ext.toPlainText().replace(",", " ").split() if x.strip()]

        try:
            mfs = int(self.input_max_file.text())
        except ValueError:
            mfs = -1

        cfg = AWECConfig(
            seeds=seeds,
            workers=self.spin_workers.value(),
            max_depth=self.spin_depth.value(),
            max_urls=self.spin_max_urls.value(),
            per_host_delay=self.spin_delay.value(),
            max_file_size=mfs,
            file_types=exts or ["*"],
            respect_robots=self.chk_robots.isChecked(),
            same_domain_only=self.chk_same_domain.isChecked(),
            download_discovered_files=self.chk_download_files.isChecked(),
            custom_user_agent=self.input_ua.text(),
            proxy_url=self.input_proxy.text(),
            custom_headers_json=self.input_headers.toPlainText(),
            request_timeout=self.spin_timeout.value(),
            max_retries=self.spin_retries.value(),
            retry_backoff_factor=self.spin_backoff.value(),
            ia_collection=self.input_collection.text(),
            ia_identifier=self.input_identifier.text(),
            ia_creator=self.input_creator.text(),
            ia_title=self.input_title.text(),
            ia_access_key=self.input_access.text(),
            ia_secret_key=self.input_secret.text(),
            ia_endpoint=self.input_endpoint.text(),
            fallback_dir=self.input_fallback.text(),
            language=self.lang
        )
        return cfg

    # ── Crawler Execution ───────────────────────────────────────
    def start_crawl(self):
        if self.site_list_widget.count() == 0:
            QMessageBox.warning(self, "AWEC", "Please add at least one seed site before starting.")
            return

        if self.engine and self.engine.stop_event and not self.engine.stop_event.is_set():
            if getattr(self.engine, 'is_paused', False):
                self.engine.is_paused = False
                self.update_status_badge("running")
                self.append_log("▶ Crawl resumed")
                return

        cfg = self.build_config_from_ui()
        self.engine = Engine(cfg)
        self.thread = QThread()
        self.engine.moveToThread(self.thread)

        self.thread.started.connect(self.engine.start)
        self.engine.log.connect(self.append_log)
        self.engine.stats.connect(self.update_stats)
        self.engine.finished.connect(self.on_crawl_finished)

        self.thread.start()
        self.update_status_badge("running")
        self.btn_start.setEnabled(False)
        self.append_log("🚀 AWEC Engine started...")

    def pause_crawl(self):
        if self.engine:
            self.engine.is_paused = True
            self.update_status_badge("paused")
            self.append_log("⏸ Crawl paused")
            self.btn_start.setEnabled(True)

    def stop_crawl(self):
        if self.engine:
            self.engine.stop()
            self.update_status_badge("stopped")
            self.append_log("🛑 Crawl stop requested...")
            self.btn_start.setEnabled(True)

    @Slot(dict)
    def update_stats(self, stats: dict):
        for k, (title_lbl, val_lbl) in self.metric_cards.items():
            if k in stats:
                val = stats[k]
                val_lbl.setText(f"{val:,}" if isinstance(val, (int, float)) else str(val))
        if "active_domain" in stats:
            self.domain_val_lbl.setText(stats["active_domain"])

    @Slot(str)
    def append_log(self, msg: str):
        t_str = datetime.now().strftime("%H:%M:%S")
        entry = f"[{t_str}] {msg}"
        self.dash_logs.appendPlainText(entry)
        self.full_logs.appendPlainText(entry)

    @Slot(str)
    def on_crawl_finished(self, summary_json: str):
        self.update_status_badge("stopped")
        self.btn_start.setEnabled(True)
        self.append_log(f"🏁 Finished: {summary_json}")
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread = None
            self.engine = None
