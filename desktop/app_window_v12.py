"""AWEC Desktop v12 — responsive light command center, full FANTI controls and resume center."""
from __future__ import annotations

import json, os, subprocess, sys
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtWidgets import (
    QFileDialog, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QTextBrowser, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget, QSplitter, QGridLayout
)
from desktop.app_window_v11 import AWECMainWindow as V11MainWindow
from desktop.crawler_engine_v12 import find_resumable_crawls


class AWECMainWindow(V11MainWindow):
    """v12: roomy light UI with all FANTI controls visible inside a scrollable page."""
    SETTINGS_FILE = Path.home() / "AWEC" / "v12_settings.json"

    def __init__(self):
        self._v12 = {}
        super().__init__()
        self._make_layout_responsive()
        self._load_v12_settings()
        self._refresh_resume_list()
        self._refresh_archive_explorer()
        self._resume_timer = QTimer(self)
        self._resume_timer.timeout.connect(self._refresh_resume_list)
        self._resume_timer.start(2500)
        self.setWindowTitle("AWEC v12 • Web Archive Command Center")

    def _make_layout_responsive(self):
        self.setMinimumSize(1180, 760)
        self.resize(max(self.width(), 1380), max(self.height(), 860))
        side = self.findChild(QWidget, "sidebar")
        if side:
            side.setMinimumWidth(225); side.setMaximumWidth(300)
        pages = getattr(self, "pages", None)
        if pages: pages.setMinimumWidth(850)
        root = self.centralWidget()
        if not root: return
        for w in root.findChildren(QWidget):
            cls = w.metaObject().className()
            if cls in {"QLineEdit", "QComboBox", "QSpinBox", "QDoubleSpinBox"}:
                w.setMinimumWidth(max(w.minimumWidth(), 260))
            elif cls in {"QPlainTextEdit", "QTextEdit", "QTextBrowser", "QListWidget", "QTreeWidget"}:
                w.setMinimumWidth(max(w.minimumWidth(), 320))
            elif cls == "QGroupBox":
                w.setMinimumWidth(max(w.minimumWidth(), 500))
        for form in root.findChildren(QFormLayout):
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

    def _dashboard(self):
        super()._dashboard()
        page = self.pages.widget(0)
        layout = page.layout()
        box = QGroupBox("♻️ Resume Center")
        bl = QVBoxLayout(box)
        info = QLabel("Interrupted crawls are kept here. Select one to reopen its existing state database and continue from pending work.")
        info.setWordWrap(True); bl.addWidget(info)
        self.resume_list = QListWidget(); self.resume_list.setMinimumHeight(130); bl.addWidget(self.resume_list, 1)
        rr = QHBoxLayout()
        rb = QPushButton("♻️ Resume Selected"); rb.setObjectName("primaryButton"); rb.clicked.connect(self._resume_selected); rr.addWidget(rb)
        rf = QPushButton("↻ Refresh"); rf.clicked.connect(self._refresh_resume_list); rr.addWidget(rf)
        of = QPushButton("📂 Open Storage"); of.clicked.connect(self._open_resume_storage); rr.addWidget(of); rr.addStretch(); bl.addLayout(rr)
        layout.addWidget(box)
        exp = QHBoxLayout(); eb = QPushButton("🌐 Open Archive Explorer"); eb.clicked.connect(lambda: self._page_v12("archive")); exp.addWidget(eb); exp.addStretch(); layout.addLayout(exp)
        self._build_resume_page()

    def _build_resume_page(self):
        if hasattr(self, "_resume_page"): return
        p = QWidget(); l = QVBoxLayout(p); l.setContentsMargins(24,20,24,20); l.setSpacing(12)
        title = QLabel("♻️ Resume Center"); title.setObjectName("pageHeader"); l.addWidget(title)
        sub = QLabel("Recover interrupted AWEC crawls without starting a new crawl or losing the existing frontier.")
        sub.setObjectName("pageSubtitle"); sub.setWordWrap(True); l.addWidget(sub)
        self.resume_summary = QLabel("Scanning TMPCRAWL…"); self.resume_summary.setObjectName("infoBadge"); l.addWidget(self.resume_summary)
        self.resume_table = QTreeWidget(); self.resume_table.setHeaderLabels(["Crawl", "Pending", "In progress", "Completed", "Failed", "Storage path"])
        self.resume_table.setMinimumHeight(360); self.resume_table.setRootIsDecorated(False); self.resume_table.itemDoubleClicked.connect(lambda *_: self._resume_selected())
        self.resume_table.setColumnWidth(0, 180); self.resume_table.setColumnWidth(1, 100); self.resume_table.setColumnWidth(2, 110); self.resume_table.setColumnWidth(3, 110); self.resume_table.setColumnWidth(4, 90); l.addWidget(self.resume_table,1)
        row = QHBoxLayout()
        b = QPushButton("♻️ Resume Selected"); b.setObjectName("primaryButton"); b.clicked.connect(self._resume_selected); row.addWidget(b)
        r = QPushButton("↻ Refresh Now"); r.clicked.connect(self._refresh_resume_list); row.addWidget(r)
        o = QPushButton("📂 Open TMPCRAWL"); o.clicked.connect(self._open_resume_storage); row.addWidget(o); row.addStretch(); l.addLayout(row)
        self.pages.addWidget(p); self._resume_page = p

    def _crawler(self):
        # Keep the base controls, but put the entire crawler configuration inside its scroll area.
        super()._crawler()
        page = self.pages.widget(2)
        scroll = page.findChild(QScrollArea)
        if scroll and scroll.widget() and scroll.widget().layout():
            host = scroll.widget(); cl = host.layout()
        else:
            host = QWidget(); cl = QVBoxLayout(host); scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(host); page.layout().addWidget(scroll, 1)

        scope = QGroupBox("🕸️ Site Copy / Link Policy")
        sf = QFormLayout(scope)
        self.v12_follow_links = QCheckBox("Follow links found inside pages"); self.v12_follow_links.setChecked(True); sf.addRow(self.v12_follow_links)
        self.v12_external = QCheckBox("Also crawl external navigation links"); self.v12_external.setChecked(False); sf.addRow(self.v12_external)
        self.v12_embedded = QCheckBox("Always fetch embedded assets — images, CSS, JS, video, audio, iframes, fonts and files"); self.v12_embedded.setChecked(True); self.v12_embedded.setEnabled(False); sf.addRow(self.v12_embedded)
        note = QLabel("www, apex and subdomains are treated as the same site. External embedded resources are fetched even when external navigation is off. No authentication/CAPTCHA/paywall/access-control bypass is attempted."); note.setWordWrap(True); sf.addRow(note)
        cl.addWidget(scope)

        storage = QGroupBox("💾 TMPCRAWL • Local Storage Governor")
        f = QFormLayout(storage)
        self.v12_tmp = QLineEdit(str(Path.home() / "AWEC" / "tmpcrawl")); f.addRow("Temporary folder", self.v12_tmp)
        choose = QPushButton("Choose…"); choose.clicked.connect(self._choose_tmp); f.addRow("", choose)
        self.v12_limit = QSpinBox(); self.v12_limit.setRange(0, 1024*1024); self.v12_limit.setValue(0); self.v12_limit.setSuffix(" MB"); f.addRow("TMP limit (0 = unlimited)", self.v12_limit)
        self.v12_reserve = QSpinBox(); self.v12_reserve.setRange(256, 1024*1024); self.v12_reserve.setValue(2048); self.v12_reserve.setSuffix(" MB"); f.addRow("Minimum free disk reserve", self.v12_reserve)
        self.v12_keep = QCheckBox("Keep local mirror after crawl"); self.v12_keep.setChecked(True); f.addRow(self.v12_keep)
        self.v12_purge = QCheckBox("After verified IA upload, purge payload from TMPCRAWL"); self.v12_purge.setChecked(False); f.addRow(self.v12_purge)
        cl.addWidget(storage)

        ia = QGroupBox("☁️ Internet Archive • Live Publisher")
        f2 = QFormLayout(ia)
        self.v12_live = QCheckBox("Upload each successfully fetched resource to IA immediately"); self.v12_live.setChecked(True); f2.addRow(self.v12_live)
        self.v12_verify = QCheckBox("Verify remote object after upload"); self.v12_verify.setChecked(True); f2.addRow(self.v12_verify)
        n = QLabel("IA publishing is asynchronous: crawl throughput is not blocked by individual uploads and failed uploads remain visible in logs."); n.setWordWrap(True); f2.addRow(n); cl.addWidget(ia)

        fanti = QGroupBox("⚡ FANTI • Advanced Transport Settings")
        fl = QGridLayout(fanti); fl.setHorizontalSpacing(22); fl.setVerticalSpacing(10)
        self.fanti_widgets = {}
        def combo(row, col, label, key, values):
            w = QComboBox(); [(w.addItem(text, data)) for text, data in values]; self.fanti_widgets[key]=w; fl.addWidget(QLabel(label),row,col*2); fl.addWidget(w,row,col*2+1); return w
        def spin(row,col,label,key,lo,hi,val,step=1,suffix=""):
            w=QDoubleSpinBox() if isinstance(val,float) else QSpinBox(); w.setRange(lo,hi); w.setValue(val); w.setSingleStep(step); w.setSuffix(suffix); self.fanti_widgets[key]=w; fl.addWidget(QLabel(label),row,col*2); fl.addWidget(w,row,col*2+1); return w
        def check(row,col,label,key,val):
            w=QCheckBox(label); w.setChecked(val); self.fanti_widgets[key]=w; fl.addWidget(w,row,col*2,1,2); return w
        combo(0,0,"UA profile","fanti_user_agent_profile",[("Archive","archive"),("Desktop","desktop"),("Custom","custom")])
        combo(0,1,"Header profile","fanti_header_profile",[("Default Archive","Default Archive"),("Browser-like","Browser-like"),("Minimal","Minimal")])
        spin(1,0,"Minimum delay","fanti_min_delay",0.0,120.0,0.05,0.01," s")
        spin(1,1,"Maximum delay","fanti_max_delay",0.0,600.0,8.0,0.1," s")
        spin(2,0,"Initial delay","fanti_initial_delay",0.0,120.0,0.15,0.01," s")
        spin(2,1,"Delay jitter","delay_jitter_sec",0.0,60.0,0.25,0.01," s")
        check(3,0,"Adaptive pacing","fanti_adaptive_pacing",True); check(3,1,"Adaptive concurrency","fanti_adaptive_concurrency",True)
        spin(4,0,"Minimum concurrency","fanti_min_concurrency",1,512,1,1)
        spin(4,1,"Initial concurrency","fanti_initial_concurrency",1,512,8,1)
        spin(5,0,"Maximum concurrency","fanti_max_concurrency",1,1024,32,1)
        spin(5,1,"Max retries","fanti_max_retries",0,100,5,1)
        combo(6,0,"Backoff strategy","fanti_backoff_strategy",[(x,x) for x in ("full_jitter","equal_jitter","decorrelated","fixed","exponential")])
        spin(6,1,"Base retry delay","fanti_base_retry_delay",0.0,600.0,1.0,0.1," s")
        spin(7,0,"Max retry delay","fanti_max_retry_delay",0.0,3600.0,60.0,1.0," s")
        check(7,1,"Circuit breaker enabled","fanti_circuit_breaker_enabled",True)
        spin(8,0,"Failure threshold","fanti_circuit_breaker_threshold",1,1000,5,1)
        spin(8,1,"Breaker cooldown","fanti_circuit_breaker_cooldown",0.0,3600.0,30.0,1.0," s")
        spin(9,0,"Max connections","fanti_max_connections",1,4096,160,1)
        spin(9,1,"Connections / host","fanti_max_connections_per_host",1,1024,32,1)
        spin(10,0,"Keep-alive timeout","fanti_keepalive_timeout",0.0,3600.0,30.0,1.0," s")
        spin(10,1,"DNS timeout","fanti_dns_timeout",0.1,600.0,10.0,0.1," s")
        spin(11,0,"Connect timeout","fanti_connect_timeout",0.1,600.0,10.0,0.1," s")
        spin(11,1,"Read timeout","fanti_read_timeout",0.1,3600.0,30.0,0.1," s")
        spin(12,0,"Total timeout","fanti_total_timeout",0.1,3600.0,60.0,0.1," s")
        spin(12,1,"Max redirects","fanti_max_redirects",0,100,10,1)
        check(13,0,"Allow cross-domain redirects","fanti_allow_cross_domain_redirects",True); combo(13,1,"Cookie policy","fanti_cookie_policy",[(x,x) for x in ("disabled","per-request","per-host","per-job","persistent")])
        spin(14,0,"Bandwidth limit","fanti_bandwidth_limit_bytes_per_sec",0,1024*1024*1024,0,1024," B/s")
        spin(14,1,"Browser timeout","fanti_browser_timeout",0.1,600.0,30.0,0.1," s")
        check(15,0,"Enable browser rendering","fanti_enable_browser_rendering",False); check(15,1,"Diagnostic mode","fanti_diagnostic_mode",False)
        help_text = QLabel("FANTI controls transport resilience, pacing, connection pooling, retries, cookies and diagnostics. They do not bypass authentication, CAPTCHA, paywalls, robots restrictions or access controls."); help_text.setWordWrap(True); fl.addWidget(help_text,16,0,1,4)
        cl.addWidget(fanti)
        cl.addStretch()
        scroll.setWidgetResizable(True)
        self._make_layout_responsive()

    def _ia_page_controls(self):
        return

    def _build_archive_page(self):
        p = QWidget(); l = QVBoxLayout(p); l.setContentsMargins(24,20,24,20); l.setSpacing(12)
        h = QHBoxLayout(); title = QLabel("🌐 Archive Explorer"); title.setObjectName("pageHeader"); h.addWidget(title); h.addStretch(); refresh=QPushButton("↻ Refresh"); refresh.clicked.connect(self._refresh_archive_explorer); h.addWidget(refresh); l.addLayout(h)
        sub=QLabel("Browse the complete local resource mirror, preview downloaded files, and open the configured IA item."); sub.setObjectName("pageSubtitle"); sub.setWordWrap(True); l.addWidget(sub)
        split=QSplitter(Qt.Orientation.Horizontal); split.setChildrenCollapsible(False)
        self.archive_tree=QTreeWidget(); self.archive_tree.setHeaderLabels(["Downloaded site / resource"]); self.archive_tree.setMinimumWidth(430); self.archive_tree.itemDoubleClicked.connect(self._preview_selected); split.addWidget(self.archive_tree)
        right=QWidget(); right.setMinimumWidth(520); rl=QVBoxLayout(right); self.archive_info=QLabel("Select a crawl or file."); self.archive_info.setWordWrap(True); rl.addWidget(self.archive_info); self.archive_preview=QTextBrowser(); self.archive_preview.setOpenExternalLinks(True); rl.addWidget(self.archive_preview,1)
        br=QHBoxLayout(); self.open_local=QPushButton("📄 Open Preview"); self.open_local.clicked.connect(self._preview_selected); br.addWidget(self.open_local); self.open_ia=QPushButton("☁️ Open IA Item"); self.open_ia.clicked.connect(self._open_ia); br.addWidget(self.open_ia); br.addStretch(); rl.addLayout(br); split.addWidget(right); split.setStretchFactor(0,1); split.setStretchFactor(1,2); split.setSizes([500,900]); l.addWidget(split,1); self.pages.addWidget(p); self._archive_page=p

    def _page_v12(self,k):
        if k=="archive":
            if not hasattr(self,"_archive_page"): self._build_archive_page()
            self.pages.setCurrentWidget(self._archive_page)
            for b in self.nav.values(): b.setChecked(False)
            if hasattr(self,"nav_v12_archive"): self.nav_v12_archive.setChecked(True)
            self._refresh_archive_explorer()
        elif k=="resume":
            self.pages.setCurrentWidget(self._resume_page)
            for b in self.nav.values(): b.setChecked(False)
            if hasattr(self,"nav_v12_resume"): self.nav_v12_resume.setChecked(True)
            self._refresh_resume_list()

    def _install_v12_nav(self):
        side=self.findChild(QWidget,"sidebar")
        if side and side.layout():
            if not hasattr(self,"nav_v12_resume"):
                b=QPushButton("♻️ Resume Center"); b.setObjectName("navButton"); b.setCheckable(True); b.clicked.connect(lambda: self._page_v12("resume")); side.layout().insertWidget(max(0,side.layout().count()-2),b); self.nav_v12_resume=b
            if not hasattr(self,"nav_v12_archive"):
                b=QPushButton("🌐 Archive Explorer"); b.setObjectName("navButton"); b.setCheckable(True); b.clicked.connect(lambda: self._page_v12("archive")); side.layout().insertWidget(max(0,side.layout().count()-2),b); self.nav_v12_archive=b

    def showEvent(self,e):
        super().showEvent(e); self._install_v12_nav(); self._make_layout_responsive()

    def _choose_tmp(self):
        p=QFileDialog.getExistingDirectory(self,"Choose TMPCRAWL folder",self.v12_tmp.text())
        if p: self.v12_tmp.setText(p); self._save_v12_settings(); self._refresh_resume_list(); self._refresh_archive_explorer()

    def _open_resume_storage(self):
        path=Path(self.v12_tmp.text()); path.mkdir(parents=True,exist_ok=True); self._open_path(path)

    @staticmethod
    def _open_path(path):
        try:
            if sys.platform.startswith("win"): os.startfile(str(path))
            elif sys.platform=="darwin": subprocess.Popen(["open",str(path)])
            else: subprocess.Popen(["xdg-open",str(path)])
        except Exception: pass

    def _load_v12_settings(self):
        try:self._v12=json.loads(self.SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:self._v12={}
        if hasattr(self,"v12_tmp"):
            self.v12_tmp.setText(self._v12.get("tmpcrawl_dir",self.v12_tmp.text())); self.v12_limit.setValue(int(self._v12.get("max_local_storage_mb",0))); self.v12_reserve.setValue(int(self._v12.get("min_free_space_mb",2048))); self.v12_keep.setChecked(bool(self._v12.get("keep_local_mirror",True))); self.v12_purge.setChecked(bool(self._v12.get("purge_local_files_after_upload",False))); self.v12_live.setChecked(bool(self._v12.get("archive_upload_live",True))); self.v12_verify.setChecked(bool(self._v12.get("archive_verify_uploads",True))); self.v12_follow_links.setChecked(bool(self._v12.get("follow_links",True))); self.v12_external.setChecked(bool(self._v12.get("follow_external_domains",False)))
            for key,w in getattr(self,"fanti_widgets",{}).items():
                if key in self._v12:
                    try:
                        val=self._v12[key]
                        if isinstance(w,QComboBox): w.setCurrentIndex(max(0,w.findData(val)))
                        elif isinstance(w,QCheckBox): w.setChecked(bool(val))
                        else: w.setValue(val)
                    except Exception: pass

    def _save_v12_settings(self):
        self._v12={"tmpcrawl_dir":self.v12_tmp.text(),"max_local_storage_mb":self.v12_limit.value(),"min_free_space_mb":self.v12_reserve.value(),"keep_local_mirror":self.v12_keep.isChecked(),"purge_local_files_after_upload":self.v12_purge.isChecked(),"archive_upload_live":self.v12_live.isChecked(),"archive_verify_uploads":self.v12_verify.isChecked(),"follow_links":self.v12_follow_links.isChecked(),"follow_external_domains":self.v12_external.isChecked(),"resume_dir":self._v12.get("resume_dir","")}
        for key,w in getattr(self,"fanti_widgets",{}).items(): self._v12[key]=w.currentData() if isinstance(w,QComboBox) else (w.isChecked() if isinstance(w,QCheckBox) else w.value())
        self.SETTINGS_FILE.parent.mkdir(parents=True,exist_ok=True); self.SETTINGS_FILE.write_text(json.dumps(self._v12,ensure_ascii=False,indent=2),encoding="utf-8")

    def _cfg(self):
        c=super()._cfg(); self._save_v12_settings()
        for k,v in self._v12.items(): setattr(c,k,v)
        c.fallback_dir=self.v12_tmp.text(); c.follow_links=self.v12_follow_links.isChecked(); c.follow_external_domains=self.v12_external.isChecked(); c.download_discovered_files=True; c.file_types=["*"]; c.max_file_size=-1
        return c

    def start_crawl(self):
        self._save_v12_settings(); super().start_crawl(); QTimer.singleShot(500,self._refresh_resume_list)

    def _resume_selected(self):
        item=self.resume_table.currentItem() if hasattr(self,"resume_table") else None
        if item:
            path=item.data(0,Qt.ItemDataRole.UserRole)
        else:
            item=self.resume_list.currentItem() if hasattr(self,"resume_list") else None
            path=item.data(Qt.ItemDataRole.UserRole) if item else None
        if not path: return
        self._v12["resume_dir"]=path; self._save_v12_settings(); self._log(f"♻️ Resume requested: {path}"); self.start_crawl()

    def _finished(self,msg):
        super()._finished(msg); self._v12["resume_dir"]=""; self._save_v12_settings(); QTimer.singleShot(200,self._refresh_resume_list); QTimer.singleShot(500,self._refresh_archive_explorer)

    def _refresh_resume_list(self):
        if not hasattr(self,"resume_list"): return
        root=Path(self.v12_tmp.text()) if hasattr(self,"v12_tmp") else Path.home()/"AWEC"/"tmpcrawl"
        try: items=find_resumable_crawls(root)
        except Exception as exc: items=[]; self._log(f"⚠️ Resume scan failed: {exc}")
        self.resume_list.clear()
        if hasattr(self,"resume_table"):
            self.resume_table.clear()
        total_pending=total_active=total_done=total_failed=0
        for x in items:
            counts=x.get("counts",{}); path=x.get("path","")
            pending=int(counts.get("pending",0)); active=int(counts.get("in_progress",0)); done=int(counts.get("completed",0)); failed=int(counts.get("failed",0)); total_pending+=pending; total_active+=active; total_done+=done; total_failed+=failed
            li=QListWidgetItem(f"{x.get('crawl_id','unknown')} • pending {pending:,} • active {active:,} • completed {done:,} • failed {failed:,}"); li.setData(Qt.ItemDataRole.UserRole,path); self.resume_list.addItem(li)
            if hasattr(self,"resume_table"):
                ti=QTreeWidgetItem([x.get("crawl_id","unknown"),f"{pending:,}",f"{active:,}",f"{done:,}",f"{failed:,}",path]); ti.setData(0,Qt.ItemDataRole.UserRole,path); self.resume_table.addTopLevelItem(ti)
        if not items:
            self.resume_list.addItem("✓ No interrupted crawls found")
        if hasattr(self,"resume_summary"):
            self.resume_summary.setText(f"{len(items):,} resumable crawl(s) • pending {total_pending:,} • in progress {total_active:,} • completed {total_done:,} • failed {total_failed:,}")

    def _refresh_archive_explorer(self):
        if not hasattr(self,"archive_tree"): return
        self.archive_tree.clear(); root=Path(self.v12_tmp.text()) if hasattr(self,"v12_tmp") else Path.home()/"AWEC"/"tmpcrawl"
        for site in sorted(root.glob("crawls/*/site"),key=lambda p:p.parent.stat().st_mtime,reverse=True):
            top=QTreeWidgetItem([f"🗂 {site.parent.name} • {site}"]); top.setData(0,Qt.ItemDataRole.UserRole,str(site)); self.archive_tree.addTopLevelItem(top); count=0
            try:
                for f in site.rglob("*"):
                    if f.is_file():
                        it=QTreeWidgetItem([str(f.relative_to(site))]); it.setData(0,Qt.ItemDataRole.UserRole,str(f)); top.addChild(it); count+=1
                        if count>=20000: break
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
            try:self.archive_preview.setPlainText(p.read_text(encoding='utf-8',errors='replace')[:500000])
            except Exception:self.archive_preview.setPlainText(f"Binary resource: {p.name}")

    def _open_ia(self):
        c=self._cfg(); ident=str(getattr(c,'ia_identifier','')).strip()
        if not ident: QMessageBox.information(self,'AWEC','Configure an Internet Archive Item Name first.'); return
        self._open_path(Path('https://archive.org/details/'+ident))
