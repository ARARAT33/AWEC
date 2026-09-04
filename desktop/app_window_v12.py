"""AWEC Desktop v12 — responsive light command center and resource archive explorer."""
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtWidgets import (QFileDialog, QCheckBox, QComboBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QListWidget, QMessageBox, QPushButton, QSpinBox, QTextBrowser,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QSplitter)
from desktop.app_window_v11 import AWECMainWindow as V11MainWindow
from desktop.crawler_engine_v12 import find_resumable_crawls


class AWECMainWindow(V11MainWindow):
    """AWEC v12 with roomy controls, resizable panes and full local mirror browsing."""
    SETTINGS_FILE = Path.home() / "AWEC" / "v12_settings.json"

    def __init__(self):
        self._v12 = {}
        super().__init__()
        self._make_layout_responsive()
        self._load_v12_settings()
        self._refresh_resume_list()
        self._refresh_archive_explorer()
        self.setWindowTitle("AWEC v12 • Web Archive Command Center")

    def _make_layout_responsive(self):
        """Prevent cramped controls and let the content area consume available width."""
        self.setMinimumSize(1180, 760)
        self.resize(max(self.width(), 1380), max(self.height(), 860))
        side = self.findChild(QWidget, "sidebar")
        if side:
            side.setMinimumWidth(225)
            side.setMaximumWidth(290)
        pages = getattr(self, "pages", None)
        if pages:
            pages.setMinimumWidth(850)
        root = self.centralWidget()
        if not root:
            return
        for w in root.findChildren(QWidget):
            cls = w.metaObject().className()
            if cls in {"QLineEdit", "QComboBox", "QSpinBox", "QDoubleSpinBox"}:
                w.setMinimumWidth(max(w.minimumWidth(), 260))
            elif cls in {"QPlainTextEdit", "QTextEdit", "QTextBrowser", "QListWidget", "QTreeWidget"}:
                w.setMinimumWidth(max(w.minimumWidth(), 320))
            elif cls == "QGroupBox":
                w.setMinimumWidth(max(w.minimumWidth(), 500))
        # Form labels get enough room for long settings names instead of squeezing fields.
        for form in root.findChildren(QFormLayout):
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

    def _dashboard(self):
        super()._dashboard()
        page = self.pages.widget(0)
        layout = page.layout()
        box = QGroupBox("♻️ Resume Center")
        bl = QVBoxLayout(box)
        self.resume_list = QListWidget(); self.resume_list.setMinimumHeight(100); bl.addWidget(self.resume_list)
        rr = QHBoxLayout()
        rb = QPushButton("♻️ Resume Selected"); rb.setObjectName("primaryButton"); rb.clicked.connect(self._resume_selected); rr.addWidget(rb)
        rf = QPushButton("↻ Refresh"); rf.clicked.connect(self._refresh_resume_list); rr.addWidget(rf); rr.addStretch(); bl.addLayout(rr)
        layout.addWidget(box)
        exp = QHBoxLayout(); eb = QPushButton("🌐 Open Archive Explorer"); eb.clicked.connect(lambda: self._page_v12("archive")); exp.addWidget(eb); exp.addStretch(); layout.addLayout(exp)

    def _crawler(self):
        super()._crawler()
        page = self.pages.widget(2); layout = page.layout()
        scope = QGroupBox("🕸️ Site Copy / Link Policy")
        sf = QFormLayout(scope)
        self.v12_follow_links = QCheckBox("Follow links found inside pages"); self.v12_follow_links.setChecked(True)
        self.v12_external = QCheckBox("Also crawl external navigation links"); self.v12_external.setChecked(False)
        self.v12_embedded = QCheckBox("Always fetch embedded assets (images, CSS, JS, video, audio, iframes, fonts/files)"); self.v12_embedded.setChecked(True); self.v12_embedded.setEnabled(False)
        self.v12_apex = QLabel("✓ www + apex + subdomains are treated as the same site")
        self.v12_depth_hint = QLabel("Max depth: 0 = unlimited. Embedded assets do not consume page depth.")
        self.v12_apex.setWordWrap(True); self.v12_depth_hint.setWordWrap(True)
        sf.addRow(self.v12_follow_links); sf.addRow(self.v12_external); sf.addRow(self.v12_embedded); sf.addRow(self.v12_apex); sf.addRow(self.v12_depth_hint)
        layout.addWidget(scope)

        box = QGroupBox("💾 TMPCRAWL • Local Storage Governor")
        f = QFormLayout(box)
        self.v12_tmp = QLabel(str(Path.home() / "AWEC" / "tmpcrawl")); self.v12_tmp.setWordWrap(True); self.v12_tmp.setMinimumWidth(420)
        choose = QPushButton("Choose…"); choose.clicked.connect(self._choose_tmp)
        f.addRow("Temporary folder", self.v12_tmp); f.addRow("", choose)
        self.v12_limit = QSpinBox(); self.v12_limit.setRange(0, 1024*1024); self.v12_limit.setValue(0); self.v12_limit.setSuffix(" MB"); f.addRow("TMP limit (0 = unlimited)", self.v12_limit)
        self.v12_reserve = QSpinBox(); self.v12_reserve.setRange(256, 1024*1024); self.v12_reserve.setValue(2048); self.v12_reserve.setSuffix(" MB"); f.addRow("Minimum free disk reserve", self.v12_reserve)
        self.v12_keep = QCheckBox("Keep local mirror after crawl"); self.v12_keep.setChecked(True); f.addRow(self.v12_keep)
        self.v12_purge = QCheckBox("After verified IA upload, purge payload from TMPCRAWL"); self.v12_purge.setChecked(False); f.addRow(self.v12_purge)
        self.v12_auto = QCheckBox("Show interrupted crawls in Resume Center"); self.v12_auto.setChecked(True); f.addRow(self.v12_auto)
        layout.addWidget(box)

        box2 = QGroupBox("☁️ Internet Archive • Live Publisher")
        f2 = QFormLayout(box2)
        self.v12_live = QCheckBox("Upload each successfully fetched resource to IA immediately"); self.v12_live.setChecked(True); f2.addRow(self.v12_live)
        self.v12_verify = QCheckBox("Verify remote object after upload"); self.v12_verify.setChecked(True); f2.addRow(self.v12_verify)
        note = QLabel("IA publishing is independent from crawling: an upload failure stays visible and does not throw away the downloaded resource."); note.setWordWrap(True); f2.addRow(note)
        layout.addWidget(box2)
        self._make_layout_responsive()

    def _build_archive_page(self):
        p = QWidget(); l = QVBoxLayout(p); l.setContentsMargins(24,20,24,20); l.setSpacing(12)
        h = QHBoxLayout(); title = QLabel("🌐 Archive Explorer"); title.setObjectName("pageHeader"); h.addWidget(title); h.addStretch()
        refresh = QPushButton("↻ Refresh"); refresh.clicked.connect(self._refresh_archive_explorer); h.addWidget(refresh); l.addLayout(h)
        sub = QLabel("Browse the complete local site/resource mirror, preview downloaded files, and open the IA item."); sub.setObjectName("pageSubtitle"); sub.setWordWrap(True); l.addWidget(sub)
        split = QSplitter(Qt.Orientation.Horizontal); split.setChildrenCollapsible(False)
        self.archive_tree = QTreeWidget(); self.archive_tree.setHeaderLabels(["Downloaded site / resource"]); self.archive_tree.setMinimumWidth(430); self.archive_tree.itemDoubleClicked.connect(self._preview_selected); split.addWidget(self.archive_tree)
        right = QWidget(); right.setMinimumWidth(520); rl = QVBoxLayout(right); self.archive_info = QLabel("Select a crawl or file."); self.archive_info.setWordWrap(True); rl.addWidget(self.archive_info)
        self.archive_preview = QTextBrowser(); self.archive_preview.setOpenExternalLinks(True); rl.addWidget(self.archive_preview,1)
        br = QHBoxLayout(); self.open_local = QPushButton("📄 Open Preview"); self.open_local.clicked.connect(self._preview_selected); br.addWidget(self.open_local)
        self.open_ia = QPushButton("☁️ Open IA Item"); self.open_ia.clicked.connect(self._open_ia); br.addWidget(self.open_ia); br.addStretch(); rl.addLayout(br)
        split.addWidget(right); split.setStretchFactor(0, 1); split.setStretchFactor(1, 2); split.setSizes([500,900]); l.addWidget(split,1); self.pages.addWidget(p); self._archive_page = p

    def _page_v12(self, _k):
        if not hasattr(self, "_archive_page"): self._build_archive_page()
        self.pages.setCurrentWidget(self._archive_page)
        for b in self.nav.values(): b.setChecked(False)
        if hasattr(self, "nav_v12_archive"): self.nav_v12_archive.setChecked(True)
        self._refresh_archive_explorer()

    def _install_archive_nav(self):
        side = self.findChild(QWidget, "sidebar")
        if side and side.layout() and not hasattr(self, "nav_v12_archive"):
            b = QPushButton("🌐 Archive Explorer"); b.setObjectName("navButton"); b.setCheckable(True); b.clicked.connect(lambda: self._page_v12("archive"))
            side.layout().insertWidget(max(0, side.layout().count()-2), b); self.nav_v12_archive = b

    def showEvent(self, e):
        super().showEvent(e)
        self._install_archive_nav()
        self._make_layout_responsive()

    def _choose_tmp(self):
        p = QFileDialog.getExistingDirectory(self, "Choose TMPCRAWL folder", self.v12_tmp.text())
        if p: self.v12_tmp.setText(p); self._save_v12_settings(); self._refresh_resume_list(); self._refresh_archive_explorer()

    def _load_v12_settings(self):
        try: self._v12 = json.loads(self.SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception: self._v12 = {}
        if hasattr(self, "v12_tmp"):
            self.v12_tmp.setText(self._v12.get("tmpcrawl_dir", self.v12_tmp.text()))
            self.v12_limit.setValue(int(self._v12.get("max_local_storage_mb", 0)))
            self.v12_reserve.setValue(int(self._v12.get("min_free_space_mb", 2048)))
            self.v12_keep.setChecked(bool(self._v12.get("keep_local_mirror", True)))
            self.v12_purge.setChecked(bool(self._v12.get("purge_local_files_after_upload", False)))
            self.v12_auto.setChecked(bool(self._v12.get("auto_resume", True)))
            self.v12_live.setChecked(bool(self._v12.get("archive_upload_live", True)))
            self.v12_verify.setChecked(bool(self._v12.get("archive_verify_uploads", True)))
            self.v12_follow_links.setChecked(bool(self._v12.get("follow_links", True)))
            self.v12_external.setChecked(bool(self._v12.get("follow_external_domains", False)))

    def _save_v12_settings(self):
        self._v12 = {"tmpcrawl_dir": self.v12_tmp.text(), "max_local_storage_mb": self.v12_limit.value(), "min_free_space_mb": self.v12_reserve.value(), "keep_local_mirror": self.v12_keep.isChecked(), "purge_local_files_after_upload": self.v12_purge.isChecked(), "auto_resume": self.v12_auto.isChecked(), "archive_upload_live": self.v12_live.isChecked(), "archive_verify_uploads": self.v12_verify.isChecked(), "follow_links": self.v12_follow_links.isChecked(), "follow_external_domains": self.v12_external.isChecked(), "resume_dir": self._v12.get("resume_dir", "")}
        self.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.SETTINGS_FILE.write_text(json.dumps(self._v12, ensure_ascii=False, indent=2), encoding="utf-8")

    def _cfg(self):
        c = super()._cfg(); self._save_v12_settings()
        for k,v in self._v12.items(): setattr(c,k,v)
        c.fallback_dir = self.v12_tmp.text(); c.follow_links = self.v12_follow_links.isChecked(); c.follow_external_domains = self.v12_external.isChecked(); c.download_discovered_files = True; c.file_types = ["*"]; c.max_file_size = -1
        return c

    def start_crawl(self):
        self._save_v12_settings(); super().start_crawl(); QTimer.singleShot(500, self._refresh_resume_list)

    def _resume_selected(self):
        item = self.resume_list.currentItem()
        if not item: return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path: return
        self._v12["resume_dir"] = path; self._save_v12_settings(); self._log(f"♻️ Resume requested: {path}"); self.start_crawl()

    def _finished(self, msg):
        super()._finished(msg); self._v12["resume_dir"] = ""; self._save_v12_settings(); QTimer.singleShot(200, self._refresh_resume_list); QTimer.singleShot(500, self._refresh_archive_explorer)

    def _refresh_resume_list(self):
        if not hasattr(self, "resume_list"): return
        self.resume_list.clear(); root = Path(self.v12_tmp.text()) if hasattr(self, "v12_tmp") else Path.home()/"AWEC"/"tmpcrawl"
        for x in find_resumable_crawls(root):
            from PySide6.QtWidgets import QListWidgetItem
            i = QListWidgetItem(f"{x['crawl_id']} • pending={x['counts'].get('pending',0):,} • in-progress={x['counts'].get('in_progress',0):,}"); i.setData(Qt.ItemDataRole.UserRole, x['path']); self.resume_list.addItem(i)
        if self.resume_list.count()==0: self.resume_list.addItem("✓ No interrupted crawls found")

    def _refresh_archive_explorer(self):
        if not hasattr(self, "archive_tree"): return
        self.archive_tree.clear(); root = Path(self.v12_tmp.text()) if hasattr(self,"v12_tmp") else Path.home()/"AWEC"/"tmpcrawl"
        for site in sorted(root.glob("crawls/*/site"), key=lambda p:p.parent.stat().st_mtime, reverse=True):
            top=QTreeWidgetItem([f"🗂 {site.parent.name} • {site}"]); top.setData(0,Qt.ItemDataRole.UserRole,str(site)); self.archive_tree.addTopLevelItem(top); count=0
            try:
                for f in site.rglob("*"):
                    if f.is_file():
                        it=QTreeWidgetItem([str(f.relative_to(site))]); it.setData(0,Qt.ItemDataRole.UserRole,str(f)); top.addChild(it); count+=1
                        if count>=10000: break
            except OSError: pass
            top.setText(0,top.text(0)+f" • {count:,} files")
        self.archive_tree.expandToDepth(0)

    def _preview_selected(self,*_):
        it=self.archive_tree.currentItem()
        if not it:return
        p=Path(it.data(0,Qt.ItemDataRole.UserRole) or '')
        if p.is_dir():return
        try:size=p.stat().st_size
        except OSError:size=0
        self.archive_info.setText(f"📄 {p}\nSize: {size:,} bytes")
        if p.suffix.lower() in {'.html','.htm','.xhtml'}: self.archive_preview.setSource(QUrl.fromLocalFile(str(p)))
        else:
            try:self.archive_preview.setPlainText(p.read_text(encoding='utf-8',errors='replace')[:300000])
            except Exception:self.archive_preview.setPlainText(f"Binary resource: {p.name}")

    def _open_ia(self):
        c=self._cfg(); ident=str(getattr(c,'ia_identifier','')).strip()
        if not ident: QMessageBox.information(self,'AWEC','Configure an Internet Archive Item Name first.'); return
        url='https://archive.org/details/'+ident
        try:
            if sys.platform.startswith('win'): os.startfile(url)
            elif sys.platform=='darwin': subprocess.Popen(['open',url])
            else: subprocess.Popen(['xdg-open',url])
        except Exception: pass
