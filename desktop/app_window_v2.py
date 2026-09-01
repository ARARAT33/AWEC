"""AWEC Modern Desktop 3.0 UI Application Window.

Features:
- Multi-tab navigation: Dashboard, Seed Sites, Crawler & Deep Settings, Storage & S3, Languages & Interactive Editor, Live Logs.
- Full dynamic re-translation of every UI string when selecting or changing language.
- Interactive key-value table editor allowing live custom naming for any button, section, label, or metric.
- Deep anti-blocking controls (User-Agent rotation, delay jitter, cookie sessions, auto Sec-Fetch headers, SSL verify, proxy).
- Zero / quota local storage management controls.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
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

        self.engine: Engine | None = None
        self.thread: QThread | None = None
        self.status_state = "stopped"

        self.setWindowTitle("AWEC Desktop 3.0 — High-Speed Web Archive Engine")
        self.resize(1340, 900)
        self.setMinimumSize(1080, 740)

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

        self.brand_label = QLabel("AWEC")
        self.brand_label.setObjectName("brandTitle")
        self.brand_sub = QLabel("Web Archive Engine 3.0")
        self.brand_sub.setObjectName("brandSubtitle")
        sidebar_layout.addWidget(self.brand_label)
        sidebar_layout.addWidget(self.brand_sub)
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

        # ── Main Content Stack ──────────────────────────────────
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

        status_box = QGroupBox("Active Crawl Diagnostics")
        self.status_box_ref = status_box
        slayout = QFormLayout(status_box)

        self.domain_val_lbl = QLabel("—")
        self.domain_val_lbl.setStyleSheet("font-weight: bold; color: #3b71fe;")
        slayout.addRow("Active Domain:", self.domain_val_lbl)

        layout.addWidget(status_box)

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

        self.btn_add_site = QPushButton("Add Site")
        self.btn_add_site.setObjectName("primaryButton")
        self.btn_add_site.clicked.connect(self.add_seed_site)

        input_layout.addWidget(self.site_input, 1)
        input_layout.addWidget(self.btn_add_site)
        layout.addLayout(input_layout)

        ctrl_layout = QHBoxLayout()
        self.btn_remove_site = QPushButton("Remove Selected")
        self.btn_remove_site.clicked.connect(self.remove_seed_site)

        self.btn_clear_sites = QPushButton("Clear All")
        self.btn_clear_sites.clicked.connect(self.site_list_widget.clear)

        self.btn_import_sites = QPushButton("Import TXT/JSON/DOCX")
        self.btn_import_sites.clicked.connect(self.import_sites_file)

        ctrl_layout.addWidget(self.btn_remove_site)
        ctrl_layout.addWidget(self.btn_clear_sites)
        ctrl_layout.addWidget(self.btn_import_sites)
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

        # General Settings Group
        self.grp_general = QGroupBox("General Crawl Settings")
        gen_form = QFormLayout(self.grp_general)

        self.spin_workers = QSpinBox()
        self.spin_workers.setRange(1, 512)
        self.spin_workers.setValue(self.config.workers)
        self.lbl_workers = QLabel("Workers:")
        gen_form.addRow(self.lbl_workers, self.spin_workers)

        self.spin_depth = QSpinBox()
        self.spin_depth.setRange(0, 100)
        self.spin_depth.setValue(self.config.max_depth)
        self.lbl_depth = QLabel("Max Depth:")
        gen_form.addRow(self.lbl_depth, self.spin_depth)

        self.spin_max_urls = QSpinBox()
        self.spin_max_urls.setRange(0, 2000000000)
        self.spin_max_urls.setValue(self.config.max_urls)
        self.lbl_max_urls = QLabel("Max URLs:")
        gen_form.addRow(self.lbl_max_urls, self.spin_max_urls)

        self.spin_delay = QDoubleSpinBox()
        self.spin_delay.setRange(0.0, 120.0)
        self.spin_delay.setDecimals(3)
        self.spin_delay.setValue(self.config.per_host_delay)
        self.lbl_delay = QLabel("Per-Host Delay:")
        gen_form.addRow(self.lbl_delay, self.spin_delay)

        self.input_max_file = QLineEdit(str(self.config.max_file_size))
        self.lbl_max_file = QLabel("Max File Size (Bytes):")
        gen_form.addRow(self.lbl_max_file, self.input_max_file)

        self.input_ext = QPlainTextEdit(" ".join(self.config.file_types))
        self.input_ext.setMaximumHeight(60)
        self.lbl_ext = QLabel("Extensions:")
        gen_form.addRow(self.lbl_ext, self.input_ext)

        self.chk_robots = QCheckBox("Respect robots.txt Rules")
        self.chk_robots.setChecked(self.config.respect_robots)
        gen_form.addRow(self.chk_robots)

        self.chk_same_domain = QCheckBox("Restrict Crawl to Seed Domains Only")
        self.chk_same_domain.setChecked(self.config.same_domain_only)
        gen_form.addRow(self.chk_same_domain)

        self.chk_download_files = QCheckBox("Automatically Download Matching Files")
        self.chk_download_files.setChecked(self.config.download_discovered_files)
        gen_form.addRow(self.chk_download_files)

        scroll_layout.addWidget(self.grp_general)

        # Deep Anti-Blocking & Network Group
        self.grp_network = QGroupBox("Anti-Blocking & Deep Network Settings")
        net_form = QFormLayout(self.grp_network)

        self.input_ua = QLineEdit(self.config.custom_user_agent)
        self.lbl_ua = QLabel("User-Agent:")
        net_form.addRow(self.lbl_ua, self.input_ua)

        self.chk_ua_rotation = QCheckBox("Enable Smart User-Agent Rotation Pool")
        self.chk_ua_rotation.setChecked(self.config.ua_rotation_enabled)
        net_form.addRow(self.chk_ua_rotation)

        self.spin_jitter = QDoubleSpinBox()
        self.spin_jitter.setRange(0.0, 30.0)
        self.spin_jitter.setDecimals(2)
        self.spin_jitter.setValue(self.config.delay_jitter_sec)
        self.lbl_jitter = QLabel("Delay Jitter (sec):")
        net_form.addRow(self.lbl_jitter, self.spin_jitter)

        self.chk_cookie_jar = QCheckBox("Enable Persistent Cookie Jar Sessions")
        self.chk_cookie_jar.setChecked(self.config.cookie_jar_enabled)
        net_form.addRow(self.chk_cookie_jar)

        self.chk_auto_headers = QCheckBox("Auto-Generate Browser Sec-Fetch & Accept Headers")
        self.chk_auto_headers.setChecked(self.config.auto_headers_enabled)
        net_form.addRow(self.chk_auto_headers)

        self.chk_verify_ssl = QCheckBox("Verify SSL Certificates")
        self.chk_verify_ssl.setChecked(self.config.verify_ssl)
        net_form.addRow(self.chk_verify_ssl)

        self.input_proxy = QLineEdit(self.config.proxy_url)
        self.lbl_proxy = QLabel("Proxy URL:")
        net_form.addRow(self.lbl_proxy, self.input_proxy)

        self.input_headers = QPlainTextEdit(self.config.custom_headers_json)
        self.input_headers.setMaximumHeight(70)
        self.lbl_headers = QLabel("Custom Headers (JSON):")
        net_form.addRow(self.lbl_headers, self.input_headers)

        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(1, 600)
        self.spin_timeout.setValue(self.config.request_timeout)
        self.lbl_timeout = QLabel("Timeout (sec):")
        net_form.addRow(self.lbl_timeout, self.spin_timeout)

        self.spin_retries = QSpinBox()
        self.spin_retries.setRange(0, 20)
        self.spin_retries.setValue(self.config.max_retries)
        self.lbl_retries = QLabel("Max Retries:")
        net_form.addRow(self.lbl_retries, self.spin_retries)

        scroll_layout.addWidget(self.grp_network)

        # Local Storage Policy Group
        self.grp_storage_policy = QGroupBox("Zero/Quota Storage Policy Settings")
        sp_form = QFormLayout(self.grp_storage_policy)

        self.spin_max_mb = QSpinBox()
        self.spin_max_mb.setRange(0, 500000)
        self.spin_max_mb.setValue(self.config.max_local_storage_mb)
        self.lbl_max_mb = QLabel("Max Disk Cache (MB, 0 = Keep Nothing):")
        sp_form.addRow(self.lbl_max_mb, self.spin_max_mb)

        self.chk_purge_upload = QCheckBox("Purge Files Immediately After S3 Upload")
        self.chk_purge_upload.setChecked(self.config.purge_local_files_after_upload)
        sp_form.addRow(self.chk_purge_upload)

        scroll_layout.addWidget(self.grp_storage_policy)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        self.pages_stack.addWidget(page)

    # ── 4. Storage & S3 Page ───────────────────────────────────
    def _build_storage_page(self):
        page, layout, self.storage_header = self._create_page_wrapper("storage")

        self.grp_ia = QGroupBox("Internet Archive S3 Credentials")
        ia_form = QFormLayout(self.grp_ia)

        self.input_collection = QLineEdit(self.config.ia_collection)
        self.lbl_collection = QLabel("IA Collection:")
        ia_form.addRow(self.lbl_collection, self.input_collection)

        self.input_identifier = QLineEdit(self.config.ia_identifier)
        self.lbl_identifier = QLabel("IA Identifier:")
        ia_form.addRow(self.lbl_identifier, self.input_identifier)

        self.input_creator = QLineEdit(self.config.ia_creator)
        self.lbl_creator = QLabel("Creator:")
        ia_form.addRow(self.lbl_creator, self.input_creator)

        self.input_title = QLineEdit(self.config.ia_title)
        self.lbl_title = QLabel("Title:")
        ia_form.addRow(self.lbl_title, self.input_title)

        self.input_access = QLineEdit(self.config.ia_access_key)
        self.input_access.setEchoMode(QLineEdit.EchoMode.Password)
        self.lbl_access = QLabel("S3 Access Key:")
        ia_form.addRow(self.lbl_access, self.input_access)

        self.input_secret = QLineEdit(self.config.ia_secret_key)
        self.input_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.lbl_secret = QLabel("S3 Secret Key:")
        ia_form.addRow(self.lbl_secret, self.input_secret)

        self.input_endpoint = QLineEdit(self.config.ia_endpoint)
        self.lbl_endpoint = QLabel("S3 Endpoint:")
        ia_form.addRow(self.lbl_endpoint, self.input_endpoint)

        layout.addWidget(self.grp_ia)

        self.grp_fallback = QGroupBox("Local Fallback Directory")
        fb_form = QFormLayout(self.grp_fallback)

        fb_row = QHBoxLayout()
        self.input_fallback = QLineEdit(self.config.fallback_dir)
        self.btn_browse_fallback = QPushButton("Browse")
        self.btn_browse_fallback.clicked.connect(self.browse_fallback_folder)
        fb_row.addWidget(self.input_fallback)
        fb_row.addWidget(self.btn_browse_fallback)

        self.lbl_fallback = QLabel("Fallback Folder:")
        fb_form.addRow(self.lbl_fallback, fb_row)
        layout.addWidget(self.grp_fallback)

        layout.addStretch()
        self.pages_stack.addWidget(page)

    # ── 5. Languages & Interactive Editor Page ──────────────────
    def _build_languages_page(self):
        page, layout, self.languages_header = self._create_page_wrapper("languages")

        top_row = QHBoxLayout()
        self.combo_lang = QComboBox()
        for code, name in LANGUAGES.items():
            self.combo_lang.addItem(f"{name} ({code})", code)
        self.combo_lang.addItem("Custom Language", "custom")
        self.combo_lang.currentIndexChanged.connect(self.on_language_changed)

        top_row.addWidget(self.combo_lang, 1)

        self.btn_import_lang = QPushButton("Import .awec.language")
        self.btn_import_lang.clicked.connect(self.import_language_file)
        self.btn_export_lang = QPushButton("Export Pack (.awec.language)")
        self.btn_export_lang.clicked.connect(self.export_language_file)

        top_row.addWidget(self.btn_import_lang)
        top_row.addWidget(self.btn_export_lang)
        layout.addLayout(top_row)

        self.grp_editor = QGroupBox("Visual Interactive Language Pack Editor")
        elayout = QVBoxLayout(self.grp_editor)

        filter_row = QHBoxLayout()
        self.input_filter_keys = QLineEdit()
        self.input_filter_keys.setPlaceholderText("Search UI keys or labels...")
        self.input_filter_keys.textChanged.connect(self.filter_key_table)
        filter_row.addWidget(self.input_filter_keys)
        elayout.addLayout(filter_row)

        # Table Widget for Visual Key-Value Editing
        self.table_lang = QTableWidget(0, 2)
        self.table_lang.setHorizontalHeaderLabels(["UI Key", "Translated Label / Button Text"])
        self.table_lang.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table_lang.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_lang.setColumnWidth(0, 220)
        self.table_lang.cellChanged.connect(self.on_table_cell_changed)
        elayout.addWidget(self.table_lang, 1)

        layout.addWidget(self.grp_editor, 1)
        self.pages_stack.addWidget(page)

    # ── 6. Live Logs Page ───────────────────────────────────────
    def _build_logs_page(self):
        page, layout, self.logs_header = self._create_page_wrapper("logs")

        self.full_logs = QPlainTextEdit()
        self.full_logs.setReadOnly(True)
        layout.addWidget(self.full_logs, 1)

        self.btn_clear_logs = QPushButton("Clear Logs")
        self.btn_clear_logs.clicked.connect(self.full_logs.clear)
        layout.addWidget(self.btn_clear_logs)

        self.pages_stack.addWidget(page)

    # ── Navigation & Dynamic Retranslation ──────────────────────
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

        # Navigation sidebar buttons
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

        # Dashboard buttons
        self.btn_start.setText(t.get("start", "Start Crawl"))
        self.btn_pause.setText(t.get("pause", "Pause"))
        self.btn_stop.setText(t.get("stop", "Stop Crawl"))

        # Sites buttons
        self.btn_add_site.setText(t.get("add", "Add Site"))
        self.btn_remove_site.setText(t.get("remove", "Remove Selected"))
        self.btn_clear_sites.setText(t.get("clear", "Clear All"))
        self.btn_import_sites.setText(t.get("import", "Import"))

        # Group Titles
        self.grp_general.setTitle(t.get("general_settings", "General Crawl Settings"))
        self.grp_network.setTitle(t.get("network_settings", "Anti-Blocking Settings"))
        self.grp_storage_policy.setTitle(t.get("storage_policy", "Storage Policy"))
        self.grp_ia.setTitle(t.get("ia_settings", "Internet Archive Credentials"))
        self.grp_fallback.setTitle(t.get("fallback", "Fallback Directory"))
        self.grp_editor.setTitle(t.get("lang_editor", "Visual Language Editor"))

        # Form Labels & Checkboxes
        self.lbl_workers.setText(t.get("workers", "Workers:"))
        self.lbl_depth.setText(t.get("depth", "Max Depth:"))
        self.lbl_max_urls.setText(t.get("max_urls", "Max URLs:"))
        self.lbl_delay.setText(t.get("delay", "Per-Host Delay:"))
        self.lbl_max_file.setText(t.get("max_file", "Max File Size:"))
        self.lbl_ext.setText(t.get("extensions", "Extensions:"))

        self.chk_robots.setText(t.get("respect_robots", "Respect robots.txt"))
        self.chk_same_domain.setText(t.get("same_domain", "Same Domain Only"))
        self.chk_download_files.setText(t.get("download_files", "Download Target Files"))

        self.lbl_ua.setText(t.get("user_agent", "User-Agent:"))
        self.chk_ua_rotation.setText(t.get("ua_rotation", "Enable UA Rotation"))
        self.lbl_jitter.setText(t.get("delay_jitter", "Delay Jitter:"))
        self.chk_cookie_jar.setText(t.get("cookie_jar", "Persistent Cookie Jar"))
        self.chk_auto_headers.setText(t.get("auto_headers", "Auto Sec-Fetch Headers"))
        self.chk_verify_ssl.setText(t.get("verify_ssl", "Verify SSL"))
        self.lbl_proxy.setText(t.get("proxy", "Proxy URL:"))
        self.lbl_headers.setText(t.get("custom_headers", "Custom Headers (JSON):"))
        self.lbl_timeout.setText(t.get("timeout", "Timeout (sec):"))
        self.lbl_retries.setText(t.get("retries", "Max Retries:"))

        self.lbl_max_mb.setText(t.get("max_local_mb", "Max Local Storage (MB):"))
        self.chk_purge_upload.setText(t.get("purge_after_upload", "Purge After Upload"))

        self.lbl_collection.setText(t.get("collection", "IA Collection:"))
        self.lbl_identifier.setText(t.get("identifier", "IA Identifier:"))
        self.lbl_creator.setText(t.get("creator", "Creator:"))
        self.lbl_title.setText(t.get("ia_title", "Title:"))
        self.lbl_access.setText(t.get("access_key", "S3 Access Key:"))
        self.lbl_secret.setText(t.get("secret_key", "S3 Secret Key:"))
        self.lbl_endpoint.setText(t.get("endpoint", "S3 Endpoint:"))
        self.lbl_fallback.setText(t.get("fallback", "Fallback Folder:"))
        self.btn_browse_fallback.setText(t.get("browse", "Browse"))

        self.btn_import_lang.setText(t.get("import", "Import .awec.language"))
        self.btn_export_lang.setText(t.get("export", "Export Pack"))
        self.btn_clear_logs.setText(t.get("clear", "Clear Logs"))

        self.input_filter_keys.setPlaceholderText(t.get("filter_keys", "Search UI keys or labels..."))
        self.table_lang.setHorizontalHeaderLabels([
            t.get("key_name", "UI Key"),
            t.get("key_value", "Translated Label")
        ])

        self.update_status_badge(self.status_state)
        self.populate_language_table()

    # ── Interactive Language Table ─────────────────────────────
    def populate_language_table(self):
        self.table_lang.blockSignals(True)
        self.table_lang.setRowCount(0)

        search = self.input_filter_keys.text().lower().strip()
        sorted_keys = sorted(self.t.keys())

        for key in sorted_keys:
            val = str(self.t[key])
            if search and search not in key.lower() and search not in val.lower():
                continue

            row = self.table_lang.rowCount()
            self.table_lang.insertRow(row)

            key_item = QTableWidgetItem(key)
            key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # Key is readonly
            key_item.setForeground(Qt.GlobalColor.lightGray)

            val_item = QTableWidgetItem(val)

            self.table_lang.setItem(row, 0, key_item)
            self.table_lang.setItem(row, 1, val_item)

        self.table_lang.blockSignals(False)

    def filter_key_table(self):
        self.populate_language_table()

    def on_table_cell_changed(self, row: int, col: int):
        if col != 1:
            return
        key_item = self.table_lang.item(row, 0)
        val_item = self.table_lang.item(row, 1)
        if key_item and val_item:
            k = key_item.text().strip()
            v = val_item.text()
            self.t[k] = v
            self._retranslate_ui()

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
            self._retranslate_ui()

    def import_language_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Language Pack", "", "AWEC Language (*.awec.language *.json);;All Files (*)"
        )
        if not path:
            return
        try:
            pack = load_language_pack(path)
            self.t = pack
            self._retranslate_ui()
            QMessageBox.information(self, "AWEC", "Language pack imported and applied successfully!")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not load language pack: {e}")

    def export_language_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Language Pack", "custom.awec.language", "AWEC Language (*.awec.language)"
        )
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(self.t, ensure_ascii=False, indent=2), encoding="utf-8")
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
            ua_rotation_enabled=self.chk_ua_rotation.isChecked(),
            delay_jitter_sec=self.spin_jitter.value(),
            cookie_jar_enabled=self.chk_cookie_jar.isChecked(),
            auto_headers_enabled=self.chk_auto_headers.isChecked(),
            verify_ssl=self.chk_verify_ssl.isChecked(),
            proxy_url=self.input_proxy.text(),
            custom_headers_json=self.input_headers.toPlainText(),
            request_timeout=self.spin_timeout.value(),
            max_retries=self.spin_retries.value(),
            max_local_storage_mb=self.spin_max_mb.value(),
            purge_local_files_after_upload=self.chk_purge_upload.isChecked(),
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
