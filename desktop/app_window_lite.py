"""AWEC portable desktop UI with mandatory first-run safety and root-local storage."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)

from desktop.app_window_v5 import AWECMainWindow as V5MainWindow
from desktop.i18n import LANGUAGES, get_translation
from desktop.language_editor import load_language, save_language
from desktop.config_schema import AWECConfig
from storage_layout import app_root, ensure_layout, migrate_legacy, config_path, data_usage_bytes, disk_free_bytes
from desktop.safety_gate import SafetySetupDialog, platform_name, platform_rules, preflight, SAFETY_VERSION


class AWECMainWindow(V5MainWindow):
    """Portable AWEC shell. No crawl data is written to ~/AWEC."""

    def __init__(self):
        self.storage_root = app_root()
        ensure_layout(self.storage_root)
        self.migration_messages = migrate_legacy(self.storage_root)
        cfg = AWECConfig.load(config_path(self.storage_root))
        if not cfg.safety_configured or cfg.safety_version != SAFETY_VERSION:
            dlg = SafetySetupDialog(self.storage_root, cfg.max_storage_gb or 10.0, cfg.min_free_space_gb or 1.0)
            if dlg.exec() != dlg.DialogCode.Accepted:
                raise SystemExit(0)
            cfg.max_storage_gb, cfg.min_free_space_gb = dlg.values()
            cfg.safety_configured = True
            cfg.safety_version = SAFETY_VERSION
            cfg.storage_root = str(self.storage_root)
            paths = ensure_layout(self.storage_root)
            cfg.fallback_dir = str(paths["fallback"])
            cfg.tmpcrawl_dir = str(paths["temp"])
            cfg.checkpoint_path = str(paths["checkpoints"] / "checkpoint.json")
            cfg.save(config_path(self.storage_root))
        super().__init__()
        self.setWindowTitle("AWEC • Web Archive Engine")
        self.setMinimumSize(900, 620)
        self.resize(1120, 720)
        self._language_code = "en"
        self._language_values = get_translation("en")
        self._language_keys = []
        self._rewrite_sidebar()
        self._build_language_page()
        self._build_storage_page()
        self._page("dashboard")
        if self.migration_messages:
            self._log(f"📦 Migrated legacy AWEC data to {self.storage_root}")

    def _load_config(self):
        """Load persistent configuration only from the AWEC executable root."""
        try:
            self.config = AWECConfig.load(config_path(self.storage_root))
        except Exception:
            self.config = AWECConfig()
        c = self.config
        for u in c.seeds: self.site_list.addItem(u)
        self.workers.setValue(min(8, max(1, c.workers))); self.depth.setValue(c.max_depth); self.max_urls.setValue(c.max_urls)
        self.delay.setValue(c.per_host_delay); self.timeout.setValue(c.request_timeout); self.retries.setValue(c.max_retries)
        self.same_domain.setChecked(c.same_domain_only); self.robots.setChecked(c.respect_robots)
        self.net_mode.setCurrentIndex(1 if c.network_mode == "fanti" else 0); self.ua.setText(c.custom_user_agent)
        self.ua_rotate.setChecked(c.ua_rotation_enabled); self.jitter.setValue(c.delay_jitter_sec); self.cookies.setChecked(c.cookie_jar_enabled)
        self.ssl.setChecked(c.verify_ssl); self.proxy.setText(c.proxy_url); self.ia_collection.setText(c.ia_collection)
        self.ia_item.setText(c.ia_identifier); self.ia_title.setText(c.ia_title); self.ia_creator.setText(c.ia_creator)
        self.ia_desc.setPlainText(c.ia_description); self.ia_access.setText(c.ia_access_key); self.ia_secret.setText(c.ia_secret_key); self.ia_endpoint.setText(c.ia_endpoint)

    def _cfg(self):
        c = super()._cfg()
        paths = ensure_layout(self.storage_root)
        c.storage_root = str(self.storage_root)
        c.max_storage_gb = float(self.storage_limit.value())
        c.min_free_space_gb = float(self.reserve_limit.value())
        c.max_local_storage_mb = int(c.max_storage_gb * 1024)
        c.fallback_dir = str(paths["fallback"])
        c.tmpcrawl_dir = str(paths["temp"])
        c.checkpoint_path = str(paths["checkpoints"] / "checkpoint.json")
        c.safety_configured = True; c.safety_version = SAFETY_VERSION
        return c

    def save_config(self):
        try:
            c = self._cfg()
            ok, msg = preflight(self.storage_root, c.max_storage_gb, c.min_free_space_gb)
            if not ok:
                QMessageBox.critical(self, "AWEC Safety", msg); return
            self.config = c; self.config.save(config_path(self.storage_root))
            self._refresh_storage(); self.ia_status.setText("✓ Settings saved in AWEC root"); self._log("💾 Configuration saved")
        except Exception as e:
            QMessageBox.critical(self, "AWEC", str(e))

    def _rewrite_sidebar(self):
        side = self.findChild(QWidget, "sidebar")
        if side is None: return
        layout = side.layout()
        if layout is None: return
        status = getattr(self, "status", None)
        for button in list(getattr(self, "nav", {}).values()): layout.removeWidget(button); button.deleteLater()
        while layout.count():
            item = layout.takeAt(0); widget = item.widget()
            if widget is not None and widget is not status: widget.deleteLater()
        side.setFixedWidth(190); layout.setContentsMargins(12,14,12,12); layout.setSpacing(5)
        brand = QLabel("AWEC"); brand.setObjectName("brandTitle"); layout.addWidget(brand)
        subtitle = QLabel("Web Archive Engine"); subtitle.setObjectName("brandSubtitle"); layout.addWidget(subtitle)
        section = QLabel("WORKSPACE"); section.setObjectName("menuSection"); layout.addWidget(section)
        self.nav = {}; group = QButtonGroup(self); group.setExclusive(True)
        items = (("dashboard","⌂  Dashboard"),("sites","◎  Seed Sites"),("crawler","↯  Crawler"),("storage","▣  Storage"),("ia","☁  Internet Archive"),("languages","文  Languages"),("logs","≡  Live Logs"))
        for key,text in items:
            b=QPushButton(text); b.setObjectName("navButton"); b.setCheckable(True); b.setMinimumHeight(34); b.clicked.connect(lambda checked=False,k=key:self._page(k)); group.addButton(b); self.nav[key]=b; layout.addWidget(b)
        layout.addStretch(1)
        if status is not None: layout.addWidget(status)

    def _build_storage_page(self):
        p=QWidget(); self.storage_page=p; l=QVBoxLayout(p); l.setContentsMargins(24,22,24,22); l.setSpacing(12)
        l.addWidget(QLabel("Storage & Safety", objectName="pageHeader"))
        l.addWidget(QLabel(f"Portable storage root • {platform_name()}", objectName="pageSubtitle"))
        box=QGroupBox("AWEC Storage"); f=QFormLayout(box)
        self.storage_path=QLineEdit(str(self.storage_root)); self.storage_path.setReadOnly(True); f.addRow("AWEC root",self.storage_path)
        self.storage_limit=QSpinBox(); self.storage_limit.setRange(1,1048576); self.storage_limit.setValue(max(1,int(getattr(self.config,'max_storage_gb',10)))); self.storage_limit.setSuffix(" GB"); f.addRow("Maximum data",self.storage_limit)
        self.reserve_limit=QSpinBox(); self.reserve_limit.setRange(0,1048576); self.reserve_limit.setValue(max(0,int(getattr(self.config,'min_free_space_gb',1)))); self.reserve_limit.setSuffix(" GB"); f.addRow("Free disk reserve",self.reserve_limit)
        l.addWidget(box)
        self.storage_status=QLabel(); l.addWidget(self.storage_status)
        layout_box=QGroupBox("Directory policy"); lf=QFormLayout(layout_box)
        paths=ensure_layout(self.storage_root)
        lf.addRow("Persistent settings",QLabel(str(paths['config']))); lf.addRow("Persistent IA data",QLabel(str(paths['ia']))); lf.addRow("Crawl/fallback",QLabel(str(paths['fallback']))); lf.addRow("Temporary",QLabel(str(paths['temp'])))
        l.addWidget(layout_box)
        b=QPushButton("✓ Validate & Save"); b.setObjectName("primaryButton"); b.clicked.connect(self.save_config); l.addWidget(b); l.addStretch(1); self.pages.addWidget(p); self._refresh_storage()

    def _refresh_storage(self):
        if not hasattr(self,'storage_status'): return
        used=data_usage_bytes(self.storage_root)/1024**3; limit=float(self.storage_limit.value()) if hasattr(self,'storage_limit') else float(getattr(self.config,'max_storage_gb',10)); free=disk_free_bytes(self.storage_root)/1024**3
        self.storage_status.setText(f"📦 Data: {used:.2f} GB / {limit:.2f} GB • 💽 Disk free: {free:.2f} GB • 🛡️ Protected: config + IA")

    def _build_language_page(self):
        p=QWidget(); self.language_page=p; l=QVBoxLayout(p); l.setContentsMargins(24,22,24,22); l.setSpacing(10)
        l.addWidget(QLabel("Languages & Custom Language Studio",objectName="pageHeader")); l.addWidget(QLabel("Built-in languages plus editable .awec.language packs.",objectName="pageSubtitle"))
        top=QHBoxLayout(); self.language_combo=QComboBox()
        for code,name in LANGUAGES.items(): self.language_combo.addItem(f"{name} ({code})",code)
        self.language_combo.currentIndexChanged.connect(self._language_selected); top.addWidget(QLabel("Language")); top.addWidget(self.language_combo,1)
        imp=QPushButton("Import .awec.language"); imp.clicked.connect(self._import_language); top.addWidget(imp); exp=QPushButton("Export .awec.language"); exp.clicked.connect(self._export_language); top.addWidget(exp); l.addLayout(top)
        row=QHBoxLayout(); self.language_filter=QLineEdit(); self.language_filter.setPlaceholderText("Search UI keys or translated text…"); self.language_filter.textChanged.connect(self._filter_language_table); row.addWidget(self.language_filter,1); ap=QPushButton("✓ Apply Language"); ap.clicked.connect(self._apply_language); row.addWidget(ap); l.addLayout(row)
        self.language_table=QTableWidget(0,2); self.language_table.setHorizontalHeaderLabels(["UI Key","Value"]); self.language_table.horizontalHeader().setStretchLastSection(True); self.language_table.cellChanged.connect(self._language_cell_changed); l.addWidget(self.language_table,1)
        self.language_status=QLabel("10 built-in languages • custom .awec.language supported"); l.addWidget(self.language_status); self.pages.addWidget(p); self._populate_language_table()
    def _language_selected(self,_): self._language_code=self.language_combo.currentData() or 'en'; self._language_values=get_translation(self._language_code); self._populate_language_table()
    def _populate_language_table(self):
        if not hasattr(self,'language_table'): return
        self.language_table.blockSignals(True); self.language_table.setRowCount(0); self._language_keys=sorted(self._language_values)
        for key in self._language_keys:
            r=self.language_table.rowCount(); self.language_table.insertRow(r); self.language_table.setItem(r,0,QTableWidgetItem(key)); self.language_table.setItem(r,1,QTableWidgetItem(str(self._language_values.get(key,''))))
        self.language_table.blockSignals(False); self._filter_language_table(self.language_filter.text() if hasattr(self,'language_filter') else '')
    def _filter_language_table(self,text):
        q=text.strip().lower()
        for r in range(self.language_table.rowCount()): self.language_table.setRowHidden(r,bool(q and q not in self.language_table.item(r,0).text().lower() and q not in self.language_table.item(r,1).text().lower()))
    def _language_cell_changed(self,row,column):
        if column==1:self._language_values[self.language_table.item(row,0).text()]=self.language_table.item(row,1).text()
    def _apply_language(self):
        t=self._language_values; labels={"dashboard":t.get("dashboard","Dashboard"),"sites":t.get("sites","Seed Sites"),"crawler":t.get("crawler","Crawler"),"storage":t.get("storage","Storage"),"ia":t.get("ia_settings","Internet Archive"),"languages":t.get("languages","Languages & Editor"),"logs":t.get("logs","Live Logs")}
        for k,v in labels.items():
            if k in self.nav:self.nav[k].setText(v)
        self.setWindowTitle(t.get("title","AWEC Desktop — Web Archive Engine")); self.language_status.setText(f"✓ Applied: {self._language_code}")
    def _import_language(self):
        path,_=QFileDialog.getOpenFileName(self,"Import AWEC Language Pack","","AWEC Language (*.awec.language);;All Files (*)")
        if not path:return
        try: self._language_values.update(load_language(path)); self._populate_language_table(); self._apply_language()
        except Exception as e:QMessageBox.critical(self,"AWEC",f"Language import failed: {e}")
    def _export_language(self):
        path,_=QFileDialog.getSaveFileName(self,"Export AWEC Language Pack",str(self.storage_root/"config"/"custom.awec.language"),"AWEC Language (*.awec.language)")
        if not path:return
        try: save_language(path,self._language_values,self._language_code,"AWEC Custom Language")
        except Exception as e:QMessageBox.critical(self,"AWEC",f"Language export failed: {e}")

    def _page(self,key):
        if key=="storage" and hasattr(self,"storage_page"):self.pages.setCurrentWidget(self.storage_page)
        elif key=="languages" and hasattr(self,"language_page"):self.pages.setCurrentWidget(self.language_page)
        else:
            indexes={"dashboard":0,"sites":1,"crawler":2,"ia":3,"logs":4}
            if key in indexes:self.pages.setCurrentIndex(indexes[key])
        for k,b in getattr(self,"nav",{}).items():b.setChecked(k==key)
