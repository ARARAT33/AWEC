"""AWEC Desktop UI v5 - clean, runtime-safe PySide6 interface."""
from __future__ import annotations
import os
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QWidget
from desktop.config_schema import AWECConfig
from desktop.engine import Engine
from awec.archive.ia import IAUploader


def W(cls, *args, name=None):
    w = cls(*args)
    if name: w.setObjectName(name)
    return w


class AWECMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = AWECConfig(); self.engine = None; self.thread = None; self.running = False
        self.setWindowTitle("AWEC • Web Archive Engine"); self.resize(1280, 820); self.setMinimumSize(1050, 700)
        self._build(); self._load_config()

    def _shell(self, title, subtitle):
        p = QWidget(); l = QVBoxLayout(p); l.setContentsMargins(30,26,30,26); l.setSpacing(14)
        l.addWidget(W(QLabel, title, name="pageHeader")); l.addWidget(W(QLabel, subtitle, name="pageSubtitle")); return p,l

    def _build(self):
        root = QWidget(); self.setCentralWidget(root); rl = QHBoxLayout(root); rl.setContentsMargins(0,0,0,0); rl.setSpacing(0)
        side = W(QFrame, name="sidebar"); side.setFixedWidth(225); sl = QVBoxLayout(side); sl.setContentsMargins(18,22,18,18)
        sl.addWidget(W(QLabel,"AWEC",name="brandTitle")); sl.addWidget(W(QLabel,"Web Archive Engine",name="brandSubtitle")); sl.addSpacing(20)
        self.nav={}
        for k,t in (("dashboard","Dashboard"),("sites","Sites"),("crawler","Crawler"),("ia","Internet Archive"),("logs","Live Logs")):
            b=W(QPushButton,t,name="navButton"); b.setCheckable(True); b.clicked.connect(lambda _,x=k:self._page(x)); self.nav[k]=b; sl.addWidget(b)
        sl.addStretch(); self.status=W(QLabel,"● READY",name="statusBadgeStopped"); self.status.setAlignment(Qt.AlignmentFlag.AlignCenter); sl.addWidget(self.status); rl.addWidget(side)
        self.pages=QStackedWidget(); rl.addWidget(self.pages,1); self._dashboard(); self._sites(); self._crawler(); self._ia(); self._logs(); self._page("dashboard")

    def _dashboard(self):
        p,l=self._shell("Dashboard","Start a crawl and monitor AWEC in real time."); grid=QGridLayout(); grid.setSpacing(12); self.metrics={}
        for i,(k,t) in enumerate((("queued","Queued"),("enqueued","URLs"),("pages","Pages"),("found","Files"),("downloaded","Uploaded"),("errors","Errors"),("active","Active"),("speed","State"))):
            c=W(QFrame,name="metricCard"); q=QVBoxLayout(c); q.addWidget(W(QLabel,t.upper(),name="metricTitle")); v=W(QLabel,"0",name="metricValue"); q.addWidget(v); self.metrics[k]=v; grid.addWidget(c,i//4,i%4)
        l.addLayout(grid); box=QGroupBox("Quick Start"); f=QFormLayout(box); self.quick=QLineEdit(); self.quick.setPlaceholderText("https://example.com"); self.quick.returnPressed.connect(self.start_crawl); f.addRow("Seed URL",self.quick); self.domain=QLabel("—"); f.addRow("Active domain",self.domain); l.addWidget(box)
        row=QHBoxLayout(); self.start_btn=W(QPushButton,"▶  Start Crawl",name="primaryButton"); self.start_btn.clicked.connect(self.start_crawl); self.pause_btn=W(QPushButton,"⏸  Pause",name="warningButton"); self.pause_btn.clicked.connect(self.pause_crawl); self.stop_btn=W(QPushButton,"■  Stop",name="dangerButton"); self.stop_btn.clicked.connect(self.stop_crawl); row.addWidget(self.start_btn); row.addWidget(self.pause_btn); row.addWidget(self.stop_btn); l.addLayout(row)
        self.dashboard_log=QPlainTextEdit(); self.dashboard_log.setReadOnly(True); self.dashboard_log.setMaximumBlockCount(300); self.dashboard_log.setPlaceholderText("Engine messages appear here…"); l.addWidget(self.dashboard_log,1); self.pages.addWidget(p)

    def _sites(self):
        p,l=self._shell("Seed Sites","Add the URLs AWEC should crawl."); self.site_list=QListWidget(); l.addWidget(self.site_list,1)
        row=QHBoxLayout(); self.site_input=QLineEdit(); self.site_input.setPlaceholderText("example.com or https://example.com"); self.site_input.returnPressed.connect(self.add_site); add=W(QPushButton,"＋ Add Site",name="primaryButton"); add.clicked.connect(self.add_site); row.addWidget(self.site_input,1); row.addWidget(add); l.addLayout(row)
        row2=QHBoxLayout(); rm=QPushButton("Remove Selected"); rm.clicked.connect(self.remove_site); cl=QPushButton("Clear All"); cl.clicked.connect(self.site_list.clear); row2.addWidget(rm); row2.addWidget(cl); row2.addStretch(); l.addLayout(row2); self.pages.addWidget(p)

    def _crawler(self):
        p,l=self._shell("Crawler","Core crawl and FANTI transport settings."); scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame); c=QWidget(); cl=QVBoxLayout(c)
        g=QGroupBox("General"); f=QFormLayout(g); self.workers=QSpinBox(); self.workers.setRange(1,512); f.addRow("Workers",self.workers); self.depth=QSpinBox(); self.depth.setRange(0,100); f.addRow("Max depth",self.depth); self.max_urls=QSpinBox(); self.max_urls.setRange(0,2000000000); f.addRow("Max URLs (0 = unlimited)",self.max_urls); self.delay=QDoubleSpinBox(); self.delay.setRange(0,120); self.delay.setDecimals(2); f.addRow("Per-host delay (s)",self.delay); self.timeout=QSpinBox(); self.timeout.setRange(1,600); f.addRow("Timeout (s)",self.timeout); self.retries=QSpinBox(); self.retries.setRange(0,20); f.addRow("Retries",self.retries); self.same_domain=QCheckBox("Stay on seed domains"); f.addRow(self.same_domain); self.robots=QCheckBox("Respect robots.txt"); f.addRow(self.robots); cl.addWidget(g)
        n=QGroupBox("Network / FANTI"); nf=QFormLayout(n); self.net_mode=QComboBox(); self.net_mode.addItem("STANDARD","standard"); self.net_mode.addItem("FANTI","fanti"); nf.addRow("Mode",self.net_mode); self.ua=QLineEdit(); nf.addRow("User-Agent",self.ua); self.ua_rotate=QCheckBox("Rotate User-Agent pool"); nf.addRow(self.ua_rotate); self.jitter=QDoubleSpinBox(); self.jitter.setRange(0,30); self.jitter.setDecimals(2); nf.addRow("Delay jitter (s)",self.jitter); self.cookies=QCheckBox("Persistent cookie sessions"); nf.addRow(self.cookies); self.ssl=QCheckBox("Verify TLS certificates"); nf.addRow(self.ssl); self.proxy=QLineEdit(); self.proxy.setPlaceholderText("optional HTTP/SOCKS proxy"); nf.addRow("Proxy",self.proxy); cl.addWidget(n); scroll.setWidget(c); l.addWidget(scroll,1); self.pages.addWidget(p)

    def _ia(self):
        p,l=self._shell("Internet Archive","Collection must exist. A missing Item Name is created on the first successful upload."); box=QGroupBox("Archive Destination"); f=QFormLayout(box)
        self.ia_collection=QLineEdit(); self.ia_collection.setPlaceholderText("Collection Name"); self.ia_item=QLineEdit(); self.ia_item.setPlaceholderText("Item Name"); self.ia_title=QLineEdit(); self.ia_title.setPlaceholderText("Item Title"); self.ia_creator=QLineEdit(); self.ia_creator.setPlaceholderText("Creator"); self.ia_desc=QPlainTextEdit(); self.ia_desc.setMaximumHeight(72); self.ia_access=QLineEdit(); self.ia_access.setEchoMode(QLineEdit.EchoMode.Password); self.ia_secret=QLineEdit(); self.ia_secret.setEchoMode(QLineEdit.EchoMode.Password); self.ia_endpoint=QLineEdit("https://s3.us.archive.org")
        for label,w in (("Collection Name",self.ia_collection),("Item Name",self.ia_item),("Item Title",self.ia_title),("Creator",self.ia_creator),("Description",self.ia_desc),("S3 Access Key",self.ia_access),("S3 Secret Key",self.ia_secret),("S3 Endpoint",self.ia_endpoint)): f.addRow(label,w)
        l.addWidget(box); self.ia_status=W(QLabel,"● Not checked",name="infoBadge"); l.addWidget(self.ia_status); row=QHBoxLayout(); ck=QPushButton("✓ Check Collection / Item"); ck.clicked.connect(self.check_ia); sv=W(QPushButton,"Save Settings",name="primaryButton"); sv.clicked.connect(self.save_config); row.addWidget(ck); row.addWidget(sv); row.addStretch(); l.addLayout(row); h=W(QLabel,"Flow: Collection check → Item check → missing item is created by first upload → crawl continues.",name="hint"); h.setWordWrap(True); l.addWidget(h); l.addStretch(); self.pages.addWidget(p)

    def _logs(self):
        p,l=self._shell("Live Logs","Engine output, IA status and errors."); self.logs=QPlainTextEdit(); self.logs.setReadOnly(True); self.logs.document().setMaximumBlockCount(1500); l.addWidget(self.logs,1); b=QPushButton("Clear Logs"); b.clicked.connect(self.logs.clear); l.addWidget(b,0,Qt.AlignmentFlag.AlignRight); self.pages.addWidget(p)

    def _page(self,k):
        self.pages.setCurrentIndex({"dashboard":0,"sites":1,"crawler":2,"ia":3,"logs":4}[k]); [b.setChecked(x==k) for x,b in self.nav.items()]
    def add_site(self):
        u=self.site_input.text().strip()
        if not u:return
        if not u.startswith(("http://","https://")):u="https://"+u
        if not any(self.site_list.item(i).text()==u for i in range(self.site_list.count())):self.site_list.addItem(u)
        self.site_input.clear()
    def remove_site(self):
        r=self.site_list.currentRow()
        if r>=0:self.site_list.takeItem(r)
    def _cfg(self):
        seeds=[self.site_list.item(i).text() for i in range(self.site_list.count())]
        if self.quick.text().strip():
            u=self.quick.text().strip();u=u if u.startswith(("http://","https://")) else "https://"+u
            if u not in seeds:seeds.append(u)
        return AWECConfig(seeds=seeds,network_mode=self.net_mode.currentData(),workers=self.workers.value(),max_depth=self.depth.value(),max_urls=self.max_urls.value(),per_host_delay=self.delay.value(),request_timeout=self.timeout.value(),max_retries=self.retries.value(),same_domain_only=self.same_domain.isChecked(),respect_robots=self.robots.isChecked(),custom_user_agent=self.ua.text(),ua_rotation_enabled=self.ua_rotate.isChecked(),delay_jitter_sec=self.jitter.value(),cookie_jar_enabled=self.cookies.isChecked(),verify_ssl=self.ssl.isChecked(),proxy_url=self.proxy.text(),ia_collection=self.ia_collection.text().strip(),ia_identifier=self.ia_item.text().strip(),ia_title=self.ia_title.text().strip(),ia_creator=self.ia_creator.text().strip(),ia_description=self.ia_desc.toPlainText().strip(),ia_access_key=self.ia_access.text(),ia_secret_key=self.ia_secret.text(),ia_endpoint=self.ia_endpoint.text().strip() or "https://s3.us.archive.org")
    def _load_config(self):
        try:self.config=AWECConfig.load(Path.home()/"AWEC"/"config.json")
        except Exception:self.config=AWECConfig()
        c=self.config
        for u in c.seeds:self.site_list.addItem(u)
        self.workers.setValue(min(8,max(1,c.workers)));self.depth.setValue(c.max_depth);self.max_urls.setValue(c.max_urls);self.delay.setValue(c.per_host_delay);self.timeout.setValue(c.request_timeout);self.retries.setValue(c.max_retries);self.same_domain.setChecked(c.same_domain_only);self.robots.setChecked(c.respect_robots);self.net_mode.setCurrentIndex(1 if c.network_mode=="fanti" else 0);self.ua.setText(c.custom_user_agent);self.ua_rotate.setChecked(c.ua_rotation_enabled);self.jitter.setValue(c.delay_jitter_sec);self.cookies.setChecked(c.cookie_jar_enabled);self.ssl.setChecked(c.verify_ssl);self.proxy.setText(c.proxy_url);self.ia_collection.setText(c.ia_collection);self.ia_item.setText(c.ia_identifier);self.ia_title.setText(c.ia_title);self.ia_creator.setText(c.ia_creator);self.ia_desc.setPlainText(c.ia_description);self.ia_access.setText(c.ia_access_key);self.ia_secret.setText(c.ia_secret_key);self.ia_endpoint.setText(c.ia_endpoint)
    def save_config(self):
        try:self.config=self._cfg();self.config.save(Path.home()/"AWEC"/"config.json");self.ia_status.setText("✓ Settings saved locally");self._log("💾 Configuration saved")
        except Exception as e:QMessageBox.critical(self,"AWEC",str(e))
    def check_ia(self):
        c=self.ia_collection.text().strip();i=self.ia_item.text().strip()
        if not c or not i:self.ia_status.setText("⚠ Collection Name and Item Name are required");return
        if not self.ia_access.text() or not self.ia_secret.text():self.ia_status.setText("⚠ S3 credentials are required");return
        try:
            u=IAUploader(self.ia_access.text(),self.ia_secret.text(),i,self.ia_endpoint.text().strip() or "https://s3.us.archive.org",collection=c,title=self.ia_title.text(),creator=self.ia_creator.text(),description=self.ia_desc.toPlainText());ok,msg=u.validate_destination();self.ia_status.setText(("✓ " if ok else "✗ ")+msg);self._log(("✓ " if ok else "✗ ")+msg)
        except Exception as e:self.ia_status.setText("✗ IA CHECK FAILED: "+str(e));self._log("❌ IA check failed: "+str(e))
    def start_crawl(self):
        if self.running:
            if self.engine and self.engine.is_paused:self.engine.is_paused=False;self.status.setText("● RUNNING");self._log("▶ Crawl resumed")
            return
        if self.quick.text().strip():self.add_quick_seed()
        if self.site_list.count()==0:QMessageBox.warning(self,"AWEC","Add at least one seed URL.");return
        c=self._cfg();os.environ["AWEC_IA_COLLECTION"]=c.ia_collection;os.environ["AWEC_IA_TITLE"]=c.ia_title;os.environ["AWEC_IA_CREATOR"]=c.ia_creator;os.environ["AWEC_IA_DESCRIPTION"]=c.ia_description
        self.engine=Engine(c);self.thread=QThread();self.engine.moveToThread(self.thread);self.thread.started.connect(self.engine.start);self.engine.log.connect(self._log);self.engine.stats.connect(self._stats);self.engine.finished.connect(self._finished);self.thread.start();self.running=True;self.status.setText("● RUNNING");self.start_btn.setEnabled(False);self._log("🚀 AWEC engine started")
    def add_quick_seed(self):
        u=self.quick.text().strip();u=u if u.startswith(("http://","https://")) else "https://"+u
        if not any(self.site_list.item(i).text()==u for i in range(self.site_list.count())):self.site_list.addItem(u)
    def pause_crawl(self):
        if self.engine:self.engine.is_paused=True;self.status.setText("● PAUSED");self.start_btn.setEnabled(True);self._log("⏸ Crawl paused")
    def stop_crawl(self):
        if self.engine:self.engine.stop();self.status.setText("● STOPPING");self._log("🛑 Stop requested")
    @Slot(dict)
    def _stats(self,s):
        for k,v in s.items():
            if k in self.metrics:self.metrics[k].setText(f"{v:,}" if isinstance(v,(int,float)) else str(v))
        if "active_domain" in s:self.domain.setText(str(s["active_domain"]))
    @Slot(str)
    def _log(self,msg):
        self.logs.appendPlainText(msg);self.dashboard_log.appendPlainText(msg)
    @Slot(str)
    def _finished(self,msg):
        self.running=False;self.start_btn.setEnabled(True);self.status.setText("● READY");self._log("🏁 Crawl finished: "+msg)
        if self.thread:self.thread.quit()
    def closeEvent(self,e):
        if self.engine:self.engine.stop()
        if self.thread and self.thread.isRunning():self.thread.quit();self.thread.wait(2000)
        e.accept()
